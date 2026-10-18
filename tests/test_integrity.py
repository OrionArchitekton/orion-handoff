import os
import json
from pathlib import Path
import subprocess
import sys
import uuid
import signal
import fcntl
import time
from concurrent.futures import ThreadPoolExecutor

from support import CLIBase, example


class Integrity(CLIBase):
    def test_incomplete_and_future_stores_are_never_repaired(self):
        self.store.mkdir(mode=0o700)
        self.assertEqual(self.result("init", expected=74)["code"], "store_incomplete")
        self.assertEqual(list(self.store.iterdir()), [])
        self.store.rmdir()
        self.initialize()
        marker = self.store / "store.json"
        marker.write_text('{"store_version":2,"record_version":1}')
        before = marker.read_bytes()
        result = self.result("record", "--input", "-", value=example(), expected=74)
        self.assertEqual(result["code"], "incompatible_version")
        self.assertEqual(marker.read_bytes(), before)
        self.assertEqual(list((self.store / "records").iterdir()), [])

    def test_oversized_record_and_control_bytes_are_not_parsed(self):
        self.initialize()
        first = self.record()
        path = self.stored_path(first["record_id"])
        path.write_bytes(b"x" * 65537)
        self.assertEqual(self.result("show", first["record_id"], expected=74)["code"], "limit_exceeded")

    def test_duplicate_root_and_predecessor_fork_are_invalid(self):
        self.initialize()
        first = self.record()
        row = json.loads(self.stored_path(first["record_id"]).read_text())
        duplicate_id = str(uuid.uuid4())
        duplicate = dict(row, record_id=duplicate_id)
        path = self.stored_path(duplicate_id)
        path.write_text(json.dumps(duplicate))
        path.chmod(0o600)
        self.assertEqual(self.result("list", expected=74)["code"], "store_invalid")
        duplicate["predecessor"] = first["record_id"]
        path.write_text(json.dumps(duplicate))
        self.result("list")
        fork_id = str(uuid.uuid4())
        fork = self.stored_path(fork_id)
        fork.write_text(json.dumps(dict(duplicate, record_id=fork_id)))
        fork.chmod(0o600)
        self.assertEqual(self.result("list", expected=74)["code"], "store_invalid")

    def test_lost_link_acknowledgement_is_unknown_and_inspectable(self):
        self.initialize()
        first = self.record()
        result = self.crash_writer("link_error_after_commit", example(predecessor=first["record_id"]))
        self.assertEqual(result.returncode, 74, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], "commit_unknown")
        self.assertTrue(self.result("show", payload["data"]["candidate_record_id"])["data"]["current"])

    def test_two_writers_cannot_replace_the_same_predecessor(self):
        self.initialize()
        first = self.record()
        value = example(predecessor=first["record_id"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.invoke, "record", "--input", "-", value=value)
                       for _ in range(2)]
            outcomes = [f.result() for f in futures]
        self.assertEqual(sorted(r.returncode for r in outcomes), [0, 73])
        self.assertEqual({json.loads(r.stdout)["code"] for r in outcomes}, {"recorded", "conflict"})
        self.assertEqual(self.result("list")["data"]["matching_total"], 2)

    def test_distinct_writers_and_readers_observe_complete_records(self):
        self.initialize()
        with ThreadPoolExecutor(max_workers=18) as pool:
            writers = [pool.submit(self.invoke, "record", "--input", "-", value=example("task-" + str(i)))
                       for i in range(16)]
            readers = [pool.submit(self.invoke, "list") for _ in range(2)]
            outcomes = [f.result() for f in writers]
            read_results = [f.result() for f in readers]
        self.assertEqual([r.returncode for r in outcomes], [0] * 16)
        self.assertTrue(all(r.returncode == 0 for r in read_results))
        ids = {json.loads(r.stdout)["data"]["record_id"] for r in outcomes}
        self.assertEqual(len(ids), 16)
        self.assertEqual(self.result("list")["data"]["matching_total"], 16)
        self.assertEqual(self.harness_snapshot(), self.before)

    def test_process_kill_at_publication_stages_preserves_prior_bytes(self):
        for stage, committed in [("partial_write", False), ("after_file_sync", False),
                                 ("after_link", True), ("after_directory_sync", True),
                                 ("before_ack", True)]:
            with self.subTest(stage=stage):
                self.store = self.root / ("store-" + stage)
                self.initialize()
                first = self.record()
                prior_bytes = self.stored_path(first["record_id"]).read_bytes()
                killed = self.crash_writer(stage, example(predecessor=first["record_id"]))
                self.assertEqual(killed.returncode, -signal.SIGKILL, killed.stdout + killed.stderr)
                self.assertEqual(self.stored_path(first["record_id"]).read_bytes(), prior_bytes)
                listing = self.result("list")
                self.assertEqual(listing["data"]["matching_total"], 2 if committed else 1)
                self.assertEqual(self.result("show", first["record_id"])["data"]["current"],
                                 not committed)
                if stage != "before_ack":
                    self.assertIn("pending_files_present", listing["warnings"])

    def test_forced_identifier_collision_preserves_existing_record(self):
        self.initialize()
        first = self.record()
        before = self.stored_path(first["record_id"]).read_bytes()
        collision = self.crash_writer("collision:" + first["record_id"], example("other"))
        self.assertEqual(collision.returncode, 73, collision.stdout + collision.stderr)
        self.assertEqual(json.loads(collision.stdout)["code"], "id_collision")
        self.assertEqual(self.stored_path(first["record_id"]).read_bytes(), before)
        self.assertEqual(len(list((self.store / "records").iterdir())), 1)

    def test_busy_lock_times_out_without_replacing_it(self):
        self.initialize()
        path = self.store / ".lock"
        inode = path.stat().st_ino
        with path.open("rb") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            start = time.monotonic()
            result = self.result("list", expected=73)
            self.assertGreaterEqual(time.monotonic() - start, 1.9)
            self.assertEqual(result["code"], "busy")
        self.assertEqual(path.stat().st_ino, inode)
        self.result("list")

    def test_unsafe_modes_symlink_fifo_and_hard_link_are_rejected(self):
        self.initialize()
        first = self.record()
        path = self.stored_path(first["record_id"])
        original = path.read_bytes()
        path.chmod(0o644)
        self.result("pickup", "--task", "alpha", expected=74)
        path.chmod(0o600)
        outside = self.root / "outside-sentinel"
        outside.write_bytes(b"outside sentinel")
        outside.chmod(0o600)
        path.unlink()
        path.symlink_to(outside)
        self.result("list", expected=74)
        self.assertEqual(outside.read_bytes(), b"outside sentinel")
        path.unlink()
        os.mkfifo(path, 0o600)
        self.result("list", expected=74)
        path.unlink()
        path.write_bytes(original)
        path.chmod(0o600)
        os.link(path, self.root / "unexpected-hardlink")
        self.assertEqual(self.result("list", expected=74)["code"], "store_unsafe")
        self.assertEqual(path.read_bytes(), original)

    def test_symlinked_store_and_ancestor_never_create_outside_files(self):
        outside = self.root / "outside-directory"
        outside.mkdir(mode=0o700)
        (outside / "sentinel").write_text("preserve")
        self.store.symlink_to(outside, target_is_directory=True)
        self.result("init", expected=74)
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["sentinel"])
        self.store.unlink()
        alias = self.root / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        self.store = alias / "new-store"
        self.result("init", expected=74)
        self.assertFalse((outside / "new-store").exists())

    def test_record_capacity_refuses_new_writes_without_deletion(self):
        self.initialize()
        first = self.record()
        template = json.loads(self.stored_path(first["record_id"]).read_text())
        for i in range(511):
            row = dict(template, task_key="synthetic-" + str(i), record_id=str(uuid.uuid4()))
            target = self.stored_path(row["record_id"])
            target.write_text(json.dumps(row))
            target.chmod(0o600)
        self.assertEqual(self.result("list", "--limit", "1")["data"]["matching_total"], 512)
        result = self.result("record", "--input", "-", value=example("over-limit"), expected=74)
        self.assertEqual(result["code"], "limit_exceeded")
        self.assertEqual(len(list((self.store / "records").iterdir())), 512)

    def test_directory_budget_reserves_publication_names(self):
        self.initialize()
        for _ in range(1024):
            pending = self.store / "records" / (".pending-" + str(uuid.uuid4()))
            pending.touch(mode=0o600)
        self.result("list")
        self.assertEqual(self.result("record", "--input", "-", value=example(), expected=74)
                         ["code"], "limit_exceeded")
        extra = self.store / "records" / (".pending-" + str(uuid.uuid4()))
        extra.touch(mode=0o600)
        self.assertEqual(self.result("list", expected=74)["code"], "limit_exceeded")

    def test_unsafe_filename_and_broken_chain_block_pickup(self):
        self.initialize()
        first = self.record()
        latest = self.record(example(predecessor=first["record_id"]))
        path = self.stored_path(latest["record_id"])
        damaged = json.loads(path.read_text())
        damaged["predecessor"] = str(uuid.uuid4())
        path.write_text(json.dumps(damaged))
        result = self.result("pickup", "--task", "alpha", expected=74)
        self.assertEqual(result["code"], "store_invalid")
        self.assertIsNone(result["data"]["continuation"])
    def crash_writer(self, stage, value):
        return subprocess.run([sys.executable, str(Path(__file__).with_name("crash_writer.py")),
                               stage, str(self.store)], input=json.dumps(value), text=True,
                              capture_output=True, cwd=self.scratch, env=self.env, timeout=10)

    def test_failed_sync_after_publication_reports_unknown_commit(self):
        self.initialize()
        first = self.record()
        result = self.crash_writer("sync_error", example(predecessor=first["record_id"]))
        self.assertEqual(result.returncode, 74, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], "commit_unknown")
        candidate = payload["data"]["candidate_record_id"]
        self.assertTrue(self.result("show", candidate)["data"]["current"])
        self.assertFalse(self.result("show", first["record_id"])["data"]["current"])

    def test_orphan_partial_file_is_ignored_and_reported(self):
        self.initialize()
        receipt = self.record()
        temporary = self.store / "records" / ".pending-01234567-89ab-4cde-8fab-0123456789ab"
        temporary.write_bytes(b'{"partial')
        temporary.chmod(0o600)
        picked = self.result("pickup", "--task", "alpha")
        self.assertEqual(picked["data"]["selected_record_id"], receipt["record_id"])
        self.assertEqual(picked["warnings"], ["pending_files_present"])
        self.assertTrue(temporary.exists())
        self.assertEqual(self.initialize()["warnings"], ["pending_files_present"])
