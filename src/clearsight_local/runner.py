from __future__ import annotations

import json
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

from clearsight_local.engine import atlas_envelope, explain_request, verify_receipt
from clearsight_local.fixtures import fixture_path, load_fixtures
from clearsight_local.models import AtlasEnvelope, IntentReceipt, SuiteSummary, project_root

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def runs_dir() -> Path:
    return project_root() / "runs" / "latest"


def outputs_dir() -> Path:
    return project_root() / "outputs"


def init_demo(force: bool = False) -> None:
    with _workspace_lock():
        _init_demo_unlocked(force=force)


def _init_demo_unlocked(force: bool = False) -> None:
    if force:
        shutil.rmtree(runs_dir(), ignore_errors=True)
        shutil.rmtree(outputs_dir(), ignore_errors=True)
    runs_dir().mkdir(parents=True, exist_ok=True)
    outputs_dir().mkdir(parents=True, exist_ok=True)
    _connect().close()


def explain(request_id: str) -> IntentReceipt:
    return explain_request(request_id)


def run_suite(iterations: int = 1) -> SuiteSummary:
    with _workspace_lock():
        _init_demo_unlocked(force=True)
        data = load_fixtures()
        receipts: list[IntentReceipt] = []
        for _ in range(iterations):
            receipts.extend(explain_request(request.id, fixtures=data) for request in data.requests)
        envelopes = [atlas_envelope(receipt) for receipt in receipts]
        summary = _summarize(f"run-{uuid.uuid4().hex[:12]}", receipts)
        _write_outputs(summary, receipts, envelopes)
        _write_db(summary, receipts, envelopes)
        return summary


def verify_outputs() -> tuple[bool, dict[str, Any]]:
    with _workspace_lock():
        summary_path = outputs_dir() / "summary.json"
        if not summary_path.exists():
            return False, {"error": "run-suite has not produced summary.json"}
        summary = SuiteSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
        receipts = [
            IntentReceipt.model_validate(item)
            for item in json.loads((outputs_dir() / "receipts.json").read_text(encoding="utf-8"))
        ]
        envelopes = [
            AtlasEnvelope.model_validate(item)
            for item in json.loads((outputs_dir() / "atlas_envelopes.json").read_text(encoding="utf-8"))
        ]
        con = _connect()
        try:
            receipt_rows = con.execute("select count(*) from receipts").fetchone()[0]
            envelope_rows = con.execute("select count(*) from envelopes").fetchone()[0]
        finally:
            con.close()
        checks = {
            "receipt_count_match": receipt_rows == len(receipts) == summary.receipt_count,
            "envelope_count_match": envelope_rows == len(envelopes) == len(receipts),
            "all_signatures_valid": all(verify_receipt(receipt) for receipt in receipts),
            "decode_coverage": summary.decode_coverage == 1.0,
            "risky_request_detected": summary.risky_request_count > 0,
            "policy_block_detected": summary.policy_block_count > 0,
            "latency_gate": summary.p95_latency_ms < 600,
            "core_outputs": all((outputs_dir() / name).exists() for name in ["receipts.json", "atlas_envelopes.json", "summary.json"]),
            "overall_pass": summary.pass_gates,
        }
        checks["overall_pass"] = all(checks.values())
        return checks["overall_pass"], checks


def benchmark(iterations: int = 100) -> SuiteSummary:
    return run_suite(iterations=iterations)


