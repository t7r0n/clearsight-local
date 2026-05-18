# Clearsight Local

Clearsight Local is an offline reference implementation for pre-signature institutional wallet intent receipts.

It decodes synthetic WalletConnect-style requests, simulates token-level balance and allowance effects, produces human-readable intent receipts, signs those receipts with an Ed25519 attestation key, and exports audit envelopes for downstream settlement workflows.

## Thesis

Offline pre-signature intent receipt simulator for institutional wallet requests.

## Primitives

- Builds a compact fixture set around offline pre-signature intent receipt simulator for institutional wallet requests.
- Separates signal, failure, and reporting code so `Clearsight Local` can be audited without a live integration.
- Writes `clearsight-local` structured outputs before rendering the dashboard, which keeps the UI honest.
- Uses the `clearsight-local` lockfile and local commands as the reproducibility contract.

## Reproduce locally

```bash
uv sync
uv run clearsight-local init-demo
uv run clearsight-local explain req-permit2-router
uv run clearsight-local run-suite
uv run clearsight-local verify
uv run clearsight-local dashboard
```

## Review packet

- `outputs/receipts.json`
- `outputs/atlas_envelopes.json`
- `outputs/summary.json`
- `outputs/dashboard.html`
- `outputs/demo_pack/`

## Confidence checks

```bash
uv run ruff check .
uv run pytest -q
uv run clearsight-local verify
```

## Data limits

`Clearsight Local` is built for local reproduction: deterministic inputs enter the run, deterministic evidence comes out, and private data stays outside the repo.
