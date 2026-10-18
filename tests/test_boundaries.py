"""Narrow deterministic seams: exact clock boundaries and unreachable output caps.

These import the installed package, never the source checkout. End-to-end CLI
tests remain the primary seam; no test clock or fault switch ships publicly.
"""
from datetime import datetime, timedelta, timezone
import unittest
import uuid

from orion_handoff.cli import envelope, render
from orion_handoff.context import assess
from orion_handoff.records import Fault, stamp, validate
from support import example


class DeterministicBoundaries(unittest.TestCase):
    def test_age_equality_microsecond_skew_and_unknown(self):
        evaluated = datetime(2026, 10, 17, 23, tzinfo=timezone.utc)
        value = example()
        value.update(record_id=str(uuid.uuid4()), created_at=stamp(evaluated - timedelta(seconds=1)))
        value["acceptance_claims"][0]["accepted_at"] = stamp(evaluated - timedelta(days=1))
        value["evidence"][0]["observed_at"] = stamp(evaluated - timedelta(days=1))
        for age, expected in [(timedelta(seconds=86400), "within_window"),
                              (timedelta(seconds=86400, microseconds=1), "stale"),
                              (timedelta(microseconds=-1), "future")]:
            value["context_as_of"] = stamp(evaluated - age)
            self.assertEqual(assess(validate(value, stored=True), 86400, evaluated)[0], expected)
        value["context_as_of"] = None
        self.assertEqual(assess(validate(value, stored=True), 86400, evaluated)[0], "unknown")

    def test_json_output_cap_refuses_partial_success(self):
        with self.assertRaises(Fault) as caught:
            render(envelope("list", "listed", {"oversized": "x" * 524288}), True)
        self.assertEqual(caught.exception.code, "output_limit")

    def test_text_output_cap_is_explicit(self):
        output = render(envelope("list", "listed", {"records": ["é" * 256] * 50}), False)
        self.assertLessEqual(len(output), 32768)
        self.assertIn(b"Text output truncated", output)
