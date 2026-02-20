# 🦍 EasyApe — Text‑to‑Stake for Bittensor

EasyApe is a chat-based staking assistant for **Bittensor**. Use simple commands in **Telegram** or **Discord** to:
- Check wallet + stake balances
- Stake / unstake on a subnet (with confirmations)
- Track **portfolio PnL** + **ROI** (entry price + unrealized/realized)

> **Important:** EasyApe uses the **Bittensor Python SDK** for wallet + chain operations (fast, no subprocess parsing).  
> You still may see a `btcli:` section name in `config.yaml` for backwards compatibility — EasyApe does **not** spawn `btcli`.

---

## What you’ll set up

You will:
1. Clone this repo on your VPS (Ubuntu recommended)
2. Run the interactive installer
3. Add your Telegram bot token (and optionally Discord)
4. Start EasyApe as a systemd service
5. Use EasyApe from chat

This guide does **not** skip steps.

---

## Requirements

- A Linux VPS or server (Ubuntu 22.04+ recommended)
- Root or sudo access
- Python 3.10+
- A Telegram Bot token (required if Telegram is enabled)
- Optional: Discord bot token (only if you enable Discord)

---

## Step 1 — Download (clone) the repo

```bash
cd /root
git clone https://github.com/TidalWavesNode/T_EASY.git EasyApe
cd /root/EasyApe
```

If you already have it installed and want to update later, see **Updating EasyApe** below.

---

## Step 2 — Run the installer (fresh install)

The installer will:
- create a Python venv
- install dependencies
- optionally create a passwordless wallet coldkey
- generate `/root/EasyApe/config.yaml`
- install the systemd service file

Run:

```bash
bash scripts/install_easyape.sh
```

Follow the prompts carefully — the config file is generated from your answers.

---

## Step 3 — Configure EasyApe (config.yaml)

Your config is here:

```bash
nano /root/EasyApe/config.yaml
```

### 3A) Telegram setup (most common)

Make sure this exists and is filled in:

```yaml
telegram:
  enabled: true
  bot_token: "YOUR_TELEGRAM_BOT_TOKEN"
```

Also set **your Telegram user ID** so nobody else can use the bot:

```yaml
auth:
  telegram_user_ids:
    - 123456789
```

How to get your Telegram user ID:
- Message `@userinfobot` on Telegram and copy your numeric ID

✅ If `telegram.enabled: true` and `bot_token` is empty → the service will fail to start.

### 3B) Discord setup (optional)

```yaml
discord:
  enabled: true
  bot_token: "YOUR_DISCORD_BOT_TOKEN"

auth:
  discord_user_ids:
    - 123456789012345678
```

Leave Discord disabled if you aren’t using it.

---

## Step 4 — Start the service

Reload systemd and start EasyApe:

```bash
systemctl daemon-reload
systemctl enable easyape
systemctl restart easyape
```

Check status:

```bash
systemctl status easyape
```

Watch logs live:

```bash
journalctl -u easyape -f
```

---

## Step 5 — Use EasyApe (commands)

Open Telegram (or Discord) and message your bot.

### Help

```
help
```

### Balance / portfolio

```
balance
```

You’ll see:
- Free TAO
- Stakes by subnet
- Entry price (if you’ve staked through EasyApe)
- Per-subnet PnL + ROI (🟢 gain / 🔴 loss)
- Portfolio PnL + Portfolio ROI

### Stake TAO

```
stake 0.5 31
```

Stake **0.5 TAO** on **netuid 31**.  
If confirmations are enabled, you’ll be asked to confirm.

### Unstake TAO

```
unstake 0.25 31
```

Unstake **0.25 TAO** from netuid 31.

### Unstake all

```
unstake all 31
```

Unstakes all alpha from that subnet.

### PnL only

```
pnl
```

### ROI only

```
roi
```

### History

```
history
```

Shows your latest stake/unstake records (stored locally).

---

## Where data is stored

EasyApe stores a simple local history file used for entry price + ROI:

- `trade_history.jsonl` (repo root)

This file contains **only** transaction summaries (no private keys).  
You can delete it if you want to reset your entry/PnL tracking.

---

## Updating EasyApe

If you installed from git and want to pull updates:

```bash
cd /root/EasyApe
git fetch origin
git pull origin main
```

Restart:

```bash
systemctl restart easyape
journalctl -u easyape -n 100 --no-pager
```

If you have local changes that block pulling, either stash them:

```bash
git stash
git pull origin main
git stash pop
```

---

## Troubleshooting

### “Telegram enabled but token missing”

This means Telegram is on, but `bot_token` is blank.

Fix:

```yaml
telegram:
  enabled: true
  bot_token: "YOUR_TOKEN"
```

Then restart:

```bash
systemctl restart easyape
journalctl -u easyape -n 200 --no-pager
```

### Bot is running but replies “Unauthorized”

Your user ID isn’t in the allowlist.

Add your ID:

```yaml
auth:
  telegram_user_ids:
    - YOUR_NUMERIC_ID
```

Restart the service.

### Service crash loop / won’t start

Check logs:

```bash
journalctl -u easyape -n 200 --no-pager
```

Common causes:
- missing Telegram token (see above)
- malformed YAML (indentation matters)
- wrong file path (must be `/root/EasyApe/config.yaml` for the systemd unit)

---

## Security notes (read this)

- **Never** commit `config.yaml` to GitHub (it contains your bot tokens).
- Wallet keys are stored in your Bittensor wallet directory (default: `/root/.bittensor/wallets`).
- Use a dedicated wallet for bot usage.
- Restrict bot usage via `auth.telegram_user_ids` / `auth.discord_user_ids`.

---

## License

MIT (or project default).

