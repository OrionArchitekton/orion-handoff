# Orion Handoff core v0.1 implementation spec

Status: **accepted for private implementation; release acceptance pending**. Prepared 2026-10-17 Pacific. Proposed package version 0.1.0, interface version 1, store version 1, record version 1. On implementation, retain this living spec under the implementation repository's `specs/` directory.

## Outcome and vocabulary

A producer records the context of a local task. A later consumer selects the intended task, sees what was recorded and what remains uncertain, then obtains current authority through the actual executor before taking action. The newest unrelated context never silently becomes the requested task.

| Term | Meaning |
|---|---|
| Task key | Caller-supplied opaque identity, stable across revisions. May equal a PM task ID, but has no PM behavior. Replaces using a topic, title, repository or conversation ID as implicit task identity. |
| Handoff record | One immutable snapshot of a task's context. Replaces private “pack” as the public term. |
| Record ID | Generated opaque identity of one handoff record, distinct from task key and request ID. |
| Predecessor | The current record ID a producer explicitly replaces for that same task. It expresses ordering, not permission. |
| Project key | Optional opaque grouping label. No directory discovery or repository lookup follows from it. |
| Acceptance claim | Caller-recorded baseline, reference and time. It is unverified evidence about acceptance, never a grant of authority. |
| Context recency | Age of the caller's context observation; it is not source correctness, reference availability, authorization or git compatibility. |
| Actor label | Caller-supplied attribution, not authenticated identity. |

“Recorded baseline” is the canonical display term; it replaces “accepted baseline” in generated summaries. Raw acceptance claims preserve what a producer asserted without endorsing it.

## Scope and support target

The core installs a CLI, stores bounded records, inspects them and selects context. It performs no network requests, subprocess execution, hook installation, external store reads, git discovery, session/transcript extraction, PM operations, browser/phone actions, credential handling or approval decisions.

Target CPython 3.11 and 3.13 on Linux x86_64 using a local filesystem supporting POSIX advisory locks, same-filesystem atomic hard-link publication and file/directory synchronization. WSL2 with an ext4-backed store needs its own recorded proof; a Windows-mounted store, native Windows, NFS/SMB, cross-host writers and hostile same-user processes are unsupported. A platform rejection is explicit before store mutation. Filesystem eligibility is documented and tested on named environments; the CLI cannot certify every mount's crash semantics.

Runtime dependencies: Python standard library only. Packaging/build tooling is development-only and recorded separately. No daemon, scheduler, database service or shared SDK.

## Seam and evidence decision

The **installed CLI** is the sole supported public seam. Tests and callers cross the same interface. The implementation may use small internal modules; they do not become a public import contract.

The primary conformance suite invokes the executable from a fresh environment, outside the source tree, with a synthetic temporary home, explicit store, bounded stdin and captured JSON/exit status. It observes producer-to-consumer results and snapshots unrelated files. Real concurrent processes exercise contention. A narrow internal fault-injection seam targets publication stages that process scheduling cannot reliably target; exact microsecond clock boundaries and unreachable output-buffer caps use deterministic checks against installed internals. These are test seams only: no fault/clock flag or environment switch is shipped in the public executable, and no Python import API becomes supported.

One scenario is implemented RED→GREEN at a time. Each new test must first fail for the intended missing behavior. Do not generate the entire suite before implementation.

## CLI contract

Global flags precede the command: `orion-handoff [--store ABSOLUTE_PATH] [--json] COMMAND ...`. `--help` and `--version` need no store and have no side effects. `--version` names package/interface/store/record versions. The private executable `handoff` is not installed or replaced.

Store selection is CLI flag, then nonempty `ORION_HANDOFF_STORE`; otherwise usage error. Relative paths and symlinked store paths are rejected. No fallback to a default or to `ORION_HANDOFF_HOME`. All examples select a fresh explicit store. A relative command argument never changes the store selection.

