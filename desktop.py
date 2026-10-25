"""Explicit Windows desktop control, with screenshot coordinates and a latched stop."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import threading
import time

from tools import STRING, declaration


INTEGER = {"type": "integer"}
OBSERVATION = {"observation_id": INTEGER}
DECLARATIONS = [
    declaration("desktop_observe", "Capture the primary monitor. Observe before acting, including after errors.", {}, []),
    declaration("desktop_click", "Click pixel coordinates in the referenced screenshot. button is left/right; clicks is 1/2.",
                {**OBSERVATION, "x": INTEGER, "y": INTEGER, "button": STRING, "clicks": INTEGER},
                ["observation_id", "x", "y", "button", "clicks"]),
    declaration("desktop_type", "Type literal Unicode text into the focused control. Does not clear existing text.",
                {**OBSERVATION, "text": STRING}, ["observation_id", "text"]),
    declaration("desktop_keys", "Press one key or a shortcut together, e.g. ['ctrl','s']. F12 is reserved for emergency stop.",
                {**OBSERVATION, "keys": {"type": "array", "items": STRING}}, ["observation_id", "keys"]),
    declaration("desktop_scroll", "Scroll at the current pointer. Positive clicks scroll up; negative scroll down.",
                {**OBSERVATION, "clicks": INTEGER}, ["observation_id", "clicks"]),
    declaration("desktop_verify", "Record your visual assessment of the referenced screenshot. This is model judgment, not an independent check. Also cite read_file for saved-file tasks.",
                {**OBSERVATION, "finding": STRING}, ["observation_id", "finding"]),
]


class DesktopStopped(RuntimeError):
    pass


class Desktop:
    def __init__(self, directory):
        if sys.platform != "win32":
            raise ValueError("Desktop tools currently support Windows only")
        try:
            import pyautogui
            from PIL import Image
        except ImportError as exc:
            raise ValueError("Install desktop dependencies: python -m pip install -r requirements-desktop.txt") from exc
        self.gui = pyautogui
        self.gui.FAILSAFE = True
        self.gui.PAUSE = 0.15
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.directory = Path(directory)
        (self.directory / "desktop").mkdir(exist_ok=True)
        self.stop_file = self.directory / "STOP"
        self.stopped = threading.Event()
        self.closed = threading.Event()
        self.revision = 0
        self.sequence = max((int(p.stem) for p in (self.directory / "desktop").glob("*.png") if p.stem.isdigit()), default=0)
        self.last = None
        self.watcher = threading.Thread(target=self._watch_stop, daemon=True)
        self.watcher.start()

    def _watch_stop(self):
        while not self.closed.wait(0.05):
            if self.user32.GetAsyncKeyState(0x7B) & 0x8000 or self.stop_file.exists():
                self.stopped.set()
                return

    def check_stop(self):
        if self.stopped.is_set() or self.stop_file.exists():
            raise DesktopStopped("Desktop emergency stop activated; no further actions will run")
        try:
            self.gui.failSafeCheck()
        except self.gui.FailSafeException as exc:
            self.stopped.set()
            raise DesktopStopped("Mouse corner fail-safe activated; run stopped") from exc

    def close(self):
        self.closed.set()
        self.watcher.join(timeout=1)

    def foreground(self):
        handle = self.user32.GetForegroundWindow()
        if not handle:
            raise ValueError("No foreground desktop window; unlock the desktop and observe again")
        return handle

    def observe(self):
        self.check_stop()
        self.last = None
        handle = self.foreground()
        screenshot = self.gui.screenshot()
        screen_width, screen_height = self.gui.size()
        if screenshot.size != (screen_width, screen_height):
            raise ValueError("Screenshot and primary monitor coordinates differ; check display scaling")
        screenshot.thumbnail((1600, 1600))
        self.sequence += 1
        relative = f"desktop/{self.sequence:04d}.png"
        screenshot.save(self.directory / relative)
        if self.foreground() != handle:
            raise ValueError("Foreground window changed during capture; observe again")
        result = {"screenshot": relative, "image_width": screenshot.width, "image_height": screenshot.height,
                  "screen_width": screen_width, "screen_height": screen_height,
                  "observation_id": self.sequence, "revision": self.revision}
        self.last = {**result, "foreground": handle, "captured_at": time.monotonic()}
        return result

    def require_observation(self, observation_id):
        self.check_stop()
        if self.last is None or observation_id != self.last["observation_id"]:
            expected = self.last["observation_id"] if self.last is not None else "none"
            raise ValueError(f"Missing or stale desktop observation: received {observation_id}, latest ID is {expected}. "
                             "Use observation_id, not the tool step; call desktop_observe")
        if time.monotonic() - self.last["captured_at"] > 60:
            raise ValueError("Desktop observation is older than 60 seconds; observe again")
        if self.foreground() != self.last["foreground"]:
            raise ValueError("Foreground window changed; observe before sending input")
        if tuple(self.gui.size()) != (self.last["screen_width"], self.last["screen_height"]):
            raise ValueError("Screen dimensions changed; observe again")
        return self.last

    def type_unicode(self, text):
        # Send Unicode without replacing or reading the user's clipboard.
        target = self.foreground()
        class Keyboard(ctypes.Structure):
            _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
        class Mouse(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
        class Payload(ctypes.Union):
            _fields_ = [("keyboard", Keyboard), ("mouse", Mouse)]
        class Input(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("payload", Payload)]
        send = self.user32.SendInput
        send.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        send.restype = wintypes.UINT
        for char in text:
            self.check_stop()
            if self.foreground() != target:
                raise ValueError("Focus changed while typing; text may be partially entered")
            if char in "\n\t":
                self.gui.press("enter" if char == "\n" else "tab")
                continue
            encoded = char.encode("utf-16-le")
            units = [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded), 2)]
            events = (Input * (2 * len(units)))()
            for index, unit in enumerate(units):
                for offset, flags in enumerate((0x0004, 0x0004 | 0x0002)):
                    events[2 * index + offset].type = 1
                    events[2 * index + offset].payload.keyboard = Keyboard(0, unit, flags, 0, 0)
            if send(len(events), events, ctypes.sizeof(Input)) != len(events):
                raise OSError("Windows rejected keyboard input; text may be partially entered")
            time.sleep(0.03)

    def verify_evidence(self, result):
        current = self.require_observation(result["observation_id"])
        if result["revision"] != self.revision or current["revision"] != self.revision:
            raise ValueError("Desktop evidence is stale; observe and verify again")

    def execute(self, name, arguments):
        self.check_stop()
        try:
            if name == "desktop_observe":
                return {"ok": True, **self.observe()}
            observed = self.require_observation(arguments["observation_id"])
            if name == "desktop_verify":
                if not arguments["finding"].strip():
                    raise ValueError("Describe the visible evidence")
                return {"ok": True, **{key: value for key, value in observed.items()
                                      if key not in {"foreground", "captured_at"}},
                        "visual_assessment": arguments["finding"], "verification_kind": "model_visual_assessment"}
            if name == "desktop_click":
                x, y = arguments["x"], arguments["y"]
                if not 0 <= x < observed["image_width"] or not 0 <= y < observed["image_height"]:
                    raise ValueError("Click coordinates are outside the screenshot")
                if arguments["button"] not in {"left", "right"} or arguments["clicks"] not in {1, 2}:
                    raise ValueError("Use left/right button and 1/2 clicks")
                x = round(x * observed["screen_width"] / observed["image_width"])
                y = round(y * observed["screen_height"] / observed["image_height"])
                action = lambda: self.gui.click(x, y, clicks=arguments["clicks"], button=arguments["button"], interval=0.1)
            elif name == "desktop_type":
                text = arguments["text"]
                if not text or len(text) > 4000 or any(ord(c) < 32 and c not in "\n\t" for c in text):
                    raise ValueError("Type 1-4000 characters; only newline/tab control characters are supported")
                action = lambda: self.type_unicode(text)
            elif name == "desktop_keys":
                keys = arguments["keys"]
                if not 1 <= len(keys) <= 4 or any(key not in self.gui.KEYBOARD_KEYS or key == "f12" for key in keys):
                    raise ValueError("Use 1-4 valid PyAutoGUI key names; f12 is reserved for emergency stop")
                action = lambda: self.gui.hotkey(*keys)
            elif name == "desktop_scroll":
                clicks = arguments["clicks"]
                if not -10 <= clicks <= 10 or clicks == 0:
                    raise ValueError("Scroll clicks must be -10..-1 or 1..10")
                action = lambda: self.gui.scroll(clicks)
            else:
                raise ValueError(f"Unknown desktop tool: {name}")
            self.revision += 1
            self.last = None
            action()
            time.sleep(0.5)
            return {"ok": True, **self.observe()}
        except self.gui.FailSafeException as exc:
            self.stopped.set()
            raise DesktopStopped("Mouse corner fail-safe activated; run stopped") from exc
        except (ValueError, OSError) as exc:
            self.last = None
            return {"ok": False, "error": str(exc), "error_type": type(exc).__name__,
                    "note": "Input may already have occurred. Observe before repeating any action."}