def export_demo_pack() -> Path:
    with _workspace_lock():
        if not (outputs_dir() / "summary.json").exists():
            _run_suite_unlocked()
        pack = outputs_dir() / "demo_pack"
        shutil.rmtree(pack, ignore_errors=True)
        pack.mkdir(parents=True, exist_ok=True)
        for source in [
            fixture_path(),
            outputs_dir() / "receipts.json",
            outputs_dir() / "atlas_envelopes.json",
            outputs_dir() / "summary.json",
        ]:
            shutil.copy2(source, pack / source.name)
        (pack / "manifest.json").write_text(
            json.dumps(
                {
                    "artifact": "clearsight-local demo pack",
                    "contents": sorted(path.name for path in pack.iterdir()),
                    "data": "synthetic only",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return pack


def _run_suite_unlocked() -> SuiteSummary:
    data = load_fixtures()
    receipts = [explain_request(request.id, fixtures=data) for request in data.requests]
    envelopes = [atlas_envelope(receipt) for receipt in receipts]
    summary = _summarize(f"run-{uuid.uuid4().hex[:12]}", receipts)
    _write_outputs(summary, receipts, envelopes)
    _write_db(summary, receipts, envelopes)
    return summary


def _summarize(run_id: str, receipts: list[IntentReceipt]) -> SuiteSummary:
    latencies = sorted(receipt.latency_ms for receipt in receipts)
    p95 = latencies[int(len(latencies) * 0.95) - 1] if len(latencies) >= 2 else (latencies[0] if latencies else 0.0)
    signature_validity = sum(1 for receipt in receipts if verify_receipt(receipt)) / max(1, len(receipts))
    decode_coverage = sum(1 for receipt in receipts if "unsupported_method" not in receipt.risk_flags) / max(1, len(receipts))
    risky = sum(1 for receipt in receipts if receipt.risk_flags)
    blocked = sum(1 for receipt in receipts if not receipt.policy_pass)
    return SuiteSummary(
        run_id=run_id,
        request_count=len(receipts),
        receipt_count=len(receipts),
        decode_coverage=round(decode_coverage, 4),
        signature_validity=round(signature_validity, 4),
        risky_request_count=risky,
        policy_block_count=blocked,
        p95_latency_ms=round(p95, 4),
        pass_gates=signature_validity == 1.0 and decode_coverage == 1.0 and risky > 0 and blocked > 0 and p95 < 600,
    )


def _write_outputs(summary: SuiteSummary, receipts: list[IntentReceipt], envelopes: list[AtlasEnvelope]) -> None:
    outputs_dir().mkdir(parents=True, exist_ok=True)
    (outputs_dir() / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    (outputs_dir() / "receipts.json").write_text(
        json.dumps([receipt.model_dump(mode="json") for receipt in receipts], indent=2),
        encoding="utf-8",
    )
    (outputs_dir() / "atlas_envelopes.json").write_text(
        json.dumps([envelope.model_dump(mode="json") for envelope in envelopes], indent=2),
        encoding="utf-8",
    )


def _write_db(summary: SuiteSummary, receipts: list[IntentReceipt], envelopes: list[AtlasEnvelope]) -> None:
    con = _connect()
    try:
        con.execute("delete from receipts")
        con.execute("delete from envelopes")
        for receipt in receipts:
            con.execute(
                "insert into receipts values (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    summary.run_id,
                    receipt.receipt_id,
                    receipt.request_id,
                    receipt.method,
                    receipt.policy_pass,
                    ",".join(receipt.risk_flags),
                    receipt.canonical_hash,
                    receipt.latency_ms,
                ],
            )
        for envelope in envelopes:
            con.execute(
                "insert into envelopes values (?, ?, ?, ?, ?)",
                [summary.run_id, envelope.envelope_id, envelope.request_id, envelope.receipt_hash, envelope.policy_pass],
            )
    finally:
        con.close()


def _connect() -> duckdb.DuckDBPyConnection:
    runs_dir().mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(runs_dir() / "clearsight.duckdb"))
    con.execute(
        """
        create table if not exists receipts (
            run_id varchar,
            receipt_id varchar,
            request_id varchar,
            method varchar,
            policy_pass boolean,
            risk_flags varchar,
            canonical_hash varchar,
            latency_ms double
        )
        """
    )
    con.execute(
        """
        create table if not exists envelopes (
            run_id varchar,
            envelope_id varchar,
            request_id varchar,
            receipt_hash varchar,
            policy_pass boolean
        )
        """
    )
    return con


@contextmanager
def _workspace_lock() -> Any:
    lock_path = project_root() / ".clearsight.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