| Command | Input and result | Mutation |
|---|---|---|
| `init` | Create a new owned store under an existing writable parent. Repeating on an intact compatible store is a no-op. Refuse an existing unrecognized/incomplete store, even if empty, and incompatible versions. | Selected store only; no parent creation or repair. |
| `record --input -` | Read one bounded JSON input object from stdin. Validate fully, enforce predecessor, generate ID/time and commit one record. Return ID, task key and SHA-256 of committed bytes. Only `-` is supported in v0.1; caller opens files explicitly. | Selected initialized store only. |
| `show RECORD_ID` | Exact full ID only. Return that record and computed metadata; inspect historical records without making them current. No prefix, path or topic lookup. | None. |
| `list [--task TASK_KEY] [--limit N]` | Return record summaries ordered by generated creation time then ID descending; default 20, range 1–50. Include `current` for each task, `returned`, `matching_total`, `truncated`. | None. |
| `pickup [--task TASK_KEY | --project PROJECT_KEY --resume] [--max-age-seconds N]` | Select current task context. Default age limit 86,400; integer range 1–2,592,000. Exact task or explicit project-resume intent only. | None. |

`pickup` without selectors returns provisional `no_task_context`, reading no records. Project selection without `--resume`, mutually exclusive selectors, unknown flags and invalid limits are usage errors. There is no prompt parsing, session environment inference or global “latest task” fallback.

`show`, `list` and selected `pickup` require an initialized store. They never bootstrap or create a lock file. `record` never implicitly initializes. No import, sweep, deletion, migration, global index, pointer or mutable status command ships in v0.1. To update status or notes, publish a complete successor with the explicit predecessor. Omitted prior content is deliberately not inherited.

## Input and stored record

`record` requires all keys below; nullable values are explicit. Unknown keys, duplicate JSON keys, non-object input, trailing JSON, non-finite numbers and incorrect types are rejected. Strings are UTF-8, without NUL. Identity/label/reference strings prohibit C0/C1 control characters; body and narrative strings permit tab/newline, but no other controls. Machine values are not silently truncated.

| Input key | Type and rules |
|---|---|
| `record_version` | Integer 1; booleans are not integers for validation. |
| `task_key` | Nonempty opaque string, at most 128 UTF-8 bytes. Never used as a path. |
| `predecessor` | Null for the first record of a task, otherwise a full record ID. |
| `project_key` | Null or nonempty opaque string, at most 256 bytes. Must equal the predecessor's project key on revision; regrouping is deferred. |
| `title` | Nonempty label, at most 256 bytes. |
| `status` | `active`, `stale` or `done`; describes context, not PM task state. A later explicit successor may change it. |
| `actor` | Nonempty attribution label, at most 128 bytes. |
| `request_id` | Null or opaque string, at most 128 bytes. Correlation only; not an idempotency key. |
| `context_as_of` | Null or RFC3339 timestamp with explicit timezone. Normalize valid timestamps to UTC. Null means unknown; future values remain visible. |
| `last_observed_outcome` | Null or narrative, at most 2,048 bytes. No automatic “verified” label. |
| `unfinished_step` | Null or narrative, at most 2,048 bytes. |
| `recorded_next_step` | Null or narrative, at most 2,048 bytes. Data for review; never executed. |
| `remaining_authority` | Null or narrative, at most 2,048 bytes. A producer's assertion only. |
| `acceptance_claims` | Array of 0–8 objects: `baseline`, `reference`, `accepted_at`, each nullable. Baseline/reference are nonempty strings when present, at most 1,024 bytes each; time follows timestamp rules. |
| `evidence` | Array of 0–16 objects, each containing exactly `source`, `artifact`, `observed_at`, `scope`, `reference`. Source/scope/reference are nonempty strings (256/1,024/1,024 bytes); artifact is null or nonempty string up to 256 bytes; observed_at is null or a timestamp. |
| `body` | Markdown text at most 16,384 UTF-8 bytes. Stored as data, never interpreted as instructions. |

