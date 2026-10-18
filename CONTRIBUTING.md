# Development and conformance

Use an isolated checkout and disposable environments. No test may use a real handoff store, native hook, transcript, account, phone or browser. Keep source and installed runtime separate.

```sh
python3.11 -m venv .venv-dev
.venv-dev/bin/python -m pip install -r requirements-build.txt
.venv-dev/bin/python -m pip install --no-deps --no-build-isolation .
.venv-dev/bin/python -m unittest discover -s tests -v
ruff check src tests
.venv-dev/bin/python -m build
```

Reinstall after changing source. These are non-editable installs. Child CLI processes use temporary homes/stores and run outside the checkout. For release conformance, install the exact wheel and sdist separately into fresh Python 3.11/3.13 environments, run the tests outside the source tree, and retain artifact hashes and exit logs.

The installed CLI is the primary test seam. Real subprocesses exercise contention. Test-only launchers target interruption stages without shipping any public fault controls. Exact clock equality and otherwise unreachable output-buffer caps use narrow deterministic checks against installed internal modules; this does not establish a supported Python import API.

Implement one observable scenario RED→GREEN at a time. Update the living spec with contract changes and the operator runbook with operational changes. Tests are standard-library unittest; Ruff and pinned build tools are development-only. A pinned four-combination CI workflow is prepared locally; no hosted run or publishing workflow is active for this private candidate.

Keep examples synthetic, preserve applicable notices, and document provenance for new copied code. This private implementation was written from the reviewed behavior spec; private runtime files and history are not redistributed.
