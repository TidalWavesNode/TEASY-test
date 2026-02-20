"""
stakechat_bot.bittensor_client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SDK-native Bittensor operations. Replaces every btcli subprocess call.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

os.environ.setdefault("BT_NO_PARSE_CLI_ARGS", "1")

import bittensor as bt
from bittensor.utils.balance import Balance

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bt_io")


async def _offload(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, lambda: fn(*args, **kwargs))


# ──────────────────────────────────────────────────────────────────────────────
# Result types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class StakeResult:
    ok: bool
    message: str
    tao_amount: float = 0.0
    alpha_amount: float = 0.0
    netuid: int = 0
    hotkey: str = ""
    rate: float = 0.0


@dataclass
class BalanceResult:
    free_tao: float
    stakes: list[dict] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# BittensorClient
# ──────────────────────────────────────────────────────────────────────────────

class BittensorClient:

    def __init__(self, network: str = "finney", wallets_path: Optional[str] = None):
        self.network = network
        self.wallets_path = wallets_path or os.path.expanduser("~/.bittensor/wallets")
        self._sub: Optional[bt.Subtensor] = None
        self._lock = asyncio.Lock()
        self._wallet_cache: dict[str, bt.Wallet] = {}

    async def subtensor(self) -> bt.Subtensor:
        async with self._lock:
            if self._sub is None:
                logger.info("Connecting to Bittensor %s …", self.network)
                self._sub = await _offload(bt.Subtensor, network=self.network)
                logger.info("Connected to %s", self.network)
            return self._sub

    async def reconnect(self) -> bt.Subtensor:
        async with self._lock:
            self._sub = None
        return await self.subtensor()

    def load_wallet(
        self,
        coldkey_name: str,
        hotkey_name: str = "default",
        password: str = "",
    ) -> bt.Wallet:

        key = f"{coldkey_name}:{hotkey_name}"
        if key not in self._wallet_cache:
            w = bt.Wallet(
                name=coldkey_name,
                hotkey=hotkey_name,
                path=self.wallets_path,
            )
            if password:
                w.unlock_coldkey(password=password)
            else:
                try:
                    w.unlock_coldkey()
                except Exception:
                    pass
            self._wallet_cache[key] = w
        return self._wallet_cache[key]

    async def best_hotkey_for_netuid(
        self,
        sub: bt.Subtensor,
        coldkey_ss58: str,
        netuid: int,
    ) -> Optional[str]:

        try:
            stakes = await _offload(
                sub.get_stake_info_for_coldkey,
                coldkey_ss58=coldkey_ss58,
            )
            candidates = [s for s in stakes if s.netuid == netuid]
            if not candidates:
                return None
            return max(candidates, key=lambda s: float(s.stake)).hotkey_ss58
        except Exception:
            return None

    async def get_balance(self, wallet: bt.Wallet) -> BalanceResult:
        sub = await self.subtensor()

        def _fetch():
            free = sub.get_balance(wallet.coldkey.ss58_address)
            raw = sub.get_stake_info_for_coldkey(
                coldkey_ss58=wallet.coldkey.ss58_address
            )
            stakes = []

            # ✅ UPDATED: live subnet pricing instead of stake.tao
            price_cache = {}

            for s in raw:
                alpha = float(s.stake)

                if s.netuid not in price_cache:
                    try:
                        price_cache[s.netuid] = float(sub.get_subnet_price(s.netuid))
                    except Exception:
                        price_cache[s.netuid] = 0.0

                rate = price_cache[s.netuid]
                tao_value = alpha * rate if rate else 0.0

                stakes.append({
                    "netuid":    s.netuid,
                    "hotkey":    s.hotkey_ss58,
                    "alpha":     alpha,
                    "tao_value": tao_value,
                    "rate":      rate,
                })

            return float(free), stakes

        try:
            free_tao, stakes = await _offload(_fetch)
            return BalanceResult(free_tao=free_tao, stakes=stakes)
        except Exception:
            logger.exception("get_balance failed")
            return BalanceResult(free_tao=0.0)

    # ─────────────────────────────────────────────
    # Stake
    # ─────────────────────────────────────────────

    async def add_stake(
        self,
        wallet: bt.Wallet,
        tao: float,
        netuid: int,
        hotkey_ss58: Optional[str] = None,
    ) -> StakeResult:

        sub = await self.subtensor()

        if hotkey_ss58 is None:
            hotkey_ss58 = await self.best_hotkey_for_netuid(
                sub, wallet.coldkey.ss58_address, netuid
            )

        if not hotkey_ss58:
            return StakeResult(
                ok=False,
                message="❌ No validator hotkey available",
                netuid=netuid,
            )

        alpha_before = await self._alpha_on_netuid(
            sub, wallet.coldkey.ss58_address, netuid
        )

        amount = Balance.from_tao(tao)

        def _do():
            return sub.add_stake(
                wallet=wallet,
                hotkey_ss58=hotkey_ss58,
                netuid=netuid,
                amount=amount,
                wait_for_inclusion=True,
                wait_for_finalization=False,
            )

        try:
            ok = await _offload(_do)
        except Exception as exc:
            logger.exception("add_stake failed")
            return StakeResult(False, f"Chain error: {exc}", netuid=netuid)

        if not ok:
            return StakeResult(False, "Transaction rejected by chain", netuid=netuid)

        alpha_after = await self._alpha_on_netuid(
            sub, wallet.coldkey.ss58_address, netuid
        )

        alpha_received = max(0.0, alpha_after - alpha_before)
        rate = tao / alpha_received if alpha_received > 0 else 0.0

        return StakeResult(
            ok=True,
            message="Stake confirmed",
            tao_amount=tao,
            alpha_amount=alpha_received,
            netuid=netuid,
            hotkey=hotkey_ss58,
            rate=rate,
        )

    # ─────────────────────────────────────────────
    # Unstake
    # ─────────────────────────────────────────────

    async def remove_stake(
        self,
        wallet: bt.Wallet,
        netuid: int,
        tao: Optional[float] = None,
        hotkey_ss58: Optional[str] = None,
    ) -> StakeResult:

        sub = await self.subtensor()

        if hotkey_ss58 is None:
            hotkey_ss58 = await self.best_hotkey_for_netuid(
                sub, wallet.coldkey.ss58_address, netuid
            )

        if not hotkey_ss58:
            return StakeResult(False, "❌ No validator hotkey found", netuid=netuid)

        alpha_before = await self._alpha_on_netuid(
            sub, wallet.coldkey.ss58_address, netuid
        )
        tao_before = await self._free_tao(sub, wallet.coldkey.ss58_address)

        if tao is None:
            amount = Balance.from_tao(alpha_before).set_unit(netuid)
        else:
            amount = Balance.from_tao(tao)

        def _do():
            return sub.unstake(
                wallet=wallet,
                hotkey_ss58=hotkey_ss58,
                netuid=netuid,
                amount=amount,
                wait_for_inclusion=True,
                wait_for_finalization=False,
            )

        try:
            ok = await _offload(_do)
        except Exception as exc:
            logger.exception("remove_stake failed")
            return StakeResult(False, f"Chain error: {exc}", netuid=netuid)

        if not ok:
            return StakeResult(False, "Transaction rejected by chain", netuid=netuid)

        alpha_after = await self._alpha_on_netuid(
            sub, wallet.coldkey.ss58_address, netuid
        )
        tao_after = await self._free_tao(sub, wallet.coldkey.ss58_address)

        alpha_sold = max(0.0, alpha_before - alpha_after)
        tao_received = max(0.0, tao_after - tao_before)
        rate = tao_received / alpha_sold if alpha_sold > 0 else 0.0

        return StakeResult(
            ok=True,
            message="Unstake confirmed",
            tao_amount=tao_received,
            alpha_amount=alpha_sold,
            netuid=netuid,
            hotkey=hotkey_ss58,
            rate=rate,
        )

    # ─────────────────────────────────────────────

    async def _alpha_on_netuid(self, sub, coldkey_ss58, netuid):
        try:
            stakes = await _offload(
                sub.get_stake_info_for_coldkey,
                coldkey_ss58=coldkey_ss58,
            )
            return sum(float(s.stake) for s in stakes if s.netuid == netuid)
        except Exception:
            return 0.0

    async def _free_tao(self, sub, coldkey_ss58):
        try:
            bal = await _offload(sub.get_balance, coldkey_ss58)
            return float(bal)
        except Exception:
            return 0.0
