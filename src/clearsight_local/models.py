from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class Policy(BaseModel):
    max_single_token_out_usd: float
    allow_unlimited_approvals: bool
    required_quorum: int


class Institution(BaseModel):
    id: str
    wallet: str
    policy: Policy


class Token(BaseModel):
    symbol: str
    address: str
    decimals: int
    usd: float


class Balance(BaseModel):
    symbol: str
    amount: float


class Counterparty(BaseModel):
    address: str
    label: str
    verified: bool


class WalletRequest(BaseModel):
    id: str
    kind: Literal["calldata", "typed_data"]
    method: str
    target: str
    params: dict[str, str | float | int]


class FixtureSet(BaseModel):
    institution: Institution
    tokens: list[Token]
    balances: list[Balance]
    counterparties: list[Counterparty]
    requests: list[WalletRequest]


class BalanceDiff(BaseModel):
    token: str
    before: float
    after: float
    delta: float
    usd_delta: float


class AllowanceGrant(BaseModel):
    token: str
    spender: str
    spender_label: str
    amount: float
    usd_value: float
    unlimited: bool
    verified_spender: bool


class RoleChange(BaseModel):
    role: str
    grantee: str
    quorum: int
    quorum_satisfied: bool


class IntentReceipt(BaseModel):
    receipt_id: str
    request_id: str
    method: str
    target: str
    target_label: str
    target_verified: bool
    summary: str
    balance_diffs: list[BalanceDiff] = Field(default_factory=list)
    allowance_grants: list[AllowanceGrant] = Field(default_factory=list)
    role_changes: list[RoleChange] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    policy_pass: bool
    canonical_hash: str
    public_key_hex: str
    signature_hex: str | None = None
    latency_ms: float


class SuiteSummary(BaseModel):
    run_id: str
    request_count: int
    receipt_count: int
    decode_coverage: float
    signature_validity: float
    risky_request_count: int
    policy_block_count: int
    p95_latency_ms: float
    pass_gates: bool


class AtlasEnvelope(BaseModel):
    envelope_id: str
    request_id: str
    receipt_hash: str
    counterparty: str
    policy_pass: bool
    risk_flags: list[str]

