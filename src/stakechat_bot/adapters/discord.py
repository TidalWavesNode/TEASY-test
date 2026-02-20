"""
stakechat_bot.adapters.discord
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Discord adapter.

Changes from original:
  - Engine called with await (async methods)
  - Button callback data fixed (was passing b.op / b.amount / b.netuid which
    don't exist on the Button dataclass)
  - Buttons disabled after use to prevent double-clicks
  - send_message chunked for messages > 2000 chars
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

from ..engine import Engine, Button

logger = logging.getLogger(__name__)

MAX_DISCORD_MSG = 1900  # Discord limit is 2000; leave headroom


class DiscordAdapter:
    def __init__(self, token: str, engine: Engine):
        self.token  = token
        self.engine = engine
        self.bot: Optional[commands.Bot] = None

    async def run(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        self.bot = commands.Bot(command_prefix="!", intents=intents)

        @self.bot.event
        async def on_ready():
            logger.info("Discord bot connected as %s", self.bot.user)

        @self.bot.event
        async def on_message(message: discord.Message):
            if message.author.bot:
                return

            text = (message.content or "").strip()
            if not text:
                return

            async with message.channel.typing():
                try:
                    resp = await self.engine.handle_text_async(
                        platform="discord",
                        user_id=int(message.author.id),
                        user_name=message.author.display_name,
                        chat_id=str(message.channel.id),
                        is_group=message.guild is not None,
                        text=text,
                    )
                except Exception as exc:
                    logger.exception("Engine error on Discord message")
                    await message.channel.send("❌ Error processing command.")
                    return

            if resp.buttons:
                view = _build_view(resp.buttons, self.engine)
                await _send_chunked(message.channel, resp.text, view=view)
            else:
                await _send_chunked(message.channel, resp.text)

        await self.bot.start(self.token)

    async def shutdown(self) -> None:
        if self.bot:
            await self.bot.close()


# ── Button view builder ───────────────────────────────────────────────────────

def _build_view(button_rows: list[list[Button]], engine: Engine) -> discord.ui.View:
    view = discord.ui.View(timeout=300)

    for row in button_rows:
        for b in row:
            action_str = b.action

            btn = discord.ui.Button(
                label=b.text,
                style=(
                    discord.ButtonStyle.danger
                    if "cancel" in action_str.lower()
                    else discord.ButtonStyle.success
                ),
            )

            async def callback(
                interaction: discord.Interaction,
                _action=action_str,
                _view=view,
            ):
                await interaction.response.defer()

                # Disable all buttons immediately
                for item in _view.children:
                    if isinstance(item, discord.ui.Button):
                        item.disabled = True

                try:
                    await interaction.edit_original_response(
                        content="⏳ Processing…",
                        view=_view,
                    )
                except Exception:
                    pass

                try:
                    resp = await engine.handle_callback_async(
                        platform="discord",
                        user_id=int(interaction.user.id),
                        user_name=interaction.user.name,
                        callback_data=f"easyape|{_action}|0",
                    )
                    await interaction.edit_original_response(
                        content=_discord_fmt(resp.text),
                        view=_view,
                    )
                except Exception as exc:
                    logger.exception("Discord callback error")
                    await interaction.edit_original_response(
                        content="❌ Error processing request.",
                        view=_view,
                    )

            btn.callback = callback
            view.add_item(btn)

    return view


# ── Helpers ───────────────────────────────────────────────────────────────────

def _discord_fmt(text: str) -> str:
    """Convert Telegram Markdown (*bold*, `code`) to Discord Markdown (**bold**, `code`)."""
    import re
    # *text* → **text**
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"**\1**", text)
    return text


async def _send_chunked(channel, text: str, view=None) -> None:
    """Send a message, splitting into chunks if over Discord's limit."""
    text = _discord_fmt(text)
    chunks = [text[i:i+MAX_DISCORD_MSG] for i in range(0, len(text), MAX_DISCORD_MSG)]
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1 and view:
            await channel.send(chunk, view=view)
        else:
            await channel.send(chunk)


async def run_discord_bot(token: str, engine: Engine) -> None:
    adapter = DiscordAdapter(token, engine)
    await adapter.run()