The stored object adds exactly `record_id` and `created_at`, generated by the CLI. Record IDs are canonical lowercase UUID4 strings. Stored `created_at` is a UTC timestamp; it orders listing, not current-task selection or evidence recency. The stored JSON object is UTF-8, sorted keys, two-space indentation, non-ASCII characters emitted as UTF-8, final newline. Its hash covers these exact bytes. No private path or environment value is inserted automatically.

Accepted timestamps use `YYYY-MM-DDTHH:MM:SS` with optional 1–6 fractional digits and required `Z` or `+/-HH:MM` offset. Reject invalid calendar values, leap seconds, timezone-free values, non-string/non-null values and alternate ISO week/date-only spellings. Stored times normalize to UTC with a `Z` suffix, preserving available fractional precision to microseconds. A nonempty string must contain a non-whitespace character; opaque keys are compared exactly, without trimming, case folding or Unicode normalization.

An input cannot supply generated keys. A valid stored record must pass the same field checks plus generated-field checks. Malformed timestamps are invalid input, not null or “fresh”. Null time is valid unknown data. Future timestamps do not prove recency. Narrative can contain untrusted requests; the CLI never follows them.

## Store, revisions and local integrity

Store version 1 consists of `store.json` containing exactly `{"store_version":1,"record_version":1}`, one `.lock`, and `records/RECORD_ID.json` plus recognized temporary files. No latest pointer or separate current-task index is authoritative. All records of each task form one predecessor chain: exactly one root, existing same-task predecessor, at most one child per record, no cycles. A task's current record is its unique tip, independent of timestamp. Project key is constant along a chain.

For a new task, predecessor must be null. For an existing task, predecessor must be that task's current ID. Missing/wrong predecessors, cross-task predecessors or an attempt to create a second root fail with conflict and no mutation. Two writers revising the same predecessor cannot both succeed; one commits and the other receives conflict. Distinct tasks can both commit with distinct IDs.

Initialization requires a previously nonexistent final store directory or a complete compatible store. It creates a directory with mode 0700, then control files (0600) and the records directory (0700); publish the version marker last and synchronize it and its directory. Interrupted initialization is explicit `store_incomplete`, never silently adopted. Existing parents are not chmodded. Concurrent initializers may return busy/incomplete; retry only after inspecting the selected path. Never overwrite an existing foreign entry.

After exclusively creating the new initialization lock file, take its exclusive lock before completing initialization. For an existing complete store, use that pre-existing lock: exclusive for record publication, shared for validated read snapshots. A command waits at most 2 seconds using a monotonic deadline, then returns `busy`. Read locking changes no file content. Lock release follows descriptor lifetime, including process exit; no lock-file deletion is a recovery procedure.

Under exclusive lock, validate the bounded store and predecessor, create a new random-ID temporary file `.pending-RECORD_ID` with exclusive creation/mode 0600, write and fsync complete bytes, publish by atomic hard link to the final ID without overwrite, fsync the records directory, then remove the temporary name and sync the directory again. Retry a generated ID collision at most 3 times; never overwrite. Only final ID names are committed records. Readers under the shared lock never observe partial JSON. Before commit, reserve stdout receipt capacity as well as store capacity; after commit, preserve the candidate ID even if acknowledgement fails.

A crash before final publication leaves prior records unchanged and possibly a recognized orphan temporary file. A crash after publication can leave a committed record and its temporary hard link. Such temporary files are ignored as records, counted toward limits and reported as warnings, never silently cleaned. A failure after publication returns `commit_unknown` with the candidate ID if possible; consumer inspection precedes retry. A lost stdout acknowledgement also requires inspection. There is no exactly-once operation guarantee.

Validate owner UID and permissions, regular file type, expected link count, and containment with descriptor-relative operations and no-follow flags. Reject symlinks in the selected path, store internals and final records; reject FIFO/device/directory record entries without opening them as content. A final record may have two links only when its matching recognized temporary name names the same inode after interrupted publication; any other extra hard link is unsafe. The lock and version marker must have one link. Never chmod or repair unsafe existing objects automatically. Advisory locks and path checks protect cooperating local clients; they do not defend against malicious same-user mutation.

