"""
stakechat_bot.parser
~~~~~~~~~~~~~~~~~~~~
Parse user messages into typed Action objects.

Changes from original:
  - ParsedStake.amount is Optional[float]; None means "unstake all"
  - "unstake all <netuid>" properly sets amount=None instead of amount=0
  - balance / pnl / roi / history added as first-class Action types
    (previously handled via a raw text fallback in engine)
  - "sn31", "SN31", "31" all resolve to netuid=31  (unchanged)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ── Action types ──────────────────────────────────────────────────────────────

@dataclass
class Action:
    pass


@dataclass
class Help(Action):
    pass


@dataclass
class Privacy(Action):
    pass


@dataclass
class Whoami(Action):
    pass


@dataclass
class Confirm(Action):
    token: str = ""


@dataclass
class Balance(Action):
    pass


@dataclass
class Pnl(Action):
    pass


@dataclass
class Roi(Action):
    pass


@dataclass
class History(Action):
    pass


@dataclass
class ParsedStake(Action):
    op: str                      # "add" or "remove"
    amount: Optional[float]      # None = "unstake all"
    netuid: Optional[int] = None
    validator: Optional[str] = None
    wallet: Optional[str] = None


@dataclass
class Unknown(Action):
    text: str = ""


# ── Tokenizer ─────────────────────────────────────────────────────────────────

_FILLER = {
    "tao", "alpha", "to", "on", "into", "in", "for", "the", "a", "an",
    "please", "pls", "subnet", "netuid", "validator", "vali",
    "delegate", "deleg",
}

_AMOUNT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_NETUID_RE = re.compile(r"^(?:sn)?(\d{1,5})$", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return re.split(r"\s+", (text or "").strip()) if (text or "").strip() else []


def _is_amount(tok: str) -> bool:
    return bool(_AMOUNT_RE.match(tok))


def _parse_netuid(tok: str) -> Optional[int]:
    m = _NETUID_RE.match(tok)
    return int(m.group(1)) if m else None


# ── Public entry point ────────────────────────────────────────────────────────

def parse_message(text: str) -> Action:
    tokens = _tokenize(text)
    if not tokens:
        return Unknown()

    cmd = tokens[0].lower()

    # Info
    if cmd in {"help", "h", "?"}:
        return Help()
    if cmd in {"privacy", "p"}:
        return Privacy()
    if cmd in {"whoami", "me", "id"}:
        return Whoami()
    if cmd in {"confirm", "ok", "yes"}:
        return Confirm(token=tokens[1].strip() if len(tokens) > 1 else "")

    # Portfolio
    if cmd in {"balance", "bal", "b", "portfolio"}:
        return Balance()
    if cmd in {"pnl", "profit"}:
        return Pnl()
    if cmd in {"roi"}:
        return Roi()
    if cmd in {"history", "hist", "tx"}:
        return History()

    # Stake / Unstake
    if cmd in {"stake", "s", "add"}:
        return _parse_stake_like("add", tokens[1:])
    if cmd in {"unstake", "u", "remove", "rm", "sell"}:
        return _parse_stake_like("remove", tokens[1:])

    return Unknown(text=text)


def _parse_stake_like(op: str, tokens: list[str]) -> Action:
    # Handle "unstake all [netuid]"
    if op == "remove" and tokens and tokens[0].lower() == "all":
        netuid = _parse_netuid(tokens[1]) if len(tokens) > 1 else None
        return ParsedStake(op="remove", amount=None, netuid=netuid)

    # Strip filler words, extract wallet=
    wallet: Optional[str] = None
    rest: list[str] = []
    for t in tokens:
        tl = t.lower()
        if tl in _FILLER:
            continue
        if tl.startswith("wallet=") or tl.startswith("w="):
            wallet = t.split("=", 1)[1].strip() or None
            continue
        rest.append(t)

    # Find amount (first numeric token)
    amount: Optional[float] = None
    idx_amount: Optional[int] = None
    for i, t in enumerate(rest):
        if _is_amount(t):
            try:
                amount = float(t)
                idx_amount = i
            except ValueError:
                pass
            break

    if amount is None:
        return Unknown(text="missing amount")

    # netuid: first matching token after amount
    after    = rest[idx_amount + 1:] if idx_amount is not None else []
    netuid: Optional[int] = None
    validator: Optional[str] = None

    for i, t in enumerate(after):
        n = _parse_netuid(t)
        if n is not None:
            netuid = n
            remaining = after[i + 1:]
            if remaining:
                validator = " ".join(remaining).strip() or None
            break

    if netuid is None and after:
        validator = " ".join(after).strip() or None

    return ParsedStake(
        op=op,
        amount=amount,
        netuid=netuid,
        validator=validator,
        wallet=wallet,
    )
