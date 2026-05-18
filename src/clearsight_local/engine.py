from __future__ import annotations

import hashlib
import json
import time
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from clearsight_local.fixtures import load_fixtures
from clearsight_local.models import (
    AllowanceGrant,
    AtlasEnvelope,
    BalanceDiff,
    FixtureSet,
    IntentReceipt,
    RoleChange,
    WalletRequest,
)


SUPPORTED_METHODS = {
    "erc20.approve",
    "permit2.permit",
    "universal_router.swap_exact_in",
    "safe.exec_transaction",
}


def explain_request(request_id: str, fixtures: FixtureSet | None = None) -> IntentReceipt:
    start = time.perf_counter()
    data = fixtures or load_fixtures()
    request = next((item for item in data.requests if item.id == request_id), None)
    if request is None:
        raise ValueError(f"unknown request: {request_id}")
    receipt = _simulate(data, request, (time.perf_counter() - start) * 1000)
    return _sign_receipt(receipt)


def verify_receipt(receipt: IntentReceipt) -> bool:
    if receipt.signature_hex is None:
        return False
    signature = bytes.fromhex(receipt.signature_hex)
    unsigned = receipt.model_copy(update={"signature_hex": None})
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(receipt.public_key_hex))
        public_key.verify(signature, _canonical_bytes(unsigned))
        return (
            _sha(unsigned.model_dump(mode="json", exclude={"signature_hex", "public_key_hex", "canonical_hash"}))
            == receipt.canonical_hash
        )
    except (InvalidSignature, ValueError):
        return False


def atlas_envelope(receipt: IntentReceipt) -> AtlasEnvelope:
    return AtlasEnvelope(
        envelope_id=f"atlas-{uuid.uuid4().hex[:12]}",
        request_id=receipt.request_id,
        receipt_hash=receipt.canonical_hash,
        counterparty=receipt.target_label,
        policy_pass=receipt.policy_pass,
        risk_flags=receipt.risk_flags,
    )


def _simulate(data: FixtureSet, request: WalletRequest, latency_ms: float) -> IntentReceipt:
    target = _counterparty(data, request.target)
    diffs: list[BalanceDiff] = []
    grants: list[AllowanceGrant] = []
    roles: list[RoleChange] = []
    risks: list[str] = []

    if request.method not in SUPPORTED_METHODS:
        risks.append("unsupported_method")
    elif request.method in {"erc20.approve", "permit2.permit"}:
        grants.append(_allowance(data, request))
    elif request.method == "universal_router.swap_exact_in":
        diffs.extend(_swap(data, request))
    elif request.method == "safe.exec_transaction":
        roles.append(_role_change(data, request))

    for grant in grants:
        if grant.unlimited:
            risks.append("unlimited_approval")
        if not grant.verified_spender:
            risks.append("unverified_spender")
        if grant.usd_value > data.institution.policy.max_single_token_out_usd:
            risks.append("approval_value_over_policy")
    for diff in diffs:
        if diff.usd_delta < -data.institution.policy.max_single_token_out_usd:
            risks.append("outflow_over_policy")
    for role in roles:
        if not role.quorum_satisfied:
            risks.append("quorum_not_satisfied")

    policy_pass = not risks
    summary = _summary(request, target.label, diffs, grants, roles, risks)
    receipt = IntentReceipt(
        receipt_id=f"receipt-{uuid.uuid4().hex[:12]}",
        request_id=request.id,
        method=request.method,
        target=request.target,
        target_label=target.label,
        target_verified=target.verified,
        summary=summary,
        balance_diffs=diffs,
        allowance_grants=grants,
        role_changes=roles,
        risk_flags=sorted(set(risks)),
        policy_pass=policy_pass,
        canonical_hash="",
        public_key_hex="",
        latency_ms=round(latency_ms, 4),
    )
    receipt.canonical_hash = _sha(receipt.model_dump(mode="json", exclude={"signature_hex", "public_key_hex", "canonical_hash"}))
    return receipt


