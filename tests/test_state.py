from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from unittest.mock import Mock, patch

from gemini import ProviderError
from harness import Agent, RunLog
from jobs import dispatch_due, enqueue, schedule_time
from main import main
from state import exclusive_lock, save_json
from test_agent import WorkspaceCase, Script, call
from tools import Toolbox


class StateTests(WorkspaceCase):
    def saved(self, log):
        return json.loads((log.directory / "checkpoint.json").read_text(encoding="utf-8"))

    def test_handoff_survives_new_agent_and_keeps_counters(self):
        first = self.agent(Script(call("ask_user", question="Which runtime?")), detach_on_handoff=True)
        outcome = first.run("Check runtime")
        self.assertEqual(outcome["status"], "waiting_for_input")
        state = self.saved(self.log)
        self.assertEqual(state["pending"]["arguments"]["question"], "Which runtime?")
        provider = Script(call("run_command", command="python_version"), call("finish", summary="Checked", evidence_steps=[2]))
        resumed = Agent(provider, Toolbox(self.workspace), RunLog.reopen(self.log.directory), announce=lambda line: None)
        outcome = resumed.run(state["task"], resume_state=state, answer="Python")
        self.assertEqual(outcome["requests"], 3)
        self.assertEqual(outcome["tokens"], 15)
        self.assertIn("Python", provider.received[0][0]["parts"][1]["text"])
        self.assertEqual(self.saved(self.log)["status"], "succeeded")

    def test_uncertain_write_requires_note_and_is_not_replayed(self):
        first = self.agent(Script(call("write_file", path="out.txt", content="once")))
        original = self.tools.write_file
        def interrupted(**kwargs):
            original(**kwargs)
            raise KeyboardInterrupt()
        with patch.object(self.tools, "write_file", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            first.run("Create out.txt")
        state = self.saved(self.log)
        self.assertEqual(state["pending"]["name"], "write_file")
        with self.assertRaisesRegex(ValueError, "note"):
            Agent(Script(), Toolbox(self.workspace), self.log).run(state["task"], resume_state=state)
        provider = Script(call("read_file", path="out.txt"), call("finish", summary="Verified", evidence_steps=[2]))
        tools = Toolbox(self.workspace)
        with patch.object(tools, "write_file") as write:
            result = Agent(provider, tools, self.log, announce=lambda line: None).run(state["task"], resume_state=state,
                                                                                     note="File exists; inspect before acting")
        write.assert_not_called()
        self.assertEqual(result["verified_files"], ["out.txt"])
        self.assertEqual((self.workspace / "out.txt").read_text(), "once")

    def test_provider_failure_keeps_completed_tool_and_written_files(self):
        class FailAfterWrite(Script):
            def generate(inner, *args):
                if inner.received:
                    raise ProviderError("429")
                return super().generate(*args)
        with self.assertRaises(ProviderError):
            self.agent(FailAfterWrite(call("write_file", path="out.txt", content="saved"))).run("Write out.txt")
        state = self.saved(self.log)
        self.assertIsNone(state["pending"])
        self.assertEqual(state["written"], ["out.txt"])
        provider = Script(call("read_file", path="out.txt"), call("finish", summary="Done", evidence_steps=[2]))
        outcome = Agent(provider, Toolbox(self.workspace), self.log, announce=lambda line: None).run(state["task"], resume_state=state)
        self.assertEqual(outcome["requests"], 4)

    def test_cli_resume_uses_saved_config_and_handoff(self):
        provider = Script(call("ask_user", question="Which runtime?"))
        with patch("main.ROOT", self.root), patch("main.Gemini", return_value=provider), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["run", "Check runtime", "--detach-on-handoff", "--min-request-interval", "0",
                                   "--max-run-tokens", "5", "--max-requests", "1", "--max-steps", "1",
                                   "--max-image-requests", "1"]), 0)
        directory = next((self.root / "runs").iterdir())
        provider = Script(call("run_command", command="python_version"), call("finish", summary="Checked", evidence_steps=[2]))
        with patch("main.ROOT", self.root), patch("main.Gemini", return_value=provider), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["resume", directory.name, "--answer", "Python", "--max-run-tokens", "unlimited",
                                   "--max-requests", "unlimited", "--max-steps", "0", "--max-image-requests", "unlimited"]), 0)
        state = json.loads((directory / "checkpoint.json").read_text())
        self.assertEqual(state["status"], "succeeded")
        config = json.loads((directory / "config.json").read_text())
        for name in ("max_run_tokens", "max_requests", "max_steps", "max_image_requests"):
            self.assertEqual(config[name], 0)
        self.assertEqual(len(list((self.root / "runs").iterdir())), 1)

    def test_lock_excludes_another_owner_and_releases(self):
        path = self.root / "run.lock"
        with exclusive_lock(path):
            with self.assertRaisesRegex(ValueError, "Another process"):
                with exclusive_lock(path):
                    self.fail("Lock allowed concurrent execution")
        with exclusive_lock(path):
            pass

    def test_resume_discards_old_evidence_and_preserves_skill(self):
        (self.workspace / "source.txt").write_text("original")
        skill = {"name": "test", "content": "Keep source text unchanged", "sha256": "fixture"}
        first = self.agent(Script(call("read_file", path="source.txt"), call("ask_user", question="Continue?")),
                           detach_on_handoff=True, skill=skill)
        first.run("Read source")
        state = self.saved(self.log)
        (self.workspace / "source.txt").write_text("changed")
        provider = Script(call("finish", summary="Old evidence", evidence_steps=[1]),
                          call("read_file", path="source.txt"), call("finish", summary="Fresh evidence", evidence_steps=[4]))
        outcome = Agent(provider, Toolbox(self.workspace), self.log, skill=state["skill"], announce=lambda line: None).run(
            state["task"], resume_state=state, answer="Yes")
        self.assertEqual(outcome["summary"], "Fresh evidence")
        failed_finish = provider.received[1][-1]["parts"][0]["functionResponse"]["response"]
        self.assertFalse(failed_finish["ok"])
        self.assertIn(skill["content"], provider.instructions[0])