Before initialization, the final directory may be absent; its existing ancestors are traversed without following symlinks. Core writes remain beneath the selected store. Explicit CLI input comes from stdin; references and project labels are not opened. Package-install files and interpreter-owned files in an explicitly selected virtual environment are outside this runtime-store promise, and still must not touch harness settings.

## Bounded work and truthful failures

| Bound | v0.1 value |
|---|---|
| Stdin / committed record | 65,536 bytes each; read at most limit+1 to detect overflow. |
| Committed records | 512 per store, including historical revisions. |
| Directory enumeration | At most 1,024 entries under records, including temporary names; no recursion. |
| Aggregate committed bytes read | 33,554,432 per command. Validate length before parsing; stop on the first limit breach. |
| JSON nesting | At most 8 levels; reject excess before general JSON decoding can exhaust the stack. |
| JSON stdout | 524,288 bytes per invocation, including envelope and escaping. Build within a bounded buffer; output-limit errors emit no partial success JSON. |
| Text stdout | 32,768 bytes. Show full data through bounded JSON; text omits body by design. Escape terminal controls and visibly label omitted sections. |

Version marker is at most 256 bytes; lock content must be empty. Unknown store entries are rejected. Recognized temporary names are `.pending-UUID4` inside records and need matching strict shape, ownership/mode/type checks; their stat size must not exceed 65,536 bytes. They are not parsed as records. A store at record capacity remains inspectable but refuses further records; no auto-archive or deletion. At a directory, data-integrity or byte-budget breach, selection is incomplete: return error rather than a possibly wrong match. This conservatively blocks all selected-task pickup when any committed record cannot be validated; the bounded whole-store design accepts that tradeoff.

Check all budgets before mutation, reserving room for the pending and final names. All read operations take one consistent snapshot under the shared lock. Timestamp, reference, input, scan, permission, lock or decoding failures can never become a successful “fresh” result. Do not expose tracebacks or entire rejected payloads in normal errors.

## Pickup result and uncertainty

Every selected pickup reports these independent dimensions:

| Dimension | Values and interpretation |
|---|---|
| `match` | `task`, `project_unique`, `none`, `ambiguous`. Exact task keys only; project resume needs exactly one current task, including stale/done tasks. Do not filter away a competing task to invent uniqueness. |
| `integrity` | `valid`, `invalid`, `unknown`, `missing`. Valid means schema/chain checks passed, not that content is true. |
| `recency` | `within_window`, `stale`, `future`, `unknown`; accompanied by nullable `age_seconds`, observation time and configured limit. Use context_as_of, never created_at. |
| `acceptance` | `recorded`, `missing`, `incomplete`, `conflicting`. References always have `reference_check:"not_performed"`; no file existence or network test. |
| `disposition` | `context_available`, `inspect_only`, `provisional`. None grants execution authority. |

For a structurally valid current record, compute age as evaluation UTC time minus context_as_of without rounding before comparison. Null time means unknown, any positive future offset means future, age greater than limit means stale; equality is within_window. `status:stale` forces stale unless time is future/unknown, which remain explicit. `status:done` is inspection-only regardless of age. A timestamp that fails parsing makes the record invalid and blocks selected pickup; never fall back to a predecessor.

Acceptance is missing for no claims; incomplete when any claim lacks baseline/reference/accepted_at; conflicting when two complete claims have different (baseline, reference, normalized accepted_at) tuples; otherwise recorded. Conflict takes precedence over incomplete when both apply. Identical complete duplicates are harmless. Missing references are not repaired from older records. A reference that no longer resolves remains explicitly **unchecked**; core cannot claim its availability. A later authorized adapter may verify it independently without changing this record into permission.

