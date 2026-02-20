#!/usr/bin/env bash

set -e

ROOT_DIR="/root/EasyApe"
VENV_DIR="${ROOT_DIR}/.venv"
CONFIG_FILE="${ROOT_DIR}/config.yaml"
SERVICE_FILE="/etc/systemd/system/easyape.service"

echo
echo "🦍 EasyApe Installer"
echo "────────────────────────────────────────────"

# ─────────────────────────────────────────────
# Ensure repo location
# ─────────────────────────────────────────────
mkdir -p "$ROOT_DIR"
cd "$ROOT_DIR"

# ─────────────────────────────────────────────
# Python / venv setup
# ─────────────────────────────────────────────
echo
echo "➜ Setting up Python virtual environment..."

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

echo "✅ venv ready"

# ─────────────────────────────────────────────
# Wallet configuration
# ─────────────────────────────────────────────
echo
read -r -p "Wallet name [EasyApe]: " WALLET_NAME
WALLET_NAME="${WALLET_NAME:-EasyApe}"

read -r -p "Wallet path [/root/.bittensor/wallets]: " WALLET_PATH
WALLET_PATH="${WALLET_PATH:-/root/.bittensor/wallets}"

echo
read -r -p "Create a new passwordless coldkey now? [Y/n]: " CREATE_WALLET
CREATE_WALLET="${CREATE_WALLET:-Y}"

if [[ "$CREATE_WALLET" =~ ^[Yy]$ ]]; then
    echo
    echo "➜ Creating coldkey '${WALLET_NAME}'..."

    "$VENV_DIR/bin/python" <<PY
import bittensor as bt

wallet = bt.Wallet(name="${WALLET_NAME}", path="${WALLET_PATH}")

mnemonic = wallet.create_new_coldkey(
    use_password=False,
    overwrite=False
)

print()
print("🔐 NEW WALLET CREATED")
print("────────────────────────────────────")
print("Wallet Name :", wallet.name)
print("Address     :", wallet.coldkey.ss58_address)
print()
print("🚨 SAVE THIS MNEMONIC PHRASE 🚨")
print(mnemonic)
print()
print("Store this securely.")
print("This is the ONLY way to recover your wallet.")
print()
PY

    echo
    read -p "Press ENTER once you have safely stored your mnemonic..."
fi

# ─────────────────────────────────────────────
# Telegram configuration
# ─────────────────────────────────────────────
echo
read -r -p "Enable Telegram bot? [Y/n]: " ENABLE_TELEGRAM
ENABLE_TELEGRAM="${ENABLE_TELEGRAM:-Y}"

TELEGRAM_TOKEN=""
TELEGRAM_IDS="    []"

if [[ "$ENABLE_TELEGRAM" =~ ^[Yy]$ ]]; then
    read -r -p "Telegram Bot Token: " TELEGRAM_TOKEN

    read -r -p "Your Telegram User ID: " TG_ID
    TELEGRAM_IDS="    - ${TG_ID}"
fi

# ─────────────────────────────────────────────
# Discord configuration (optional)
# ─────────────────────────────────────────────
echo
read -r -p "Enable Discord bot? [y/N]: " ENABLE_DISCORD
ENABLE_DISCORD="${ENABLE_DISCORD:-N}"

DISCORD_TOKEN=""
DISCORD_IDS="    []"

if [[ "$ENABLE_DISCORD" =~ ^[Yy]$ ]]; then
    read -r -p "Discord Bot Token: " DISCORD_TOKEN

    read -r -p "Your Discord User ID: " DC_ID
    DISCORD_IDS="    - ${DC_ID}"
fi

# ─────────────────────────────────────────────
# Write config.yaml
# ─────────────────────────────────────────────
echo
echo "➜ Writing config.yaml..."

cat > "$CONFIG_FILE" <<YAML
app:
  mode: live
  require_confirmation: true
  confirm_over_tao: 0.5
  confirm_ttl_seconds: 120

telegram:
  enabled: ${ENABLE_TELEGRAM}
  bot_token: "${TELEGRAM_TOKEN}"

discord:
  enabled: ${ENABLE_DISCORD}
  bot_token: "${DISCORD_TOKEN}"

auth:
  telegram_user_ids:
${TELEGRAM_IDS}
  discord_user_ids:
${DISCORD_IDS}

btcli:
  path: btcli
  default_wallet: main
  common_args:
    - --subtensor.network
    - finney
  wallets:
    main:
      coldkey: "${WALLET_NAME}"
      wallets_dir: "${WALLET_PATH}"
      password: ""
      validator_all: tao.bot
YAML

echo "✅ config.yaml written"

# ─────────────────────────────────────────────
# Install systemd service
# ─────────────────────────────────────────────
echo
echo "➜ Installing systemd service..."

cp systemd/easyape.service "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable easyape

echo "✅ systemd service installed"

# ─────────────────────────────────────────────
# Final start
# ─────────────────────────────────────────────
echo
echo "➜ Starting EasyApe..."

systemctl restart easyape

echo
echo "🎉 EasyApe installation complete!"
echo "Check logs:"
echo "journalctl -u easyape -f"
echo
