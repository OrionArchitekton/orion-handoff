---
verified: 2026-10-17
review_after: 2026-11-17
topics:
  - orion-handoff
  - private-extraction
  - local-store-recovery
references:
  - ../../specs/orion-handoff-core-spec.md
  - ../../README.md
  - ../../RELEASE_CHECKLIST.md
---

# Local handoff core: operator runbook

The installed CLI has passed isolated synthetic conformance. Published checksums bind the release artifacts; validation covers CPython 3.11 and 3.13 on WSL2 Linux x86_64/ext4. Select a new user-owned store for a trial. This runbook neither installs native hooks nor migrates existing handoffs.

## Rollout and isolated use

Use an owned scratch parent, a fresh virtual environment and a new explicit store. Record the artifact digest and interpreter/filesystem combination before use. Install the reviewed wheel into that environment; verify `orion-handoff --version` before selecting state. Installation/help/import must create no handoff store or harness integration.

Example flow for this candidate, one invocation at a time:

```text
orion-handoff --store /owned/scratch/sample-handoff --json init
orion-handoff --store /owned/scratch/sample-handoff --json record --input -
orion-handoff --store /owned/scratch/sample-handoff --json list --task sample-task-alpha
orion-handoff --store /owned/scratch/sample-handoff --json pickup --task sample-task-alpha
orion-handoff --store /owned/scratch/sample-handoff --json show FULL_RECORD_ID
```

The `record` invocation receives the reviewed synthetic JSON on stdin; reference strings are not opened. The [example input](../../examples/record-input.json) has fixed historical times and will naturally age. For a fresh demonstration, the producer must supply its actual observation time. Changing a timestamp is not a way to reverify old work. Copy a **complete** successor input and set predecessor to the observed current record ID when revising; there is no patch inheritance or status mutation command.

## Validation and monitoring

Check parsed JSON and exit status together. Exit 0 only establishes its named operation; context_available remains unverified. Inspect-only (10), no-match/ambiguity (11), conflict/busy (73) and integrity/unknown commit (74) are intentional distinct outcomes. No hook-compatible fail-open mode is provided.

Observe current record IDs, chain integrity, record count, selected-task dimensions and warnings through the CLI. No background monitor is installed. Listing is bounded and reports truncation; it is not a complete export when truncated. A store limit refuses new writes and never triggers deletion. Null/future observations and unchecked references remain review work.

## Backup and restore

1. Stop all cooperating producers and readers for the selected synthetic/user-owned store. A filesystem copy during active publication is not the supported backup procedure.
2. Copy the complete selected store, including version marker and empty lock file, with modes preserved into a new private directory. Do not follow symlinks; unsafe objects require inspection. Backup access must remain restricted to the owner. Preserve hard links if present; otherwise validate the restored structure before use.
3. Record original record byte hashes and the complete expected record count (at most 512). Preserve temporary files as evidence; never silently discard them in backup.
4. Restore to a fresh explicit path on a supported local filesystem. Verify ownership/modes, compatible versions and all expected IDs/hashes, then inspect current context through the reviewed CLI. Keep the original untouched until this comparison succeeds.
5. Re-enable only the selected cooperating users/processes. Native estate hooks are not part of this core procedure.

No command writes another tool's private state. The core does not search for a backup, import old Markdown packs or select a “nearest” compatible record automatically.

## Failure and recovery decisions

| Observation | Action |
|---|---|
| Conflict | Inspect current record. Reconcile the whole successor deliberately; do not automatically replace the winning context. |
| Busy | Check live cooperating processes. Retry after the holder exits; never delete or recreate the lock file to break a lock. |
| Commit unknown / writer killed without receipt | Preserve output if present, inspect candidate ID and current task chain. Compare committed content with intended input before deciding on any new successor. Unlock/close acknowledgement errors after attempted publication also return `commit_unknown` (74) with the candidate ID. Never infer that exit 74 means nothing was written, and never blindly resend. |
| Recognized orphan temporary warning | Stop writers, back up the whole store, inspect final ID/inode relationships. Remove only specifically identified orphan names after verifying committed record integrity; this manual cleanup is not an automatic core command. Keep the backup. |
| Incomplete initialization | Preserve the incomplete directory for inspection. Select a fresh empty store path for a retry; do not initialize over unknown files. |
| Corrupt/unsafe/over-limit store | Stop writes and preserve evidence. Inspect a known compatible backup in a fresh path; do not delete an inconvenient record to make pickup look healthy. |
| Incompatible version | Use the matching reviewed artifact against a copy, or restore its matching backup. No automatic downgrade/migration. |
| Unsupported filesystem | Select a newly initialized store on a tested local filesystem; moving production state is a separate backed-up operation. |

## Retention and removal

v0.1 retains every committed record, including stale/done/historical revisions, until the operator explicitly disposes of the selected store outside the CLI. There is no sweep, scheduled cleanup or auto-expiry deletion. Near capacity, preserve/retire a complete store and deliberately begin a new one; previous task context is not implicitly carried across. A future archive/import feature needs its own spec and lineage proof.

Uninstall removes package files from the selected environment, preserving the store. To undo the isolated trial, stop its processes, preserve receipts/backup, uninstall or remove only the owned test environment, and remove only the explicitly owned synthetic store if no longer wanted. Never use recursive cleanup against `.orion`, `.claude` or `.codex`.

## Limits of rollback

At the first public version there is no previous public artifact to downgrade to. Recovery means reinstalling the exact reviewed artifact, selecting a validated backup/copy, or removing the isolated trial. Later upgrades must declare store compatibility and add actual upgrade/downgrade proof. Publication rollback and users' installed copies are separate from local store restore; future release notes must explain both.

No estate adoption is performed by a package release. An eventual adapter migration needs a fresh inventory, explicit activation and reversal instructions, authority checks, native binding proof and a separate approval checkpoint.
