from __future__ import annotations

import json
import subprocess

from clearsight_local.dashboard import build_dashboard
from clearsight_local.engine import explain_request, verify_receipt
from clearsight_local.runner import export_demo_pack, run_suite, verify_outputs


def test_explain_request_signs_receipt_and_decodes_allowance() -> None:
    receipt = explain_request("req-permit2-router")
    assert verify_receipt(receipt)
    assert receipt.allowance_grants
    assert receipt.policy_pass
    assert receipt.canonical_hash


def test_risky_request_is_blocked_with_specific_flags() -> None:
    receipt = explain_request("req-unlimited-drain")
    assert verify_receipt(receipt)
    assert not receipt.policy_pass
    assert "unlimited_approval" in receipt.risk_flags
    assert "unverified_spender" in receipt.risk_flags


def test_swap_receipt_has_token_level_diffs() -> None:
    receipt = explain_request("req-router-swap")
    assert len(receipt.balance_diffs) == 2
    assert any(diff.delta < 0 for diff in receipt.balance_diffs)
    assert any(diff.delta > 0 for diff in receipt.balance_diffs)


def test_run_verify_dashboard_and_demo_pack() -> None:
    summary = run_suite()
    assert summary.pass_gates
    ok, checks = verify_outputs()
    assert ok, checks
    dashboard = build_dashboard()
    assert "Clearsight Intent Dashboard" in dashboard.read_text(encoding="utf-8")
    pack = export_demo_pack()
    assert (pack / "manifest.json").exists()


def test_jsonl_tool_loop() -> None:
    payload = {"tool": "explain", "arguments": {"request_id": "req-safe-role"}}
    completed = subprocess.run(
        ["uv", "run", "--project", "elite_projects/clearsight-local", "clearsight-local", "tool-loop"],
        input=json.dumps(payload) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["request_id"] == "req-safe-role"
    assert result["signature_hex"]

