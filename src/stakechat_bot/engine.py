"""
stakechat_bot.engine
~~~~~~~~~~~~~~~~~~~~
Core logic layer — handles all commands and produces BotResponse objects.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import json
from dataclasses import dataclass
from typing import List, Optional

from .bittensor_client import BittensorClient, StakeResult
from .config import RootConfig
from .parser import (
    Help, Privacy, Whoami, Confirm,
    ParsedStake, Unknown, parse_message,
)
from .utils.jsonlog import append_jsonl

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
HISTORY_FILE = os.path.abspath(os.path.join(BASE_DIR, "..", "trade_history.jsonl"))


# ──────────────────────────────────────────────────────────────────────────────
# Response types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Button:
    text: str
    action: str
    tx_id: str = "0"


@dataclass
class BotResponse:
    text: str
    buttons: Optional[List[List[Button]]] = None


# ──────────────────────────────────────────────────────────────────────────────
# Pending-confirmation store (in-memory, TTL-gated)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _PendingOp:
    action: str
    expires_at: float


class _PendingStore:
    def __init__(self):
        self._store: dict[str, _PendingOp] = {}  # user_key -> pending

    def save(self, user_key: str, action: str, ttl: int) -> None:
        self._store[user_key] = _PendingOp(action=action, expires_at=time.time() + ttl)

    def pop(self, user_key: str) -> Optional[str]:
        op = self._store.pop(user_key, None)
        if op and time.time() < op.expires_at:
            return op.action
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────────────────────────────────────

class Engine:
    def __init__(self, cfg: RootConfig):
        self.cfg = cfg
        self._pending = _PendingStore()

        self._btclient = BittensorClient(
            network=self._subtensor_network(),
            wallets_path=self._wallets_path(),
        )
        self._wallet = None  # lazy-load

    # ── Config helpers ────────────────────────────────────────────────────────

    def _subtensor_network(self) -> str:
        """Return the configured subtensor network (defaults to finney)."""
        args = list(getattr(self.cfg.btcli, "common_args", []) or [])

        for i, a in enumerate(args):
            if a == "--subtensor.network" and i + 1 < len(args):
                v = str(args[i + 1]).strip()
                if v:
                    return v

        for v in args:
            v = str(v).strip().lower()
            if v in ("finney", "test", "local", "nakamoto"):
                return v

        return "finney"

    def _wallets_path(self) -> str:
        w = self.cfg.btcli.wallets.get(self.cfg.btcli.default_wallet)
        if w:
            return w.wallets_dir
        return os.path.expanduser("~/.bittensor/wallets")

    def _load_wallet(self):
        wallet_cfg = self.cfg.btcli.wallets.get(self.cfg.btcli.default_wallet)
        if not wallet_cfg:
            raise ValueError(f"Wallet '{self.cfg.btcli.default_wallet}' not in config")
        return self._btclient.load_wallet(
            coldkey_name=wallet_cfg.coldkey,
            password=wallet_cfg.password or "",
        )

    async def _get_wallet(self):
        if self._wallet is None:
            self._wallet = self._load_wallet()
        return self._wallet

    def _default_netuid(self) -> Optional[int]:
        w = self.cfg.btcli.wallets.get(self.cfg.btcli.default_wallet)
        if w and w.default_netuid is not None:
            return w.default_netuid
        return self.cfg.defaults.netuid

    def _default_hotkey(self) -> Optional[str]:
        """
        Return the configured default validator SS58, if any.

        Supports:
          - wallet.validator_all alias/ss58
          - cfg.defaults.validator alias/ss58
        """
        w = self.cfg.btcli.wallets.get(self.cfg.btcli.default_wallet)

        # Helper: if string looks like SS58, use directly (avoids resolver confusion).
        def _looks_like_ss58(s: str) -> bool:
            s = (s or "").strip()
            # loose SS58 check (base58, length 47-48)
            return bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{47,48}", s))

        if w and getattr(w, "validator_all", None):
            v = str(w.validator_all).strip()
            if _looks_like_ss58(v):
                return v
            from .validators import ValidatorResolver
            return ValidatorResolver(self.cfg.validators).resolve(v)

        if self.cfg.defaults.validator:
            v = str(self.cfg.defaults.validator).strip()
            if _looks_like_ss58(v):
                return v
            from .validators import ValidatorResolver
            return ValidatorResolver(self.cfg.validators).resolve(v)

        return None

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _is_authorized(self, platform: str, user_id: int) -> bool:
        if platform == "telegram":
            allowed = self.cfg.auth.telegram_user_ids
            return not allowed or user_id in allowed
        if platform == "discord":
            allowed = self.cfg.auth.discord_user_ids
            return not allowed or user_id in allowed
        return False

    def _user_key(self, platform: str, user_id: int) -> str:
        return f"{platform}:{user_id}"

    # ── Command normalization (tolerant parsing) ──────────────────────────────

    _TRAILING_JUNK_RE = re.compile(r"[^\w/]+$")

    def _normalize_cmd(self, raw_text: str) -> str:
        """
        Normalize a user message into a primary command token.
        Examples:
          'balance -' -> 'balance'
          '/start'    -> 'start'
          'BAL'       -> 'bal'
        """
        t = (raw_text or "").strip()
        if not t:
            return ""
        token = t.split()[0].strip()
        token = self._TRAILING_JUNK_RE.sub("", token)
        if token.startswith("/"):
            token = token[1:]
        return token.lower()

    # ── Public async entry point ──────────────────────────────────────────────

    async def handle_text_async(
        self,
        platform: str,
        user_id: int,
        user_name: str,
        chat_id: str,
        is_group: bool,
        text: str,
    ) -> BotResponse:
        if not self._is_authorized(platform, user_id):
            return BotResponse("🔒 Unauthorized.")

        user_key = self._user_key(platform, user_id)

        # Always normalize the first token and route core commands here
        cmd = self._normalize_cmd(text)

        if cmd in ("start",):
            return self._help()

        if cmd in ("help", "h", "?"):
            return self._help()
        if cmd in ("privacy",):
            return self._privacy()
        if cmd in ("whoami", "me"):
            return self._whoami(user_id, user_name)
        if cmd in ("confirm", "yes"):
            return await self._handle_confirm(user_key)
        if cmd in ("cancel", "no"):
            return BotResponse("❌ Cancelled")
        if cmd in ("balance", "bal", "b", "portfolio"):
            return await self._balance()
        if cmd in ("pnl", "p&l"):
            return await self._pnl()
        if cmd in ("roi",):
            return await self._roi()
        if cmd in ("history", "hist"):
            return self._history()
        if cmd in ("quit", "exit", "stop"):
            return BotResponse("🛑 EasyApe runs as a service. To stop it: `systemctl stop easyape`")

        # Stake/unstake use the structured parser
        action = parse_message(text)

        if isinstance(action, Help):
            return self._help()
        if isinstance(action, Privacy):
            return self._privacy()
        if isinstance(action, Whoami):
            return self._whoami(user_id, user_name)
        if isinstance(action, Confirm):
            return await self._handle_confirm(user_key)
        if isinstance(action, ParsedStake):
            return await self._handle_stake_action(action, user_key)
        if isinstance(action, Unknown):
            return BotResponse("❓ Unknown command.\n\nType `help` to see available commands.")

        return BotResponse("❓ Unknown command.")

    def handle_text(self, platform, user_id, user_name, chat_id, is_group, text):
        return asyncio.get_event_loop().run_until_complete(
            self.handle_text_async(platform, user_id, user_name, chat_id, is_group, text)
        )

    async def handle_callback_async(
        self,
        platform=None,
        user_id=None,
        user_name=None,
        action=None,
        callback_data=None,
        **kwargs,
    ) -> BotResponse:
        if not self._is_authorized(platform or "", user_id or 0):
            return BotResponse("🔒 Unauthorized.")

        if not action and callback_data:
            parts = str(callback_data).split("|")
            if len(parts) >= 2:
                action = parts[1]

        return await self._dispatch_action(action, platform, user_id)

    def handle_callback(self, platform=None, user_id=None, user_name=None,
                        action=None, callback_data=None, **kwargs):
        return asyncio.get_event_loop().run_until_complete(
            self.handle_callback_async(
                platform=platform, user_id=user_id, user_name=user_name,
                action=action, callback_data=callback_data, **kwargs,
            )
        )

    # ── Stake / Unstake flow ──────────────────────────────────────────────────

    async def _handle_stake_action(self, action: ParsedStake, user_key: str) -> BotResponse:
        netuid = action.netuid if action.netuid is not None else self._default_netuid()
        if netuid is None:
            return BotResponse("❓ Please specify a netuid.\nExample: `stake 0.5 31`")

        if action.op == "add":
            return await self._confirm_stake(action.amount, netuid, user_key)
        else:
            # UPDATED: treat None as "all" (parser may set amount=None for "unstake all")
            is_all = (
                action.amount is None
                or action.amount == 0
                or str(action.amount).lower() == "all"
            )
            if is_all:
                return await self._confirm_unstake_all(netuid, user_key)
            return await self._confirm_unstake(action.amount, netuid, user_key)

    async def _confirm_stake(self, amount: float, netuid: int, user_key: str) -> BotResponse:
        wallet = await self._get_wallet()

        if self.cfg.app.mode == "dry":
            return BotResponse(
                f"🧪 *DRY MODE*\n\nWould stake `{amount:.4f} τ` → Subnet `{netuid}`\n_(no transaction sent)_"
            )

        # ✅ OPTIONAL UPGRADE: show available balance, current rate, est alpha, slippage notice
        free_tao = None
        rate_now = None
        est_alpha = None
        try:
            bal = await self._btclient.get_balance(wallet)
            free_tao = bal.free_tao
        except Exception:
            pass
        try:
            rate_now = await self._btclient.get_exchange_rate(netuid)
        except Exception:
            pass
        if rate_now and rate_now > 0:
            est_alpha = amount / rate_now

        # ✅ OPTIONAL UPGRADE: if clearly insufficient balance, tell them up-front (still allow cancel)
        if free_tao is not None and free_tao < amount:
            return BotResponse(
                "❌ Not enough balance\n\n"
                f"Available: `{free_tao:.6f} τ`\n"
                f"Required:  `{amount:.6f} τ`"
            )

        needs_confirm = (
            self.cfg.app.require_confirmation
            and amount >= self.cfg.app.confirm_over_tao
        )

        if needs_confirm:
            action_str = f"stake_confirm:{amount}:{netuid}"
            self._pending.save(user_key, action_str, self.cfg.app.confirm_ttl_seconds)

            extra_lines = []
            if free_tao is not None:
                extra_lines.append(f"  Available: `{free_tao:.4f} τ`")
            if rate_now is not None and rate_now > 0:
                extra_lines.append(f"  Rate:      `{rate_now:.6f} τ/α`")
            if est_alpha is not None:
                extra_lines.append(f"  Est α:     `{est_alpha:.6f} α`")

            extra = ("\n" + "\n".join(extra_lines) + "\n") if extra_lines else "\n"
            slippage = (
                "\nℹ️ Final execution price may vary slightly due to subnet price impact / slippage."
                if rate_now is not None
                else ""
            )

            return BotResponse(
                text=(
                    f"⚠️ *Confirm Stake*\n\n"
                    f"  Subnet:   `{netuid}`\n"
                    f"  Amount:   `{amount:.4f} τ`\n"
                    f"  Wallet:   `{wallet.name}`"
                    f"{extra}"
                    f"Press **Confirm** or type `confirm`"
                    f"{slippage}"
                ),
                buttons=[[Button("✅ Confirm", f"stake_confirm:{amount}:{netuid}"),
                          Button("❌ Cancel", "cancel")]],
            )

        return await self._stake(amount, netuid)

    async def _confirm_unstake(self, amount: float, netuid: int, user_key: str) -> BotResponse:
        wallet = await self._get_wallet()

        if self.cfg.app.mode == "dry":
            return BotResponse(
                f"🧪 *DRY MODE*\n\nWould unstake `{amount:.4f} α` from Subnet `{netuid}`\n_(no transaction sent)_"
            )

        # UPDATED: guard None before numeric compare (prevents None >= float crash)
        needs_confirm = (
            self.cfg.app.require_confirmation
            and amount is not None
            and amount >= self.cfg.app.confirm_over_tao
        )

        if needs_confirm:
            action_str = f"unstake_confirm:{amount}:{netuid}"
            self._pending.save(user_key, action_str, self.cfg.app.confirm_ttl_seconds)
            return BotResponse(
                text=(
                    f"⚠️ *Confirm Unstake*\n\n"
                    f"  Subnet:  `{netuid}`\n"
                    f"  Amount:  `{amount:.4f} α`\n"
                    f"  Wallet:  `{wallet.name}`\n\n"
                    f"Press **Confirm** or type `confirm`"
                ),
                buttons=[[Button("✅ Confirm", f"unstake_confirm:{amount}:{netuid}"),
                          Button("❌ Cancel", "cancel")]],
            )

        return await self._unstake(amount, netuid)

    async def _confirm_unstake_all(self, netuid: int, user_key: str) -> BotResponse:
        wallet = await self._get_wallet()

        if self.cfg.app.mode == "dry":
            return BotResponse(
                f"🧪 *DRY MODE*\n\nWould unstake **ALL** alpha from Subnet `{netuid}`\n_(no transaction sent)_"
            )

        alpha_amount = None
        rate_now = None
        est_tao = None

        # How much alpha is currently staked on this netuid?
        try:
            bal = await self._btclient.get_balance(wallet)
            for s in bal.stakes:
                if s["netuid"] == netuid:
                    alpha_amount = s["alpha"]
                    break
        except Exception:
            pass

        # Current τ/α rate for estimate
        try:
            rate_now = await self._btclient.get_exchange_rate(netuid)
        except Exception:
            pass

        if alpha_amount is not None and rate_now:
            est_tao = alpha_amount * rate_now

        lines = [
            f"🚨 *Confirm Unstake ALL*",
            "",
            f"  Subnet: `{netuid}`",
        ]

        if alpha_amount is not None:
            lines.append(f"  Alpha:  `{alpha_amount:.6f} α`")

        if rate_now is not None:
            lines.append(f"  Rate:   `{rate_now:.6f} τ/α`")

        if est_tao is not None:
            lines.append(f"  Est τ:  `{est_tao:.6f} τ`")

        if est_tao is not None:
            lines.append("")
            lines.append("ℹ️ Estimate only — final execution value may vary slightly due to slippage.")

        lines.append("")
        lines.append("This will remove **all** your alpha on this subnet.")
        lines.append("")
        lines.append("Press **Unstake ALL** to proceed.")

        action_str = f"unstake_all_confirm:{netuid}"
        self._pending.save(user_key, action_str, self.cfg.app.confirm_ttl_seconds)
        return BotResponse(
            text="\n".join(lines),
            buttons=[[Button("🔥 Unstake ALL", f"unstake_all_confirm:{netuid}"),
                      Button("❌ Cancel", "cancel")]],
        )

    async def _handle_confirm(self, user_key: str) -> BotResponse:
        pending = self._pending.pop(user_key)
        if not pending:
            return BotResponse("⏰ No pending action (or it expired).")
        return await self._dispatch_action(pending, None, None)

    async def _dispatch_action(self, action: Optional[str], platform, user_id) -> BotResponse:
        if not action:
            return BotResponse("❌ Invalid action")

        await self._get_wallet()

        if action == "cancel":
            return BotResponse("❌ Cancelled")

        if action.startswith("stake_confirm:"):
            _, amount, netuid = action.split(":")
            return await self._stake(float(amount), int(netuid))

        if action.startswith("unstake_confirm:"):
            _, amount, netuid = action.split(":")
            return await self._unstake(float(amount), int(netuid))

        if action.startswith("unstake_all_confirm:"):
            _, netuid = action.split(":")
            return await self._unstake(None, int(netuid))

        return BotResponse("❌ Unknown action")

    # ── Execution ─────────────────────────────────────────────────────────────

    async def _stake(self, amount: float, netuid: int) -> BotResponse:
        wallet = await self._get_wallet()
        hotkey = self._default_hotkey()

        # ✅ REQUIRED: pre-flight balance check (prevents false "confirmed")
        try:
            bal = await self._btclient.get_balance(wallet)
            if bal.free_tao < amount:
                return BotResponse(
                    "❌ Not enough balance\n\n"
                    f"Available: `{bal.free_tao:.6f} τ`\n"
                    f"Required:  `{amount:.6f} τ`"
                )
        except Exception:
            # If balance read fails, still attempt stake; SDK layer should also guard.
            pass

        result: StakeResult = await self._btclient.add_stake(
            wallet=wallet,
            tao=amount,
            netuid=netuid,
            hotkey_ss58=hotkey,
        )

        if not result.ok:
            return BotResponse(f"❌ Stake failed\n\n`{result.message}`")

        append_jsonl(HISTORY_FILE, {
            "type":         "stake",
            "netuid":       netuid,
            "tao_spent":    result.tao_amount,
            "alpha_bought": result.alpha_amount,
            "rate":         result.rate,
        })

        # ✅ OPTIONAL: show entry + cost basis explicitly
        entry_price = result.rate
        cost_basis = result.tao_amount

        return BotResponse(
            f"✅ *Stake Confirmed*\n\n"
            f"  Subnet:     `{netuid}`\n"
            f"  Spent:      `{result.tao_amount:.4f} τ`\n"
            f"  Received:   `{result.alpha_amount:.6f} α`\n"
            f"  Rate:       `{result.rate:.6f} τ/α`\n"
            f"  Entry:      `{entry_price:.6f} τ/α`\n"
            f"  Cost Basis: `{cost_basis:.4f} τ`"
        )

    async def _unstake(self, amount: Optional[float], netuid: int) -> BotResponse:
        wallet = await self._get_wallet()
        hotkey = self._default_hotkey()

        result: StakeResult = await self._btclient.remove_stake(
            wallet=wallet,
            netuid=netuid,
            tao=amount,
            hotkey_ss58=hotkey,
        )

        if not result.ok:
            return BotResponse(f"❌ Unstake failed\n\n`{result.message}`")

        history = self._load_history()
        tao_spent_total = sum(t.get("tao_spent", 0.0) for t in history if t.get("type") == "stake" and t.get("netuid") == netuid)
        alpha_bought_total = sum(t.get("alpha_bought", 0.0) for t in history if t.get("type") == "stake" and t.get("netuid") == netuid)
        avg_entry = tao_spent_total / alpha_bought_total if alpha_bought_total else 0.0
        cost_basis = avg_entry * result.alpha_amount
        pnl = result.tao_amount - cost_basis
        roi = pnl / cost_basis * 100 if cost_basis else 0.0
        color = "🟢" if pnl >= 0 else "🔴"

        append_jsonl(HISTORY_FILE, {
            "type":         "unstake",
            "netuid":       netuid,
            "alpha_sold":   result.alpha_amount,
            "tao_received": result.tao_amount,
            "pnl":          pnl,
            "roi":          roi,
        })

        pnl_line = f"\n  PnL:       {color} `{pnl:+.4f} τ`\n  ROI:       {color} `{roi:+.2f}%`" if cost_basis else ""
        all_tag = " *(all)*" if amount is None else ""

        return BotResponse(
            f"✅ *Unstake Confirmed*\n\n"
            f"  Subnet:    `{netuid}`{all_tag}\n"
            f"  Sold:      `{result.alpha_amount:.6f} α`\n"
            f"  Received:  `{result.tao_amount:.4f} τ`\n"
            f"  Rate:      `{result.rate:.6f} τ/α`"
            f"{pnl_line}"
        )

    # ── Portfolio ─────────────────────────────────────────────────────────────

    async def _balance(self) -> BotResponse:
        wallet = await self._get_wallet()
        bal = await self._btclient.get_balance(wallet)
        history = self._load_history()

        lines = [f"🦍 *Portfolio*\n"]
        lines.append(f"  Free Balance: `{bal.free_tao:.4f} τ`\n")

        total_value = 0.0
        total_cost = 0.0
        unrealized = 0.0

        for stake in sorted(bal.stakes, key=lambda s: s["tao_value"], reverse=True):
            netuid = stake["netuid"]
            alpha = stake["alpha"]
            tao_value = stake["tao_value"]
            rate = stake["rate"]

            tao_in = sum(t.get("tao_spent", 0.0) for t in history if t.get("type") == "stake" and t.get("netuid") == netuid)
            alpha_in = sum(t.get("alpha_bought", 0.0) for t in history if t.get("type") == "stake" and t.get("netuid") == netuid)
            entry = tao_in / alpha_in if alpha_in else 0.0
            cost_basis = entry * alpha
            pnl = tao_value - cost_basis
            roi = pnl / cost_basis * 100 if cost_basis else 0.0
            color = "🟢" if pnl >= 0 else "🔴"

            total_value += tao_value
            total_cost += cost_basis
            unrealized += pnl

            lines.append(f"**SN{netuid}**")
            lines.append(f"  Alpha: `{alpha:.4f} α`  ≈  `{tao_value:.4f} τ`")
            lines.append(f"  Rate:  `{rate:.6f} τ/α`")
            if cost_basis:
                lines.append(f"  Entry: `{entry:.6f} τ/α`  |  Cost: `{cost_basis:.4f} τ`")
                lines.append(f"  PnL:   {color} `{pnl:+.4f} τ`  |  ROI: `{roi:+.2f}%`")
            lines.append("")

        realized = sum(t.get("pnl", 0.0) for t in history if t.get("type") == "unstake")

        capital_deployed = sum(
            t.get("tao_spent", 0.0)
            for t in history
            if t.get("type") == "stake"
        )

        total_pnl = unrealized + realized
        port_roi = total_pnl / capital_deployed * 100 if capital_deployed else 0.0
        open_roi = unrealized / total_cost * 100 if total_cost else 0.0
        realized_roi = realized / capital_deployed * 100 if capital_deployed else 0.0

        port_color = "🟢" if total_pnl >= 0 else "🔴"
        open_color = "🟢" if unrealized >= 0 else "🔴"
        realized_color = "🟢" if realized >= 0 else "🔴"

        if total_cost:
            lines.insert(2, f"  Portfolio PnL (total): {port_color} `{total_pnl:+.4f} τ`")
            lines.insert(3, f"  Portfolio ROI:        {port_color} `{port_roi:+.2f}%`")
            lines.insert(4, f"  Open ROI:             {open_color} `{open_roi:+.2f}%`")
            lines.insert(5, f"  Realized ROI:         {realized_color} `{realized_roi:+.2f}%`\n")

        lines.append("─────────────────")
        lines.append("*Portfolio Summary*")
        lines.append(f"  Staked Value:    `{total_value:.4f} τ`")
        if total_cost:
            lines.append(f"  Cost Basis:      `{total_cost:.4f} τ`")
            lines.append(f"  Unrealized PnL:  `{unrealized:+.4f} τ`")
            lines.append(f"  Realized PnL:    `{realized:+.4f} τ`")
            lines.append(f"  Total PnL:       {port_color} `{total_pnl:+.4f} τ`")
            lines.append(f"  Portfolio ROI:   {port_color} `{port_roi:+.2f}%`")
            lines.append(f"  Open ROI:        {open_color} `{open_roi:+.2f}%`")
            lines.append(f"  Realized ROI:    {realized_color} `{realized_roi:+.2f}%`")

        return BotResponse("\n".join(lines))

    async def _pnl(self) -> BotResponse:
        wallet = await self._get_wallet()
        bal = await self._btclient.get_balance(wallet)
        history = self._load_history()

        if not bal.stakes and not history:
            return BotResponse("📊 No stake history found.")

        lines = ["📈 *P&L Summary*\n"]
        total_unrealized = 0.0
        total_realized = 0.0

        for stake in sorted(bal.stakes, key=lambda s: s["tao_value"], reverse=True):
            netuid = stake["netuid"]
            tao_value = stake["tao_value"]
            alpha = stake["alpha"]

            tao_in = sum(t.get("tao_spent", 0.0) for t in history if t.get("type") == "stake" and t.get("netuid") == netuid)
            alpha_in = sum(t.get("alpha_bought", 0.0) for t in history if t.get("type") == "stake" and t.get("netuid") == netuid)
            entry = tao_in / alpha_in if alpha_in else 0.0
            cost = entry * alpha
            pnl = tao_value - cost
            color = "🟢" if pnl >= 0 else "🔴"
            total_unrealized += pnl

            if cost:
                lines.append(f"  SN{netuid:>3}  {color} `{pnl:+.4f} τ`")

        for rec in history:
            if rec.get("type") == "unstake":
                total_realized += rec.get("tao_received", 0.0)

        lines.append("")
        color = "🟢" if total_unrealized >= 0 else "🔴"
        lines.append(f"  Unrealized: {color} `{total_unrealized:+.4f} τ`")
        lines.append(f"  Realized:   `{total_realized:+.4f} τ`")

        return BotResponse("\n".join(lines))

    async def _roi(self) -> BotResponse:
        wallet = await self._get_wallet()
        bal = await self._btclient.get_balance(wallet)
        history = self._load_history()

        if not bal.stakes:
            return BotResponse("💹 No active stakes.")

        lines = ["💹 *ROI by Subnet*\n"]
        for stake in sorted(bal.stakes, key=lambda s: s["tao_value"], reverse=True):
            netuid = stake["netuid"]
            tao_value = stake["tao_value"]
            alpha = stake["alpha"]

            tao_in = sum(t.get("tao_spent", 0.0) for t in history if t.get("type") == "stake" and t.get("netuid") == netuid)
            alpha_in = sum(t.get("alpha_bought", 0.0) for t in history if t.get("type") == "stake" and t.get("netuid") == netuid)
            entry = tao_in / alpha_in if alpha_in else 0.0
            cost = entry * alpha
            roi = (tao_value - cost) / cost * 100 if cost else 0.0
            color = "🟢" if roi >= 0 else "🔴"
            roi_str = f"`{roi:+.2f}%`" if cost else "—"
            lines.append(f"  SN{netuid:>3}  {color} {roi_str}  (`{tao_value:.4f} τ`)")

        return BotResponse("\n".join(lines))

    # ── History ───────────────────────────────────────────────────────────────

    def _history(self) -> BotResponse:
        history = self._load_history()
        if not history:
            return BotResponse("📜 No transaction history.")

        lines = ["📜 *Transaction History*\n"]
        for t in reversed(history[-20:]):
            ts = t.get("ts", "")[:16]
            kind = t.get("type", "?")
            nid = t.get("netuid", "?")
            if kind == "stake":
                lines.append(f"  `{ts}`  ➕ Stake SN{nid}  `{t.get('tao_spent', 0):.4f} τ` → `{t.get('alpha_bought', 0):.4f} α`")
            elif kind == "unstake":
                lines.append(f"  `{ts}`  ➖ Unstake SN{nid}  `{t.get('alpha_sold', 0):.4f} α` → `{t.get('tao_received', 0):.4f} τ`")

        return BotResponse("\n".join(lines))

    def _load_history(self) -> list[dict]:
        if not os.path.exists(HISTORY_FILE):
            return []
        records = []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass
        return records

    # ── Info ──────────────────────────────────────────────────────────────────

    def _help(self) -> BotResponse:
        return BotResponse(
            "🦍 *EasyApe Commands*\n\n"
            "*Portfolio*\n"
            "  `balance` / `bal` / `portfolio`\n"
            "  `pnl`\n"
            "  `roi`\n"
            "  `history`\n\n"
            "*Staking*\n"
            "  `stake <amount> <netuid>`\n"
            "  `unstake <amount> <netuid>`\n"
            "  `unstake all <netuid>`\n"
            "*Examples*\n"
            "  `stake 0.5 31`\n"
            "  `unstake 0.25 31`\n"
            "  `balance -`  _(also works)_"
        )

    def _privacy(self) -> BotResponse:
        return BotResponse(
            "🔒 *Privacy*\n\n"
            "EasyApe does not transmit your wallet keys or seed phrases.\n"
            "Transaction history is stored locally on your server.\n"
            "Your Telegram/Discord user ID is used only for authorization."
        )

    def _whoami(self, user_id: int, user_name: str) -> BotResponse:
        wallet_name = self._wallet.name if self._wallet else "—"
        ss58 = ""
        try:
            ss58 = self._wallet.coldkey.ss58_address[:12] + "…"
        except Exception:
            pass
        return BotResponse(
            f"👤 *You*\n\n"
            f"  Name:    `{user_name}`\n"
            f"  ID:      `{user_id}`\n"
            f"  Wallet:  `{wallet_name}`\n"
            f"  Address: `{ss58}`"
        )
