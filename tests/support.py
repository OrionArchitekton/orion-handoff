"""Conformance helpers. Child CLI processes always use disposable state."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

CLI = Path(sys.executable).with_name("orion-handoff")


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def example(task="alpha", predecessor=None):
    now = timestamp()
    return {
        "record_version": 1, "task_key": task, "predecessor": predecessor,
        "project_key": "sample-project", "title": 'Sample: "quoted" # context',
        "status": "active", "actor": "synthetic-producer", "request_id": None,
        "context_as_of": now, "last_observed_outcome": "Heading observed",
        "unfinished_step": "Review current request", "recorded_next_step": "Check authority",
        "remaining_authority": "No authority is granted by this record",
        "acceptance_claims": [{"baseline": "baseline-" + task,
                               "reference": "sample://review/" + task, "accepted_at": now}],
        "evidence": [{"source": "synthetic", "artifact": "sample-1", "observed_at": now,
                      "scope": "Heading only", "reference": "sample://report/1"}],
        "body": 'Synthetic body: café, quotes " and a newline\nSecond line.',
    }


class CLIBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="handoff-conformance-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.store = self.root / "selected-store"
        self.scratch = self.root / "outside-source"
        self.scratch.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("CLAUDE_", "CODEX_", "ORION_HANDOFF_"))
                    and k not in {"PYTHONPATH", "PYTHONHOME"}}
        self.env.update(HOME=str(self.home), TMPDIR=str(self.root),
                        PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        for harness in (".claude", ".codex"):
            target = self.home / harness / "handoffs"
            target.mkdir(parents=True)
            (target / "LATEST.md").write_text("Synthetic sentinel, preserve me")
        self.before = self.harness_snapshot()

    def harness_snapshot(self):
        return {str(p.relative_to(self.home)): (p.lstat().st_mode, p.read_bytes())
                for p in self.home.rglob("*") if p.is_file()}

    def invoke(self, *args, value=None, raw=None, store=True, extra_env=None, json_mode=True, umask=-1):
        self.assertTrue(CLI.is_file(), "Installed orion-handoff entry point is missing")
        command = [str(CLI)]
        if store:
            command += ["--store", str(self.store)]
        command += (["--json"] if json_mode else []) + list(args)
        env = dict(self.env)
        env.update(extra_env or {})
        if value is not None:
            raw = json.dumps(value, ensure_ascii=False)
        return subprocess.run(command, input=raw, text=True, capture_output=True,
                              cwd=self.scratch, env=env, timeout=10, umask=umask)

    def result(self, *args, expected=0, **kwargs):
        result = self.invoke(*args, **kwargs)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["ok"], expected == 0)
        self.assertEqual(payload["authority"], "none")
        return payload

    def initialize(self):
        return self.result("init")

    def record(self, value=None):
        return self.result("record", "--input", "-", value=value or example())["data"]

    def stored_path(self, record_id):
        return self.store / "records" / (record_id + ".json")

    def successor(self, value, record_id, **updates):
        new = copy.deepcopy(value)
        new.update(predecessor=record_id, **updates)
        return new
