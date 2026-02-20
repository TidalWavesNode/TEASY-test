"""
stakechat_bot.config
~~~~~~~~~~~~~~~~~~~~
Config loader.

Changes from original:
  - btcli.path / btcli.common_args kept for backward compat (used to extract
    subtensor.network in engine.py) but no longer used for subprocess calls
  - channels.telegram.bot_token accepts both old key and new 'token' alias
  - Added app.confirm_over_tao default (was missing, caused AttributeError)
  - Added app.confirm_ttl_seconds alias for confirm_timeout_seconds
  - ValidatorsConfig now has cache_ttl_minutes + delegates_fallback_url
    so validators.py doesn't crash on resolution
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ──────────────────────────────────────────────────────────────────────────────
# ENV resolution
# ──────────────────────────────────────────────────────────────────────────────

def _env_resolve(val: Any) -> Any:
    if isinstance(val, str) and val.strip().lower().startswith("env:"):
        key = val.split(":", 1)[1].strip()
        return os.getenv(key, "")
    return val


def _deep_resolve(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _deep_resolve(_env_resolve(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_resolve(_env_resolve(v)) for v in obj]
    return _env_resolve(obj)


# ──────────────────────────────────────────────────────────────────────────────
# Config models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AppConfig:
    mode: str = "live"
    require_confirmation: bool = True
    confirm_over_tao: float = 0.0
    confirm_ttl_seconds: int = 300


@dataclass(frozen=True)
class AuthAllow:
    telegram_user_ids: List[int]
    discord_user_ids: List[int]


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""


@dataclass(frozen=True)
class DiscordConfig:
    enabled: bool = False
    bot_token: str = ""


@dataclass(frozen=True)
class ChannelsConfig:
    telegram: TelegramConfig
    discord: DiscordConfig


@dataclass(frozen=True)
class WalletProfile:
    coldkey: str
    wallets_dir: str
    password: str = ""
    default_netuid: Optional[int] = None
    validator_all: Optional[str] = None


@dataclass(frozen=True)
class BtcliConfig:
    """
    Kept for backward compat.  'path' and 'common_args' are read by engine.py
    to extract the subtensor network name but are NOT used for subprocess calls.
    """
    path: str
    default_wallet: str
    wallets: Dict[str, WalletProfile]
    wallets_path: Optional[str] = None
    common_args: Optional[List[str]] = None


@dataclass(frozen=True)
class ValidatorsConfig:
    aliases: Dict[str, str]
    delegates_fallback_url: str = (
        "https://raw.githubusercontent.com/opentensor/bittensor-delegates/main/public/delegates.json"
    )
    cache_ttl_minutes: int = 60


@dataclass(frozen=True)
class DefaultsConfig:
    netuid: Optional[int]
    validator: Optional[str]


@dataclass(frozen=True)
class RootConfig:
    app: AppConfig
    auth: AuthAllow
    channels: ChannelsConfig
    btcli: BtcliConfig
    validators: ValidatorsConfig
    defaults: DefaultsConfig


# ──────────────────────────────────────────────────────────────────────────────
# Loader
# ──────────────────────────────────────────────────────────────────────────────

def load_config(path: str | Path) -> RootConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")

    raw = yaml.safe_load(p.read_text()) or {}
    raw = _deep_resolve(raw)

    # ── APP ──────────────────────────────────────────────────────────────────
    app_raw = raw.get("app", {}) or {}
    confirm_ttl = int(
        app_raw.get("confirm_ttl_seconds")
        or app_raw.get("confirm_timeout_seconds")
        or 300
    )
    app_cfg = AppConfig(
        mode=str(app_raw.get("mode", "live")).lower(),
        require_confirmation=bool(app_raw.get("require_confirmation", True)),
        confirm_over_tao=float(app_raw.get("confirm_over_tao", 0.0)),
        confirm_ttl_seconds=confirm_ttl,
    )

    # ── AUTH ─────────────────────────────────────────────────────────────────
    auth_raw = raw.get("auth", {}) or {}
    tg_ids = auth_raw.get("telegram_user_ids") or auth_raw.get("allowed_telegram_users") or []
    dc_ids = auth_raw.get("discord_user_ids")  or auth_raw.get("allowed_discord_users")  or []
    auth_cfg = AuthAllow(
        telegram_user_ids=[int(x) for x in tg_ids],
        discord_user_ids= [int(x) for x in dc_ids],
    )

    # ── CHANNELS ─────────────────────────────────────────────────────────────
    telegram_raw = raw.get("telegram") or (raw.get("channels", {}) or {}).get("telegram", {}) or {}
    discord_raw  = raw.get("discord")  or (raw.get("channels", {}) or {}).get("discord",  {}) or {}

    telegram_cfg = TelegramConfig(
        enabled=bool(telegram_raw.get("enabled", False)),
        bot_token=str(telegram_raw.get("bot_token") or telegram_raw.get("token") or ""),
    )
    discord_cfg = DiscordConfig(
        enabled=bool(discord_raw.get("enabled", False)),
        bot_token=str(discord_raw.get("bot_token") or discord_raw.get("token") or ""),
    )
    channels_cfg = ChannelsConfig(telegram=telegram_cfg, discord=discord_cfg)

    # ── DEFAULTS ─────────────────────────────────────────────────────────────
    defaults_raw = raw.get("defaults", {}) or {}
    defaults_cfg = DefaultsConfig(
        netuid=(int(defaults_raw["netuid"]) if defaults_raw.get("netuid") not in (None, "") else None),
        validator=(str(defaults_raw["validator"]) if defaults_raw.get("validator") else None),
    )

    # ── VALIDATORS ───────────────────────────────────────────────────────────
    validators_raw = raw.get("validators", {}) or {}
    validators_cfg = ValidatorsConfig(
        aliases={str(k): str(v) for k, v in (validators_raw.get("aliases", {}) or {}).items()},
        delegates_fallback_url=str(
            validators_raw.get(
                "delegates_fallback_url",
                "https://raw.githubusercontent.com/opentensor/bittensor-delegates/main/public/delegates.json",
            )
        ),
        cache_ttl_minutes=int(validators_raw.get("cache_ttl_minutes", 60)),
    )

    # ── BTCLI (kept for network extraction + wallet profiles) ─────────────────
    bt_raw       = raw.get("btcli", {}) or {}
    wallets_raw  = bt_raw.get("wallets", {}) or {}
    wallets: Dict[str, WalletProfile] = {}

    for name, w in wallets_raw.items():
        wallets[str(name)] = WalletProfile(
            coldkey=str(w.get("coldkey") or w.get("wallet_name") or ""),
            wallets_dir=str(w.get("wallets_dir", os.path.expanduser("~/.bittensor/wallets"))),
            password=str(w.get("password", "")),
            default_netuid=(int(w["default_netuid"]) if w.get("default_netuid") not in (None, "", 0) else None),
            validator_all=(str(w["validator_all"]) if w.get("validator_all") else None),
        )

    default_wallet = str(bt_raw.get("default_wallet", "main"))

    btcli_cfg = BtcliConfig(
        path=str(bt_raw.get("path", "btcli")),
        default_wallet=default_wallet,
        wallets=wallets,
        wallets_path=bt_raw.get("wallets_path"),
        common_args=bt_raw.get("common_args") or [],
    )

    # ── SANITY CHECKS ────────────────────────────────────────────────────────
    if telegram_cfg.enabled and not telegram_cfg.bot_token:
        raise ValueError("Telegram is enabled but bot_token is missing in config.")
    if discord_cfg.enabled and not discord_cfg.bot_token:
        raise ValueError("Discord is enabled but bot_token is missing in config.")
    if default_wallet not in wallets:
        raise ValueError(
            f"btcli.default_wallet '{default_wallet}' not found in btcli.wallets. "
            f"Available: {list(wallets.keys())}"
        )

    return RootConfig(
        app=app_cfg,
        auth=auth_cfg,
        channels=channels_cfg,
        btcli=btcli_cfg,
        validators=validators_cfg,
        defaults=defaults_cfg,
    )
