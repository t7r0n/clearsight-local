# Clearsight Local

Clearsight Local is an offline reference implementation for pre-signature institutional wallet intent receipts.

It decodes synthetic WalletConnect-style requests, simulates token-level balance and allowance effects, produces human-readable intent receipts, signs those receipts with an Ed25519 attestation key, and exports audit envelopes for downstream settlement workflows.

The project is fully local and synthetic. It does not call chain RPCs, wallet APIs, custody systems, or external identity services.

## Quick Start

```bash
uv sync
uv run clearsight-local init-demo
uv run clearsight-local explain req-permit2-router
uv run clearsight-local run-suite
uv run clearsight-local verify
uv run clearsight-local dashboard
```

## Tool Surface

- `explain REQUEST_ID` decodes, simulates, scores, and signs one request.
- `run-suite` evaluates all synthetic requests.
- `verify` checks signature validity, decode coverage, latency, and risk gates.
- `tool-loop` accepts JSONL calls for local MCP-style integration.

## Outputs

- `outputs/receipts.json`
- `outputs/atlas_envelopes.json`
- `outputs/summary.json`
- `outputs/dashboard.html`
- `outputs/demo_pack/`

