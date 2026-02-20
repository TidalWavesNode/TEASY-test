"""
stakechat_bot.adapters.telegram
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Telegram adapter.

Changes from original:
  - Engine is called with await (async methods) instead of asyncio.to_thread
  - Messages sent with parse_mode=Markdown for bold/code formatting
  - Auth user_id check now done inside engine, adapter stays thin
  - Graceful shutdown on SIGTERM
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import BadRequest

from ..engine import Engine

logger = logging.getLogger(__name__)


class TelegramAdapter:
    def __init__(self, token: str, engine: Engine):
        self.token  = token
        self.engine = engine
        self.app: Optional[Application] = None

    # ── Message handler ───────────────────────────────────────────────────────

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.effective_chat or not update.message:
            return

        text = (update.message.text or "").strip()
        if not text:
            return

        user_id  = int(update.effective_user.id)
        username = (
            update.effective_user.username
            or update.effective_user.full_name
            or "user"
        ).strip()

        # Send "typing" indicator while we process
        await update.effective_chat.send_action("typing")

        try:
            resp = await self.engine.handle_text_async(
                platform="telegram",
                user_id=user_id,
                user_name=username,
                chat_id=str(update.effective_chat.id),
                is_group=update.effective_chat.type in ("group", "supergroup"),
                text=text,
            )
        except Exception as exc:
            logger.exception("Engine error on message")
            await update.message.reply_text("❌ Internal error.")
            return

        markup = _build_markup(resp.buttons)
        await update.message.reply_text(
            resp.text,
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── Callback (button press) ───────────────────────────────────────────────

    async def _on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.callback_query or not update.effective_user:
            return

        q    = update.callback_query
        data = str(q.data or "")

        # ACK immediately to stop the spinner on the button
        try:
            await q.answer()
        except BadRequest:
            return

        user_id  = int(update.effective_user.id)
        username = (
            update.effective_user.username
            or update.effective_user.full_name
            or "user"
        ).strip()

        # Immediate UI feedback: disable the buttons and show spinner
        try:
            await q.edit_message_text("⏳ Processing…", parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass

        async def run_job():
            try:
                resp = await self.engine.handle_callback_async(
                    platform="telegram",
                    user_id=user_id,
                    user_name=username,
                    callback_data=data,
                )
                try:
                    await q.edit_message_text(
                        resp.text,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    if q.message:
                        await q.message.reply_text(
                            resp.text, parse_mode=ParseMode.MARKDOWN
                        )
            except Exception as exc:
                logger.exception("Callback job error")
                try:
                    await q.edit_message_text("❌ Error processing request.")
                except Exception:
                    pass

        asyncio.create_task(run_job())

    # ── Error handler ─────────────────────────────────────────────────────────

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Telegram error: %s", context.error)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        self.app = Application.builder().token(self.token).build()

        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        self.app.add_handler(MessageHandler(filters.COMMAND, self._on_message))
        self.app.add_handler(CallbackQueryHandler(self._on_callback, pattern=r"^easyape\|"))
        self.app.add_error_handler(self._on_error)

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)

        logger.info("Telegram adapter running")

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    async def shutdown(self) -> None:
        if not self.app:
            return
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_markup(buttons) -> Optional[InlineKeyboardMarkup]:
    if not buttons:
        return None
    rows = []
    for row in buttons:
        rows.append([
            InlineKeyboardButton(
                text=b.text,
                callback_data=f"easyape|{b.action}|{b.tx_id}",
            )
            for b in row
        ])
    return InlineKeyboardMarkup(rows)


async def run_telegram_bot(token: str, engine: Engine) -> None:
    adapter = TelegramAdapter(token, engine)
    await adapter.run()
