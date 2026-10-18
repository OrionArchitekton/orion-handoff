# Orion Handoff

Carry bounded task context between local sessions. A producer records what it observed; another session selects the intended task and reviews what remains uncertain. Handoff data never grants permission to execute the next step.

**Version 0.1.0. MIT licensed.** The installed CLI is the supported interface; internal Python imports are not a public API.

## Install and select an isolated store

Use CPython 3.11 or 3.13 on Linux x86_64 and a supported local filesystem. Validation covers WSL2 with an ext4-backed store. Native Windows, Windows-mounted stores, network filesystems and cross-host writers are unsupported. Exact interpreter and artifact proof belongs in the release receipt.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install orion-handoff==0.1.0
.venv/bin/orion-handoff --json --version
.venv/bin/orion-handoff --store /absolute/owned/scratch/handoff-demo --json init
```

Select an existing writable parent and a new store path. Every stateful invocation requires `--store` or the new `ORION_HANDOFF_STORE` environment variable. There is no implicit home, and the private tool's `ORION_HANDOFF_HOME` is ignored. Package installation creates no store, hook, service or harness pointer.

For a complete wheel-only walkthrough with a synthetic generator and recovery checks, read the [guide](https://www.danmercede.com/guides/hand-off-local-agent-tasks).

## A two-session walkthrough

In the producer session, review `examples/record-input.json`. It is synthetic and has fixed historical times; supply actual observation times for a new demonstration. A new timestamp does not reverify an old result.

```sh
.venv/bin/orion-handoff --store /absolute/owned/scratch/handoff-demo --json record --input - < examples/record-input.json
```

In another session:

```sh
.venv/bin/orion-handoff --store /absolute/owned/scratch/handoff-demo --json pickup --task sample-task-alpha
.venv/bin/orion-handoff --store /absolute/owned/scratch/handoff-demo --json list --task sample-task-alpha
.venv/bin/orion-handoff --store /absolute/owned/scratch/handoff-demo --json show FULL_RECORD_ID
```

Task keys are explicit opaque identities. A project-resume selection needs exactly one current task; two tasks remain ambiguous even if one is newer, stale or done. Pickup with no selector returns provisional context without reading any records.

To revise a task, send a **complete** new input with `predecessor` set to its current record ID. All existing records remain immutable. A competing update returns conflict; inspect and reconcile rather than automatically overwriting it. Marking context stale or done is a successor record, not a PM task transition.

## Read results honestly

JSON reports task match, structural integrity, context recency, recorded acceptance and disposition separately. `context_available` remains unverified. `inspect_only` has a selected record but no usable continuation. Missing, ambiguous or invalid context stays provisional; there is no fallback to an older baseline.

Every result states `authority: none`. References, actor labels, acceptance claims, evidence and next steps are recorded data. References are never opened or fetched. Freshness describes the supplied observation time, not current source compatibility or permission. The core performs no network requests, subprocess actions, session/history reads or integration with another tool's private store.

| Exit | Meaning |
|---|---|
| 0 | Named operation established; no execution authority. |
| 2 | Usage/configuration error. |
| 10 | Matched context needs inspection. |
| 11 | Missing or ambiguous requested context. |
| 65 | Invalid submitted input; no record committed. |
| 69 | Store/platform/I/O unavailable. |
| 73 | Busy, predecessor conflict or ID collision. |
| 74 | Integrity/compatibility/budget failure or unknown commit. Inspect before retry. |

## Limits and recovery

Inputs and records are at most 64 KiB, the body at most 16 KiB, and a store retains at most 512 committed records. Reads are bounded and reject invalid stores rather than report partial selection as healthy. There is no automatic deletion, archive, import, migration or current-task pointer. A malformed committed record blocks selected pickup until an operator recovers the store.

Locks coordinate cooperative local clients. This is not authentication or protection from malicious same-user processes. Process-interruption tests do not establish physical power-loss behavior on every filesystem.

Read the [operator runbook](docs/runbooks/local-handoff-store.md) for stopped-writer backup, exact-store restore, unknown commits and retention. Uninstall preserves the store. The first version's recovery uses the exact artifact and matching backup; no prior public version exists to downgrade to.

## Contracts and development

- [Living implementation spec](specs/orion-handoff-core-spec.md)
- [Release checklist](RELEASE_CHECKLIST.md)
- [Security scope](SECURITY.md)
- [Contribution and test instructions](CONTRIBUTING.md)

The core has no runtime dependencies outside the Python standard library. PM, browser, phone, Remote Hands and vendor harness integrations are separate packages. An optional future starter profile needs exact component pins and its own combined proof. Releasing this package does not migrate an installed estate.

MIT. Copyright 2026 Dan Mercede.
