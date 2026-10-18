"""The sole public seam. References and recorded next steps are never executed."""
import argparse
import json
import os
import sys

from . import __version__
from .context import pickup, provisional
from .records import Fault, MAX_BYTES, decode, validate
from .store import Store, initialize, path_parts, supported

NOTICE = "Unverified handoff data; current request and executor authority must be checked."


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Fault("usage", 2)


def parser():
    p = Parser(prog="orion-handoff", allow_abbrev=False)
    p.add_argument("--store")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", action="store_true")
    commands = p.add_subparsers(dest="command")
    commands.add_parser("init", allow_abbrev=False)
    record = commands.add_parser("record", allow_abbrev=False)
    record.add_argument("--input", required=True, choices=["-"])
    show = commands.add_parser("show", allow_abbrev=False)
    show.add_argument("record_id")
    listing = commands.add_parser("list", allow_abbrev=False)
    listing.add_argument("--task")
    listing.add_argument("--limit", type=int, default=20)
    pick = commands.add_parser("pickup", allow_abbrev=False)
    selectors = pick.add_mutually_exclusive_group()
    selectors.add_argument("--task")
    selectors.add_argument("--project")
    pick.add_argument("--resume", action="store_true")
    pick.add_argument("--max-age-seconds", type=int, default=86400)
    return p


def envelope(command, code, data, status=0, warnings=None):
    return {"interface_version": 1, "command": command, "ok": status == 0,
            "code": code, "data": data, "warnings": warnings or [],
            "authority": "none", "notice": NOTICE}


def render(result, json_mode):
    if json_mode:
        parts, total = [], 1
        for part in json.JSONEncoder(ensure_ascii=False).iterencode(result):
            raw = part.encode("utf-8")
            total += len(raw)
            if total > 524288:
                raise Fault("output_limit", 74)
            parts.append(raw)
        return b"".join(parts) + b"\n"
    lines = [NOTICE, "authority: none", "result: " + result["code"]]
    data = result["data"]
    if isinstance(data, dict):
        for key in ("match", "integrity", "recency", "acceptance", "disposition", "reasons"):
            if key in data:
                lines.append(key + ": " + json.dumps(data[key], ensure_ascii=True))
        record = data.get("record")
        if record:
            for key in ("task_key", "record_id", "title", "status", "actor", "context_as_of",
                        "last_observed_outcome", "unfinished_step", "recorded_next_step",
                        "remaining_authority", "acceptance_claims", "evidence"):
                lines.append("recorded " + key + ": " + json.dumps(record[key], ensure_ascii=True))
            lines.append("body omitted; use --json for bounded full data")
        else:
            lines.append(json.dumps(data, ensure_ascii=True))
    if result["warnings"]:
        lines.append("warnings: " + json.dumps(result["warnings"]))
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > 32768:
        note = b"\nText output truncated; use --json for bounded data.\n"
        raw = raw[:32768 - len(note)] + note
    return raw


def execute(args):
    if args.version:
        if args.command is not None:
            raise Fault("usage", 2)
        return "version", {"package_version": __version__, "interface_version": 1,
                           "store_version": 1, "record_version": 1}, []
    if args.command is None:
        raise Fault("usage", 2)
    path = args.store if args.store is not None else os.environ.get("ORION_HANDOFF_STORE")
    if not path:
        raise Fault("usage", 2)
    supported()
    path_parts(path)
    if args.command == "list" and not 1 <= args.limit <= 50:
        raise Fault("usage", 2)
    if args.command == "pickup":
        if (not 1 <= args.max_age_seconds <= 2592000
                or args.resume != (args.project is not None)):
            raise Fault("usage", 2)
        if args.task is None and args.project is None:
            return "no_task_context", provisional("no_task_context", args.max_age_seconds), []
    if args.command == "init":
        initialized, warnings = initialize(path)
        return "initialized", {"initialized": initialized}, warnings
    value = (validate(decode(sys.stdin.buffer.read(MAX_BYTES + 1)))
             if args.command == "record" else None)
    with Store(path, write=args.command == "record") as store:
        if args.command == "record":
            return "recorded", store.record(value), store.warnings
        if args.command == "pickup":
            code, data = pickup(store.tips.values(), args.task, args.project, args.max_age_seconds)
            return code, data, store.warnings
        if args.command == "list":
            return "listed", store.list(args.task, args.limit), store.warnings
        return "shown", store.show(args.record_id), store.warnings


def main():
    command = None
    status = 0
    try:
        args = parser().parse_args()
        command = args.command
        if args.version and command is None:
            command = "version"
        code, data, warnings = execute(args)
        status = {"inspect_only": 10, "no_match": 11, "ambiguous": 11,
                  "no_task_context": 11}.get(code, 0)
        result = envelope(command, code, data, status=status, warnings=warnings)
    except Fault as exc:
        status = exc.exit_status
        data = exc.data
        if command == "pickup" and data is None:
            integrity = ("missing" if exc.code == "store_missing" else
                         "invalid" if exc.exit_status == 74 else "unknown")
            data = provisional(exc.code, args.max_age_seconds, integrity)
        result = envelope(command, exc.code, data, status)
    except Exception:
        status = 69
        data = provisional("unavailable", args.max_age_seconds) if command == "pickup" else None
        result = envelope(command, "unavailable", data, status)
    json_mode = "--json" in sys.argv[1:]
    try:
        raw = render(result, json_mode)
    except Fault as exc:
        status = exc.exit_status
        raw = render(envelope(command, exc.code, None, status), json_mode)
    try:
        while raw:
            count = os.write(sys.stdout.fileno(), raw)
            if count == 0:
                return 69
            raw = raw[count:]
    except OSError:
        return 69
    return status
