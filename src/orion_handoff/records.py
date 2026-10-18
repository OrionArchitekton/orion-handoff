"""Record bytes and domain errors; no ambient state or external reference access."""
from datetime import datetime, timezone
import copy
import json
import re
import uuid

MAX_BYTES = 65536
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z", re.ASCII)
FIELDS = {"record_version", "task_key", "predecessor", "project_key", "title", "status",
          "actor", "request_id", "context_as_of", "last_observed_outcome", "unfinished_step",
          "recorded_next_step", "remaining_authority", "acceptance_claims", "evidence", "body"}


class Fault(Exception):
    def __init__(self, code, exit_status, data=None):
        super().__init__(code)
        self.code = code
        self.exit_status = exit_status
        self.data = data


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def bounded_depth(text):
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 8:
                raise ValueError("nesting limit")
        elif char in "]}":
            depth -= 1


def reject_constant(value):
    raise ValueError("non-finite number")


def decode(raw):
    try:
        if len(raw) > MAX_BYTES:
            raise ValueError
        text = raw.decode("utf-8")
        bounded_depth(text)
        result = json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Fault("invalid_input", 65) from exc


def valid_id(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
        return parsed.version == 4 and str(parsed) == value
    except ValueError:
        return False


def time_value(value):
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise ValueError("timestamp")
    # fromisoformat normalizes e.g. +00:60; validate the wire grammar first.
    if value[-1] != "Z" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("timestamp offset")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def text(value, limit, nullable=False, narrative=False, empty=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or len(value.encode("utf-8")) > limit:
        raise ValueError("text")
    if not empty and not value.strip():
        raise ValueError("blank text")
    if any((ord(c) < 32 or 127 <= ord(c) <= 159)
           and not (narrative and c in "\n\t") for c in value):
        raise ValueError("control character")


def normalize_time(value):
    return None if value is None else stamp(time_value(value))


def validate(value, stored=False):
    """Validate and normalize a complete value, never infer missing fields."""
    try:
        result = copy.deepcopy(value)
        expected = FIELDS | ({"record_id", "created_at"} if stored else set())
        if not isinstance(result, dict) or set(result) != expected:
            raise ValueError("shape")
        if type(result["record_version"]) is not int or result["record_version"] != 1:
            raise ValueError("record version")
        if result["status"] not in ("active", "stale", "done"):
            raise ValueError("status")
        for key, limit in (("task_key", 128), ("title", 256), ("actor", 128)):
            text(result[key], limit)
        for key, limit in (("project_key", 256), ("request_id", 128)):
            text(result[key], limit, nullable=True)
        if result["predecessor"] is not None and not valid_id(result["predecessor"]):
            raise ValueError("predecessor")
        result["context_as_of"] = normalize_time(result["context_as_of"])
        for key in ("last_observed_outcome", "unfinished_step", "recorded_next_step",
                    "remaining_authority"):
            text(result[key], 2048, nullable=True, narrative=True)
        text(result["body"], 16384, narrative=True, empty=True)
        claims = result["acceptance_claims"]
        if not isinstance(claims, list) or len(claims) > 8:
            raise ValueError("claims")
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {"baseline", "reference", "accepted_at"}:
                raise ValueError("claim shape")
            text(claim["baseline"], 1024, nullable=True)
            text(claim["reference"], 1024, nullable=True)
            claim["accepted_at"] = normalize_time(claim["accepted_at"])
        evidence = result["evidence"]
        if not isinstance(evidence, list) or len(evidence) > 16:
            raise ValueError("evidence")
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {
                    "source", "artifact", "observed_at", "scope", "reference"}:
                raise ValueError("evidence shape")
            for key, limit in (("source", 256), ("scope", 1024), ("reference", 1024)):
                text(item[key], limit)
            text(item["artifact"], 256, nullable=True)
            item["observed_at"] = normalize_time(item["observed_at"])
        if stored:
            if not valid_id(result["record_id"]) or result["created_at"] is None:
                raise ValueError("generated fields")
            result["created_at"] = normalize_time(result["created_at"])
        if len(encode(result)) > MAX_BYTES:
            raise ValueError("encoded size")
        return result
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError) as exc:
        raise Fault("store_invalid" if stored else "invalid_input", 74 if stored else 65) from exc
