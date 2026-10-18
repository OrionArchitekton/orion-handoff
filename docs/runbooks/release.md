---
verified: 2026-10-17
review_after: 2026-11-17
topics: [release, pypi, github]
references: [../../.github/workflows/release.yml, ../../.github/release-manifest.json, ../../requirements-build.txt]
---
# Release operations

Release from a human-reviewed protected main. CI validates installed wheel and sdist separately on CPython 3.11/3.13, plus lint, secrets and dependency changes.

Build distributions outside the publishing job, run the exact-artifact conformance suite, inspect exports and bind bytes to the release manifest and SHA256SUMS. If packaging documentation changes, record the new hashes and prove runtime module bytes unchanged from the approved implementation.

Upload wheel, sdist, source archive and checksums to the corresponding GitHub release. Configure a PyPI Trusted Publisher scoped to OrionArchitekton/orion-handoff, release.yml, environment pypi. The protected environment requires a human reviewer. No package password or API token is needed.

Dispatch release.yml from main after verifying the public GitHub release. Its verify job and publish job each download the named release files and check the fixed manifest hashes; the publishing job never checks out source, builds, or installs dependencies. It submits only wheel/sdist to PyPI. Never overwrite published version bytes.

Validate public GitHub/PyPI metadata, downloaded hashes, clean installs and the installed CLI's version/pickup behavior. Monitor the exact workflow, version and artifacts; a workflow success alone is not consumer proof.

Rollback: stop an unapproved pending environment deployment or future release workflow. If a public package is defective, preserve receipts, consider yanking and publish a corrected version after review. Do not delete/reuse release versions or roll back user stores automatically. Site/hub reversions are separate. No estate hooks, runtime, stores or scheduled jobs are changed by publishing.
