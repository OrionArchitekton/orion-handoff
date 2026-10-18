# Security scope

The core records unverified local task context. It does not authenticate actors, grant execution authority, validate approval, execute next steps or fetch references. Record prose and evidence are untrusted data.

The supported coordination model is cooperating processes under one local user on a tested Linux local filesystem. Other processes with that user's access can modify files or bypass advisory locks. Cross-host fencing, network filesystems and adversarial same-user isolation are outside the contract.

Core commands require an explicit store. They reject unsafe paths, ownership/modes, unrecognized entries, invalid revision chains and bounded-I/O failures. Those checks reduce accidental escape and corruption; they are not a sandbox. Do not place secrets in synthetic examples or send a real handoff store as a bug report.

Report vulnerabilities privately through [GitHub security advisories](https://github.com/OrionArchitekton/orion-handoff/security/advisories/new). Provide the candidate version, platform/filesystem, a minimal synthetic reproduction and the observed exit/JSON. Exclude tokens, transcripts, personal paths, approvals and private task content.

No security contact, hosted reporting service or notification workflow is installed by the package.