`context_available` requires one matched task, valid integrity, current active record, within_window recency and recorded acceptance. Additionally, generated creation time and every claim time must not be future, and no submitted evidence time may be null or future; such limitations produce inspect_only with explicit reasons even while context recency remains within_window. An empty evidence array is permitted and visibly reported as `evidence_missing`; the core makes no independent evidence-validation claim. The result includes a `continuation` object with `recorded_baseline` and `recorded_next_step`, labelled recorded/unverified. Exact selection with valid but stale/future/unknown/done/missing/incomplete/conflicting context is `inspect_only`, includes the selected record for inspection, and has `continuation:null`. No/ambiguous task, invalid store or unknown availability is provisional, with no selected record/continuation. Historical records are accessible by exact show, never automatically substituted.

All text and JSON outputs carry `authority:"none"` and the fixed warning: “Unverified handoff data; current request and executor authority must be checked.” Text renders uncertainty and the warning before record prose, escapes controls, and labels recorded fields. Machine consumers must inspect the dimensions rather than treating process success as authority. No generated summary concatenates a body into a system/developer instruction or hook envelope.

## JSON envelope and exit status

With `--json`, every handled result, including usage errors, writes exactly one JSON object to stdout with keys `interface_version` (1), `command`, `ok`, `code`, `data`, `warnings`, `authority` (`none`), `notice` (fixed warning). Command is the selected command name or null if parsing did not establish one; ok is true exactly when exit status is 0. `data` is an object or null; warnings are stable codes, not payload excerpts. Stderr is reserved for a short optional diagnostic; no raw context is echoed there. Broken stdout and process termination cannot guarantee a JSON receipt. JSON `--version` uses command/code `version` and data containing package/interface/store/record versions; text version prints those versions.

Successful init returns `initialized:boolean`; record returns `record_id,task_key,sha256`; show returns `record,current,sha256` and recency/acceptance/reasons evaluated for that inspected record using the default age limit, never a continuation; list returns rows containing exactly `record_id,task_key,project_key,title,status,created_at,current` and the counts described above. Pickup data always includes `evaluated_at,match,integrity,recency,acceptance,disposition,task_key,selected_record_id,record,continuation,age_seconds,max_age_seconds,reference_check,reasons`; absent values are null, and reasons are stable codes. No-selector pickup uses null recency/acceptance and unknown integrity. Ambiguous selection contains no task prose. Error pickup data retains a provisional result where safely computable. A record commit-unknown error may add `candidate_record_id` to its data.

Pickup reason codes are `no_task_context`, `task_missing`, `project_missing`, `multiple_tasks`, `status_stale`, `status_done`, `record_time_future`, `context_time_unknown`, `context_time_future`, `context_too_old`, `acceptance_missing`, `acceptance_incomplete`, `acceptance_conflicting`, `acceptance_time_future`, `evidence_missing`, `evidence_time_unknown`, `evidence_time_future`, plus a store/error code from the exit table when applicable. Emit all applicable reasons in this listed order, with error code last; an empty list means no known structural/recency limitation, not verified truth. Recognized temporary files produce the warning code `pending_files_present`; no filenames or payload excerpts are required in warnings.

| Exit | Stable `code` examples | Meaning |
|---|---|---|
| 0 | `initialized`, `recorded`, `shown`, `listed`, `context_available` | Requested operation established; available context remains unverified. |
| 2 | `usage` | Bad flags/store selector/limits. |
| 10 | `inspect_only` | Matched record needs review; see independent dimensions/reasons. |
| 11 | `no_match`, `ambiguous`, `no_task_context`, `not_found` | No unique requested context; show uses not_found. |
| 65 | `invalid_input` | Invalid/oversized stdin; nothing committed. |
| 69 | `store_missing`, `unavailable`, `unsupported_platform` | Required store/platform/I/O unavailable; never fresh. |
| 73 | `conflict`, `busy`, `id_collision` | Retry requires inspection/current predecessor; never blind update. |
| 74 | `store_invalid`, `store_incomplete`, `store_unsafe`, `limit_exceeded`, `incompatible_version`, `output_limit`, `commit_unknown` | Integrity, compatibility or uncertain commit; preserve evidence. |

