# Privacy

EasyApe is self-hosted. It does **not** send your chat commands, wallet info, or staking history to any third-party service.

## What EasyApe stores locally

- A JSONL log file (default: `./data/bot.log.jsonl`) containing:
  - timestamp
  - platform (telegram / discord)
  - user id
  - message text
  - action parsed
  - the btcli command that would run / did run
  - result (dry-run output or exit code)
- A small cache of delegate/validator metadata used to resolve names to hotkeys.

## What EasyApe does NOT store

- Your mnemonic
- Your private keys
- Your Telegram/Discord messages anywhere other than the local log file

## Tokens

Bot tokens live in `.env` (never commit this file).
