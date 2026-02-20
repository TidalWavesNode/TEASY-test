"""
stakechat_bot.main
~~~~~~~~~~~~~~~~~~
Entry point.

Changes from original:
  - Engine constructed once; both adapters share it
  - Graceful shutdown on SIGTERM / SIGINT
  - --doctor mode validates config + Subtensor connection
  - No reference to btcli path (not needed any more)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from stakechat_bot.config import load_config
from stakechat_bot.engine import Engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="EasyApe – text to stake")
    parser.add_argument("--config", type=str, default="config.yaml")
    parser.add_argument("--doctor", action="store_true", help="Validate config and exit")
    args = parser.parse_args()

    cfg_path = Path(args.config)

    if args.doctor:
        _doctor(cfg_path)
        return

    logger.info("🦍 Starting EasyApe…")

    cfg    = load_config(cfg_path)
    engine = Engine(cfg)

    asyncio.run(_run(cfg, engine))


async def _run(cfg, engine: Engine):
    tasks = []

    if cfg.channels.telegram.enabled:
        from stakechat_bot.adapters.telegram import run_telegram_bot
        tasks.append(asyncio.create_task(
            run_telegram_bot(cfg.channels.telegram.bot_token, engine)
        ))
        logger.info("Telegram adapter starting")

    if cfg.channels.discord.enabled:
        from stakechat_bot.adapters.discord import run_discord_bot
        tasks.append(asyncio.create_task(
            run_discord_bot(cfg.channels.discord.bot_token, engine)
        ))
        logger.info("Discord adapter starting")

    if not tasks:
        logger.error("No bots enabled. Set channels.telegram.enabled or channels.discord.enabled in config.yaml")
        return

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: [t.cancel() for t in tasks])

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutting down…")


def _doctor(cfg_path: Path):
    """Validate config and test Subtensor connection."""
    print(f"🩺 Doctor mode — checking {cfg_path}")

    try:
        cfg = load_config(cfg_path)
        print("✅ Config loaded OK")
    except Exception as exc:
        print(f"❌ Config error: {exc}")
        sys.exit(1)

    print(f"   Telegram: {'enabled' if cfg.channels.telegram.enabled else 'disabled'}")
    print(f"   Discord:  {'enabled' if cfg.channels.discord.enabled else 'disabled'}")
    print(f"   Wallets:  {list(cfg.btcli.wallets.keys())}")

    print("\n🔌 Testing Subtensor connection…")
    try:
        import bittensor as bt
        engine = Engine(cfg)
        loop = asyncio.new_event_loop()
        sub = loop.run_until_complete(engine._btclient.subtensor())
        print(f"✅ Connected: {sub.network}")
        loop.close()
    except Exception as exc:
        print(f"❌ Subtensor connection failed: {exc}")
        sys.exit(1)

    print("\n✅ All checks passed. EasyApe is ready.")


if __name__ == "__main__":
    main()