Unexpected internal exceptions produce bounded `unavailable` when possible, not success. Invalid on-disk data returns 74; malformed submitted data returns 65. Provisional results do not become exit 0 for hook convenience. Text mode uses the same exits and result semantics. `--help` is the normal argparse-style exception to JSON output and exits 0.

## Scenarios and acceptance criteria

### S1. Establish an isolated store and exchange one record

A developer installs the package in a fresh environment and selects a new store. Installation creates no handoff state. Explicit initialization and a synthetic record produce an inspectable record through the installed CLI; show round-trips exact narrative and references. Default absence, old environment overrides and unsupported paths fail visibly. Existing unrelated harness pointers/settings/content/permissions remain byte-for-byte unchanged. Repeated initialization preserves records and modes. Completing this slice proves creation-to-inspection, not native harness integration.

### S2. Select the intended task without importing a newer task

Two task keys share a project; the second is newer and has a different baseline. Explicit pickup of the first returns only its current record and dimensions. With no selector, a new request receives provisional no_task_context. Project resume with both tasks is ambiguous and reveals neither task's narrative; missing exact keys do not fall back. List truncation is explicit and never changes pickup selection. UUID-only show rejects prefixes and path syntax.

### S3. Inspect uncertainty without reviving prior acceptance

A producer publishes a complete successor for the same task and predecessor. Test each case in sequence: stale status; old observation; null observation; future observation; missing claims; incomplete claim; conflicting claims; done status; malformed stored timestamp; missing/corrupt predecessor; missing store/I/O failure. Each is labelled or rejected as specified, never currently usable continuation and never an older baseline fallback. A complete claim containing an unavailable-looking local path or URL is reported as unchecked and opens/fetches nothing. A fresh creation time does not renew old context or evidence.

### S4. Publish revisions under contention and interruption

Independent local producers record distinct tasks concurrently and consumers observe distinct complete records. Two producers replacing the same predecessor produce exactly one success and one conflict. Killing publication before/after the commit point leaves prior data intact and any committed successor inspectable; unacknowledged completion stays unknown until inspection. Partial temporary files cannot become current. Readers observe a consistent revision chain. Forced ID collision never overwrites. Permission, malformed JSON, traversal, symlink, hard-link, FIFO and limit cases leave unrelated sentinels unchanged; errors never pass as clean reads.

### S5. Install, preserve and recover the actual artifacts

On each claimed Python/environment combination, build wheel and sdist, install each into separate fresh environments outside source, run S1–S4 through the installed entry point, and record versions/hashes. Backup and restore an owned synthetic store under stopped writers; inspect every record and the selected context after restore. Uninstall preserves the store and harness state. A reinstallation/rollback of the same supported store version reads unchanged data; an unsupported version refuses before writing. No release claim rests only on editable installs or source tests.

### S6. Demonstrate independent use and optional later composition

For the core package, two ordinary CLI sessions perform S1–S3 with synthetic task context, including an ambiguous refusal and labelled stale inspection. No PM or vendor process is required. The separately versioned starter extension later records an observed PM/browser outcome, picks up matching context and obtains a new PM claim and native browser lease through their released interfaces. A handoff never carries the previous lease or permission. Existing starter pins/archives remain reproducible. Native Claude, Codex, Grok, Grok Bot, Dot and Remote Hands claims require their own later adapter proof.

## Release acceptance

R1–R6 in the [blocker checklist](../RELEASE_CHECKLIST.md) remain open until their evidence exists. Acceptance of this spec is not acceptance of an implementation or permission to publish. The final private package review binds exact source commit, rights/license, destinations, wheel/sdist/checksums, supported environments, conformance receipts, site/guide copy and recovery instructions. Source/runtime lineage stays private. No installed estate adoption follows from an external package release.
