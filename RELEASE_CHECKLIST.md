# Release checklist

MIT. Selected source rights confirmed by the author. Release approval covers the exact recorded candidate and destinations.

- Verify wheel/sdist on CPython 3.11 and 3.13 with the installed CLI outside source.
- Confirm explicit-store isolation, task matching, observed recency, immutable revision integrity and uncertain-commit receipts.
- Validate backed-up stores, uninstall/reinstall preservation and future-version refusal.
- Bind distribution files to SHA256SUMS; verify the manifest before uploading. Never rebuild inside the publishing job.
- Require CI, secret scans, dependency review, protected human review and the PyPI environment approval.
- Verify source, package install, site assets, Works routing and canonical guide at their public consumer boundaries.
- A package release performs no estate integration, native hook installation or migration.

See [release operations](docs/runbooks/release.md) and [local recovery](docs/runbooks/local-handoff-store.md).