def _allowance(data: FixtureSet, request: WalletRequest) -> AllowanceGrant:
    token_info = _token(data, str(request.params["token"]))
    spender = str(request.params["spender"])
    amount = float(request.params["amount"])
    counterparty = _counterparty(data, spender)
    balance = _balance(data, token_info.symbol)
    unlimited = amount > balance.amount * 1000
    usd_value = amount * token_info.usd
    return AllowanceGrant.model_validate(
        {
            "token": token_info.symbol,
            "spender": spender,
            "spender_label": counterparty.label,
            "amount": amount,
            "usd_value": round(usd_value, 2),
            "unlimited": unlimited,
            "verified_spender": counterparty.verified,
        }
    )


def _swap(data: FixtureSet, request: WalletRequest) -> list[BalanceDiff]:
    token_in_info = _token(data, str(request.params["token_in"]))
    token_out_info = _token(data, str(request.params["token_out"]))
    amount_in = float(request.params["amount_in"])
    min_amount_out = float(request.params["min_amount_out"])
    before_in = _balance(data, token_in_info.symbol).amount
    before_out = _balance(data, token_out_info.symbol).amount
    return [
        BalanceDiff.model_validate(
            {
                "token": token_in_info.symbol,
                "before": before_in,
                "after": round(before_in - amount_in, 8),
                "delta": -amount_in,
                "usd_delta": round(-amount_in * token_in_info.usd, 2),
            }
        ),
        BalanceDiff.model_validate(
            {
                "token": token_out_info.symbol,
                "before": before_out,
                "after": round(before_out + min_amount_out, 8),
                "delta": min_amount_out,
                "usd_delta": round(min_amount_out * token_out_info.usd, 2),
            }
        ),
    ]


def _role_change(data: FixtureSet, request: WalletRequest) -> RoleChange:
    quorum = int(request.params["quorum"])
    return RoleChange(
        role=str(request.params["role"]),
        grantee=str(request.params["grantee"]),
        quorum=quorum,
        quorum_satisfied=quorum >= data.institution.policy.required_quorum,
    )


def _sign_receipt(receipt: IntentReceipt) -> IntentReceipt:
    signing_key = Ed25519PrivateKey.generate()
    public_key_hex = signing_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    unsigned = receipt.model_copy(update={"public_key_hex": public_key_hex, "signature_hex": None})
    signature = signing_key.sign(_canonical_bytes(unsigned))
    return unsigned.model_copy(update={"signature_hex": signature.hex()})


def _canonical_bytes(receipt: IntentReceipt) -> bytes:
    return json.dumps(receipt.model_dump(mode="json", exclude={"signature_hex"}), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _counterparty(data: FixtureSet, address: str):
    return next((item for item in data.counterparties if item.address.lower() == address.lower()), data.counterparties[-1])


def _token(data: FixtureSet, symbol: str):
    return next(item for item in data.tokens if item.symbol == symbol)


def _balance(data: FixtureSet, symbol: str):
    return next(item for item in data.balances if item.symbol == symbol)


def _summary(
    request: WalletRequest,
    target_label: str,
    diffs: list[BalanceDiff],
    grants: list[AllowanceGrant],
    roles: list[RoleChange],
    risks: list[str],
) -> str:
    if grants:
        grant = grants[0]
        return f"{request.method} grants {grant.spender_label} permission over {grant.amount:g} {grant.token}; risks: {', '.join(risks) or 'none'}."
    if diffs:
        outflows = [diff for diff in diffs if diff.delta < 0]
        inflows = [diff for diff in diffs if diff.delta > 0]
        return f"{target_label} swaps {abs(outflows[0].delta):g} {outflows[0].token} for at least {inflows[0].delta:g} {inflows[0].token}; risks: {', '.join(risks) or 'none'}."
    if roles:
        role = roles[0]
        return f"{target_label} grants role {role.role} to {role.grantee} with quorum {role.quorum}; risks: {', '.join(risks) or 'none'}."
    return f"{request.method} could not be decoded safely."
