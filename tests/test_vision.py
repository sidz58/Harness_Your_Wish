import base64
import copy
import io
import json
from unittest.mock import patch

from gemini import Gemini
from harness import RunError
from test_agent import WorkspaceCase, Script, call
from vision import image_parts, remove_old_images


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


class VisionTests(WorkspaceCase):
    def test_wire_image_and_signature_preservation(self):
        (self.root / "screen.png").write_bytes(PNG)
        observation = {"screenshot": "screen.png", "image_width": 1, "image_height": 1, "step": 3, "observation_id": 1}
        parts, metadata = image_parts(self.root, observation, 1024)
        self.assertEqual(base64.b64decode(parts[1]["inlineData"]["data"]), PNG)
        self.assertEqual(metadata["bytes"], len(PNG))
        self.assertIn("observation_id=1", parts[0]["text"])
        content = call("desktop_observe")
        content["parts"][0]["thoughtSignature"] = "signature"
        history = [{"role": "user", "parts": [{"text": "Task"}, *parts]}, content]
        response = {"candidates": [{"finishReason": "STOP", "content": content}], "usageMetadata": {"totalTokenCount": 10}}
        with patch("gemini.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as request:
            Gemini("test").generate(history, [], "test")
        sent = json.loads(request.call_args.args[0].data)
        self.assertEqual(sent["contents"][0]["parts"][-1]["inlineData"]["mimeType"], "image/png")
        remove_old_images(history)
        self.assertFalse(any("inlineData" in part for part in history[0]["parts"]))
        self.assertEqual(history[1], content)

    def test_image_size_and_path_limits(self):
        (self.root / "screen.png").write_bytes(PNG)
        observation = {"screenshot": "screen.png", "image_width": 1, "image_height": 1, "step": 1}
        with self.assertRaisesRegex(ValueError, "budget"):
            image_parts(self.root, observation, 8)
        observation["screenshot"] = "../outside.png"
        with patch("vision.Path.resolve", side_effect=[self.root, self.root.parent / "outside.png"]):
            with self.assertRaisesRegex(ValueError, "leaves"):
                image_parts(self.root, observation, 1024)

    def test_latest_image_only_and_explicit_image_request_budget(self):
        class ScreenshotBrowser:
            revision = 0
            restored_observation = None
            def execute(inner, name, arguments):
                return {"ok": True, "screenshot": "screen.png", "image_width": 1, "image_height": 1}
        provider = Script(call("browser_observe"), call("browser_observe"), call("browser_observe"))
        agent = self.agent(provider, browser=ScreenshotBrowser(), vision=True, max_image_requests=2)
        (self.log.directory / "screen.png").write_bytes(PNG)
        with self.assertRaisesRegex(RunError, "image-request budget"):
            agent.run("Observe the browser")
        counts = [sum("inlineData" in part for item in history for part in item["parts"]) for history in provider.received]
        self.assertEqual(counts, [0, 1, 1])
        self.assertEqual(agent.image_requests, 2)
        self.assertNotIn(base64.b64encode(PNG).decode(), self.log.events.read_text())

    def test_default_run_continues_beyond_previous_request_step_and_image_caps(self):
        class ScreenshotBrowser:
            revision = 0
            restored_observation = None
            def execute(inner, name, arguments):
                return {"ok": True, "screenshot": "screen.png", "image_width": 1, "image_height": 1}
        provider = Script(*[call("browser_observe") for _ in range(45)],
                          call("report_blocker", message="Observed the configured test sequence", evidence_steps=[45]))
        agent = self.agent(provider, browser=ScreenshotBrowser(), vision=True)
        (self.log.directory / "screen.png").write_bytes(PNG)
        outcome = agent.run("Observe the complete test sequence")
        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(agent.requests, 46)
        self.assertEqual(agent.steps, 46)
        self.assertEqual(agent.image_requests, 45)
