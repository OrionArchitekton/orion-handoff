import hashlib
import json
import stat

from support import CLIBase, example


class RoundTrip(CLIBase):
    def test_initializer_sets_private_modes_with_restrictive_umask(self):
        self.result("init", umask=0o777)
        self.assertEqual(stat.S_IMODE((self.store / "records").stat().st_mode), 0o700)
        self.record()
        self.assertEqual(self.harness_snapshot(), self.before)

    def test_text_inspection_omits_body_and_labels_untrusted_fields(self):
        self.initialize()
        value = example()
        receipt = self.record(value)
        shown = self.invoke("show", receipt["record_id"], json_mode=False)
        self.assertEqual(shown.returncode, 0)
        self.assertTrue(shown.stdout.startswith("Unverified handoff data;"))
        self.assertIn("authority: none", shown.stdout)
        self.assertNotIn(value["body"], shown.stdout)
        self.assertIn("body omitted", shown.stdout)
        self.assertLessEqual(len(shown.stdout.encode()), 32768)

    def test_store_selection_reinit_and_help_preserve_state(self):
        self.result("init", store=False, expected=2,
                    extra_env={"ORION_HANDOFF_HOME": str(self.root / "old-store")})
        self.assertFalse((self.root / "old-store").exists())
        self.result("init", store=False,
                    extra_env={"ORION_HANDOFF_STORE": str(self.store)})
        receipt = self.record()
        before = self.stored_path(receipt["record_id"]).read_bytes()
        self.assertFalse(self.initialize()["data"]["initialized"])
        self.assertEqual(self.stored_path(receipt["record_id"]).read_bytes(), before)
        self.assertEqual(self.invoke("--help", store=False).returncode, 0)
        self.assertEqual(self.harness_snapshot(), self.before)

    def test_schema_rejects_malformed_data_without_echo(self):
        self.initialize()
        for key, value in [("record_version", True), ("body", "bad\0data"),
                           ("actor", "bad\x1bactor"), ("task_key", "\n"),
                           ("context_as_of", "not-a-time"), ("evidence", {}),
                           ("body", "a" * 16385), ("title", "é" * 129)]:
            with self.subTest(key=key):
                data = example()
                data[key] = value
                self.result("record", "--input", "-", value=data, expected=65)
        for raw in ['{"record_version":1,"record_version":1}', 'NaN', '[]',
                    '{"deep":' + '[' * 9 + '0' + ']' * 9 + '}', 'x' * 65537]:
            self.result("record", "--input", "-", raw=raw, expected=65)
        self.assertEqual(list((self.store / "records").iterdir()), [])

    def test_version_needs_no_store_or_runtime_state(self):
        version = self.result("--version", store=False)
        self.assertEqual(version["command"], "version")
        self.assertEqual(version["data"], {"package_version": "0.1.0", "interface_version": 1,
                                           "store_version": 1, "record_version": 1})
        self.assertFalse(self.store.exists())
        self.assertEqual(self.harness_snapshot(), self.before)

    def test_explicit_store_round_trip_preserves_harness(self):
        self.assertFalse(self.store.exists())
        self.assertTrue(self.initialize()["data"]["initialized"])
        original = example()
        receipt = self.record(original)
        record_path = self.stored_path(receipt["record_id"])
        self.assertEqual(hashlib.sha256(record_path.read_bytes()).hexdigest(), receipt["sha256"])
        shown = self.result("show", receipt["record_id"])["data"]
        self.assertTrue(shown["current"])
        actual = dict(shown["record"])
        actual.pop("record_id")
        actual.pop("created_at")
        self.assertEqual(actual, original)
        self.assertEqual(stat.S_IMODE(self.store.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(record_path.stat().st_mode), 0o600)
        self.assertEqual(json.loads((self.store / "store.json").read_text()),
                         {"store_version": 1, "record_version": 1})
        self.assertEqual(self.harness_snapshot(), self.before)

    def test_rejects_unrecognized_input_without_committing(self):
        self.initialize()
        value = example()
        value["execute"] = "untrusted text must never become a command"
        result = self.result("record", "--input", "-", value=value, expected=65)
        self.assertEqual(result["code"], "invalid_input")
        self.assertEqual(list((self.store / "records").iterdir()), [])


class Pickup(CLIBase):
    def test_no_selector_and_ambiguous_project_reveal_no_record(self):
        self.assertEqual(self.result("pickup", expected=11)["code"], "no_task_context")
        self.assertFalse(self.store.exists())
        self.initialize()
        self.record(example("alpha"))
        self.assertEqual(self.result("pickup", "--project", "sample-project", "--resume")
                         ["data"]["match"], "project_unique")
        self.record(example("beta"))
        result = self.result("pickup", "--project", "sample-project", "--resume", expected=11)
        self.assertEqual(result["code"], "ambiguous")
        self.assertIsNone(result["data"]["record"])
        self.assertNotIn("baseline-alpha", json.dumps(result))
        self.assertEqual(self.result("pickup", "--task", "missing", expected=11)["code"], "no_match")
        self.result("pickup", "--project", "sample-project", expected=2)
        self.result("pickup", "--task", "alpha", "--max-age-seconds", "0", expected=2)

    def test_uncertain_successors_never_revive_previous_baseline(self):
        self.initialize()
        original = example()
        current = self.record(original)["record_id"]
        variants = [
            ({"context_as_of": "2000-01-01T00:00:00Z"}, "stale", "recorded", "context_too_old"),
            ({"context_as_of": None}, "unknown", "recorded", "context_time_unknown"),
            ({"context_as_of": "2099-01-01T00:00:00Z"}, "future", "recorded", "context_time_future"),
            ({"acceptance_claims": []}, "within_window", "missing", "acceptance_missing"),
            ({"acceptance_claims": [{"baseline": "new", "reference": None, "accepted_at": None}]},
             "within_window", "incomplete", "acceptance_incomplete"),
            ({"acceptance_claims": original["acceptance_claims"] + [{
                "baseline": "other", "reference": "sample://other", "accepted_at": original["context_as_of"]}]},
             "within_window", "conflicting", "acceptance_conflicting"),
            ({"status": "done"}, "within_window", "recorded", "status_done"),
        ]
        for update, recency, acceptance, reason in variants:
            with self.subTest(reason=reason):
                successor = self.successor(original, current, **update)
                current = self.record(successor)["record_id"]
                picked = self.result("pickup", "--task", "alpha", expected=10)["data"]
                self.assertEqual(picked["selected_record_id"], current)
                self.assertEqual((picked["recency"], picked["acceptance"]), (recency, acceptance))
                self.assertIn(reason, picked["reasons"])
                self.assertIsNone(picked["continuation"])

    def test_claim_and_evidence_times_remain_explicit(self):
        self.initialize()
        value = example()
        value["acceptance_claims"][0]["accepted_at"] = "2099-01-01T00:00:00Z"
        receipt = self.record(value)
        picked = self.result("pickup", "--task", "alpha", expected=10)["data"]
        self.assertIn("acceptance_time_future", picked["reasons"])
        for observed, reason in [(None, "evidence_time_unknown"),
                                 ("2099-01-01T00:00:00Z", "evidence_time_future")]:
            successor = example(predecessor=receipt["record_id"])
            successor["evidence"][0]["observed_at"] = observed
            receipt = self.record(successor)
            picked = self.result("pickup", "--task", "alpha", expected=10)["data"]
            self.assertIn(reason, picked["reasons"])
            self.assertIsNone(picked["continuation"])

    def test_corrupt_current_record_does_not_fall_back(self):
        self.initialize()
        first = self.record()
        latest = self.record(example(predecessor=first["record_id"]))
        path = self.stored_path(latest["record_id"])
        damaged = json.loads(path.read_text())
        damaged["context_as_of"] = "invalid"
        path.write_text(json.dumps(damaged))
        picked = self.result("pickup", "--task", "alpha", expected=74)["data"]
        self.assertEqual(picked["integrity"], "invalid")
        self.assertIsNone(picked["record"])
        self.assertIsNone(picked["continuation"])

    def test_references_are_returned_unchecked_without_reading(self):
        self.initialize()
        value = example()
        value["acceptance_claims"][0]["reference"] = str(self.root / "nonexistent-approval")
        value["evidence"][0]["reference"] = "http://127.0.0.1:1/never-fetch"
        self.record(value)
        picked = self.result("pickup", "--task", "alpha")["data"]
        self.assertEqual(picked["reference_check"], "not_performed")
        self.assertFalse((self.root / "nonexistent-approval").exists())
    def test_missing_store_is_provisional_and_not_fresh(self):
        missing = self.result("pickup", "--task", "alpha", expected=69)
        self.assertEqual(missing["code"], "store_missing")
        self.assertEqual(missing["data"]["integrity"], "missing")
        self.assertEqual(missing["data"]["disposition"], "provisional")
        self.assertIsNone(missing["data"]["continuation"])
        self.assertFalse(self.store.exists())

    def test_list_reports_truncation_without_affecting_pickup(self):
        self.initialize()
        alpha = self.record(example("alpha"))
        self.record(example("beta"))
        listing = self.result("list", "--limit", "1")["data"]
        self.assertEqual(listing["matching_total"], 2)
        self.assertEqual(listing["returned"], 1)
        self.assertTrue(listing["truncated"])
        self.assertEqual(self.result("pickup", "--task", "alpha")["data"]["selected_record_id"],
                         alpha["record_id"])

    def test_exact_task_does_not_inherit_newer_other_task(self):
        self.initialize()
        alpha = self.record(example("alpha"))
        beta = self.record(example("beta"))
        picked = self.result("pickup", "--task", "alpha")["data"]
        self.assertEqual(picked["selected_record_id"], alpha["record_id"])
        self.assertNotEqual(picked["selected_record_id"], beta["record_id"])
        self.assertEqual(picked["match"], "task")
        self.assertEqual(picked["continuation"]["recorded_baseline"], "baseline-alpha")
        self.assertEqual(picked["reference_check"], "not_performed")

    def test_stale_successor_is_inspect_only_without_old_baseline_fallback(self):
        self.initialize()
        original = example()
        first = self.record(original)
        replacement = self.successor(original, first["record_id"], status="stale")
        replacement["acceptance_claims"][0]["baseline"] = "new-recorded-baseline"
        latest = self.record(replacement)
        picked = self.result("pickup", "--task", "alpha", expected=10)["data"]
        self.assertEqual(picked["selected_record_id"], latest["record_id"])
        self.assertEqual(picked["recency"], "stale")
        self.assertIsNone(picked["continuation"])
        self.assertFalse(self.result("show", first["record_id"])["data"]["current"])