class JobTests(WorkspaceCase):
    def test_time_requires_offset_and_overdue_jobs_are_marked_missed(self):
        with self.assertRaisesRegex(ValueError, "offset"):
            schedule_time("2030-01-01T10:00:00")
        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        with patch("jobs.utc_now", return_value=now):
            job = enqueue(self.root, {"task": "test"}, at=(now + timedelta(seconds=10)).isoformat(), max_lateness=5)
        execute = Mock()
        with patch("jobs.utc_now", return_value=now + timedelta(seconds=16)):
            dispatch_due(self.root, execute)
        execute.assert_not_called()
        saved = json.loads((self.root / "jobs" / f"{job['id']}.json").read_text())
        self.assertEqual(saved["status"], "missed")

    def test_scheduled_job_dispatches_once(self):
        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        with patch("jobs.utc_now", return_value=now):
            enqueue(self.root, {"task": "test"}, at=(now + timedelta(seconds=10)).isoformat())
        def complete(config, log):
            log.result({"status": "succeeded"})
            return 0
        execute = Mock(side_effect=complete)
        with patch("jobs.utc_now", return_value=now + timedelta(seconds=10)):
            dispatch_due(self.root, execute)
            dispatch_due(self.root, execute)
        execute.assert_called_once()

    def test_file_event_and_interrupted_job_are_not_replayed(self):
        marker = self.root / "trigger.ready"
        job = enqueue(self.root, {"task": "fixed task"}, event_file=marker)
        execute = Mock(side_effect=KeyboardInterrupt)
        dispatch_due(self.root, execute)
        execute.assert_not_called()
        marker.write_text("This content is deliberately not used as instructions")
        with self.assertRaises(KeyboardInterrupt):
            dispatch_due(self.root, execute)
        dispatch_due(self.root, execute)
        execute.assert_called_once()
        saved = json.loads((self.root / "jobs" / f"{job['id']}.json").read_text())
        self.assertEqual(saved["status"], "interrupted")
        with self.assertRaisesRegex(ValueError, "already exists"):
            enqueue(self.root, {}, event_file=marker)

    def test_cleanup_failure_does_not_mark_job_succeeded(self):
        marker = self.root / "cleanup.ready"
        job = enqueue(self.root, {"task": "test"}, event_file=marker)
        marker.touch()
        def fail_after_task(config, log):
            log.result({"status": "succeeded"})
            return 1
        dispatch_due(self.root, fail_after_task)
        saved = json.loads((self.root / "jobs" / f"{job['id']}.json").read_text())
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["exit_code"], 1)

    def test_cli_event_worker_runs_saved_task_without_model_at_enqueue(self):
        marker = self.root / "trigger.ready"
        with patch("main.ROOT", self.root), patch("main.Gemini") as provider, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["on-event", "Check Python", "--event-file", str(marker), "--min-request-interval", "0"]), 0)
        provider.assert_not_called()
        marker.touch()
        provider = Script(call("run_command", command="python_version"), call("finish", summary="Checked", evidence_steps=[1]))
        with patch("main.ROOT", self.root), patch("main.Gemini", return_value=provider), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["worker", "--once"]), 0)
        job = json.loads(next((self.root / "jobs").glob("*.json")).read_text())
        self.assertEqual(job["status"], "succeeded")
