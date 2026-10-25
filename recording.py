"""Opt-in Windows primary-screen recording. No audio, uploads, or automatic retry."""

import ctypes
from ctypes import wintypes
import os
import subprocess
import threading
from uuid import uuid4


def parent_bound_job(process):
    """Windows closes this non-inherited handle on parent exit, killing the encoder."""
    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
                    ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                    ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle, int(process._handle)):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(handle)
        raise error
    return kernel, handle


class ScreenRecorder:
    def __init__(self, log):
        if os.name != "nt":
            raise RuntimeError("Screen recording currently requires Windows")
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            from PIL import ImageGrab
        except ImportError as exc:
            raise RuntimeError("Install recording dependencies: python -m pip install -r requirements-recording.txt") from exc
        self.log = log
        self.grab = ImageGrab.grab
        self.process = None
        self.job = None
        self.closed = False
        self.ready = threading.Event()
        self.frames = 0
        directory = log.directory / "recordings"
        directory.mkdir(exist_ok=True)
        self.stem = "segment-" + uuid4().hex[:12]
        self.relative = f"recordings/{self.stem}.mp4"
        self.video = log.directory / self.relative
        self.error_path = directory / f"{self.stem}.log"
        # Match Pillow's primary-monitor pixel dimensions, including display scaling.
        width, height = self.grab().size
        executable = get_ffmpeg_exe()
        self.errors = self.error_path.open("wb")
        command = [executable, "-hide_banner", "-loglevel", "error", "-n",
                   "-f", "gdigrab", "-framerate", "5", "-offset_x", "0", "-offset_y", "0",
                   "-video_size", f"{width}x{height}", "-draw_mouse", "1", "-i", "desktop",
                   "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                   "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p",
                   "-movflags", "+frag_keyframe+empty_moov+default_base_moof", "-g", "10",
                   "-progress", "pipe:1", "-nostats", str(self.video)]
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.errors, creationflags=subprocess.CREATE_NO_WINDOW)
            self.job = parent_bound_job(self.process)
            self.reader = threading.Thread(target=self._progress, daemon=True)
            self.reader.start()
            if not self.ready.wait(15) or self.frames == 0:
                raise RuntimeError("Screen recorder did not produce a frame within 15 seconds")
            self.check()
            self.log.record("recording_started", video=self.relative, fps=5,
                            width=width, height=height, executable=executable,
                            scope="primary monitor; no audio")
        except (Exception, KeyboardInterrupt) as exc:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self._close_handles()
            self.log.record("recording_failed", video=self.relative, error=str(exc), diagnostic=self._diagnostic())
            raise RuntimeError(f"Recording startup failed: {exc}. {self._diagnostic()}") from exc

    def _progress(self):
        for line in iter(self.process.stdout.readline, b""):
            if line.startswith(b"frame="):
                self.frames = int(line.split(b"=", 1)[1].strip())
                if self.frames > 0:
                    self.ready.set()
        self.ready.set()

    def _diagnostic(self):
        return self.error_path.read_text(encoding="utf-8", errors="replace")[-4000:]

    def _close_handles(self):
        if self.job is not None:
            kernel, handle = self.job
            kernel.CloseHandle(handle)
            self.job = None
        if self.process is not None:
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    stream.close()
        self.errors.close()

    def check(self):
        if self.closed or self.process.poll() is not None:
            raise RuntimeError(f"Screen recording stopped unexpectedly. {self._diagnostic()}")

    def capture(self, step, phase):
        """Supplementary local evidence; never sent to the model as an observation."""
        self.check()
        directory = self.log.directory / "evidence"
        directory.mkdir(exist_ok=True)
        path = directory / f"{self.stem}-{step:04d}-{phase}.png"
        self.grab().save(path)
        self.log.record("step_screenshot", step=step, phase=phase,
                        screenshot=path.relative_to(self.log.directory).as_posix())

    def close(self):
        if self.closed:
            return
        self.closed = True
        failure = None
        try:
            if self.process.poll() is not None:
                raise RuntimeError("Recorder exited before recording was stopped")
            self.process.stdin.write(b"q\n")
            self.process.stdin.flush()
            code = self.process.wait(timeout=15)
            self.reader.join(timeout=2)
            if code != 0 or self.frames == 0 or not self.video.is_file() or self.video.stat().st_size == 0:
                raise RuntimeError(f"Recorder failed to finalize video (exit {code}, frames {self.frames})")
        except (Exception, KeyboardInterrupt) as exc:
            failure = exc
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
        finally:
            self._close_handles()
        if failure is not None:
            self.log.record("recording_failed", video=self.relative, error=str(failure), diagnostic=self._diagnostic())
            raise RuntimeError(f"Screen recording failed: {failure}. {self._diagnostic()}") from failure
        self.log.record("recording_stopped", video=self.relative, frames=self.frames,
                        bytes=self.video.stat().st_size)
