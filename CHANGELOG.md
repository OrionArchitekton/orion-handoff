# Changelog

## 0.1.0 candidate

Explicit local stores, immutable task revisions and bounded JSON/text inspection.
Pickup separates matching, integrity, observed recency and acceptance claims;
every result carries no authority. No provider adapters or runtime integration.

Release review corrections:

- Reject numeric timezone offsets outside hour 00–23 / minute 00–59 before
  normalization, including timestamps inside claims, evidence and stored records.
- Preserve candidate identity for uncertain publication when lock or descriptor
  cleanup fails. Attempt all descriptor cleanup and preserve original operation
  faults. Inspect the candidate before retrying.

Supported evidence is limited to the environments recorded in the release packet.
