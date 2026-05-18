# Security Review

## Scope

Local CLI, deterministic synthetic wallet requests, calldata and typed-data decode, balance-diff simulation, signed intent receipts, DuckDB run store, static dashboard, JSONL tool loop, and demo-pack export.

## Assessment

The application is offline and synthetic-only. It does not contact chain RPCs, wallet APIs, custody systems, external identity providers, or shell commands at runtime.

## Controls

- Fixtures are parsed through Pydantic models.
- Request decoding uses a closed local ABI/action registry.
- Receipts include canonical hashes and Ed25519 signatures.
- Signature verification is part of the CLI verifier.
- DuckDB writes use parameterized inserts.
- Dashboard rendering uses Jinja autoescaping.
- Runtime state, outputs, caches, and virtual environments are ignored by git.

## Focused Scan Status

Completed 2026-05-18.

Threat model: local offline CLI and dashboard over synthetic institutional wallet requests. Primary risks are accidental credential/data inclusion, unsafe command execution, receipt forgery, unsupported-method acceptance, unsafe dashboard rendering, and incorrect policy-pass reporting for risky signing intents.

Finding discovery:

- Secret/public-hygiene scan found no credentials, sensitive auth material, campaign artifacts, or private customer data in committed source candidates.
- Dangerous sink scan found no runtime shell execution, network clients, dynamic `eval`/`exec`, pickle, YAML loading, or socket use in `src/`.
- The only `subprocess` use is in tests to black-box validate the CLI JSONL tool loop.
- Request decoding uses a closed local action registry; unsupported methods are flagged as risk.
- Receipt signatures verify against canonical unsigned receipt bytes and the receipt hash excludes signature/public-key/hash self-reference fields.
- DuckDB writes use parameterized statements.
- Dashboard output is generated from local JSON through Jinja autoescaping.

Validation: no reportable findings.

Residual risk: this is a synthetic local reference implementation, not a production signing gateway. Production use would need canonical ABI management, real fork simulation, HSM/MPC integration, chain-specific replay protection, authenticated operators, rate limits, and independent audit of the policy engine.
