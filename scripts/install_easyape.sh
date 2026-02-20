#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
CONFIG_FILE="${ROOT_DIR}/config.yaml"
SERVICE_FILE="/etc/systemd/system/easyape.service"

CYAN="\033[0;36m"
GREEN="\033[0;32m"
RED="\033[0;31m"
NC="\033[0m"

info()    { echo -e "${CYAN}➜${NC}  $1"; }
success() { echo -e "${GREEN}✅${NC}  $1"; }
warn()    { echo -e "${RED}⚠️${NC}   $1"; }

echo
echo -e "${CYAN}🦍 EasyApe Installer${NC}"
echo "──────────────────────────────────────────────────"

if [[ ! -f "${ROOT_DIR}/requirements.txt" ]]; then
    warn "requirements.txt missing"
    exit 1
fi

echo
info "Setting up virtual environment..."

python3 -m venv "$VENV_DIR" || true
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

# ✅ CRITICAL FIX — INSTALL EASYAPE ITSELF
"$VENV_DIR/bin/pip" install -e .

success "Environment ready"

echo
read -r -p "Wallet name [EasyApe]: " WALLET_NAME || true
WALLET_NAME="${WALLET_NAME:-EasyApe}"

WALLET_PATH="/root/.bittensor/wallets"

echo
read -r -p "Create passwordless coldkey? [Y/n]: " CREATE_WALLET || true
CREATE_WALLET="${CREATE_WALLET:-Y}"

if [[ "$CREATE_WALLET" =~ ^[Yy]$ ]]; then
    info "Creating coldkey..."

    "$VENV_DIR/bin/python" <<PY
import bittensor as bt

wallet = bt.Wallet(name="${WALLET_NAME}", path="${WALLET_PATH}")
mnemonic = wallet.create_new_coldkey(use_password=False, overwrite=False)

print()
print("🔐 NEW WALLET CREATED")
print("Wallet Name :", wallet.name)
print("Address     :", wallet.coldkey.ss58_address)
print()
print("🚨 SAVE THIS MNEMONIC 🚨")
print(mnemonic)
print()
PY

    read -r -p "Press ENTER after saving mnemonic..."
fi

echo
read -r -p "Enable Telegram bot? [Y/n]: " ENABLE_TELEGRAM || true
ENABLE_TELEGRAM="${ENABLE_TELEGRAM:-Y}"

TELEGRAM_TOKEN=""
TELEGRAM_USER_IDS_BLOCK="    []"

if [[ "$ENABLE_TELEGRAM" =~ ^[Yy]$ ]]; then
    ENABLE_TELEGRAM="true"
    read -r -p "Telegram Bot Token: " TELEGRAM_TOKEN
    read -r -p "Telegram User ID: " TG_ID
    TELEGRAM_USER_IDS_BLOCK="    - ${TG_ID}"
else
    ENABLE_TELEGRAM="false"
fi

echo
read -r -p "Enable Discord bot? [y/N]: " ENABLE_DISCORD || true
ENABLE_DISCORD="${ENABLE_DISCORD:-N}"

DISCORD_TOKEN=""
DISCORD_USER_IDS_BLOCK="    []"

if [[ "$ENABLE_DISCORD" =~ ^[Yy]$ ]]; then
    ENABLE_DISCORD="true"
    read -r -p "Discord Bot Token: " DISCORD_TOKEN
    read -r -p "Discord User ID: " DC_ID
    DISCORD_USER_IDS_BLOCK="    - ${DC_ID}"
else
    ENABLE_DISCORD="false"
fi

info "Writing config.yaml..."

cat > "$CONFIG_FILE" <<YAML
app:
  mode: live

telegram:
  enabled: ${ENABLE_TELEGRAM}
  bot_token: "${TELEGRAM_TOKEN}"

discord:
  enabled: ${ENABLE_DISCORD}
  bot_token: "${DISCORD_TOKEN}"

auth:
  telegram_user_ids:
${TELEGRAM_USER_IDS_BLOCK}
  discord_user_ids:
${DISCORD_USER_IDS_BLOCK}

btcli:
  default_wallet: main
  wallets:
    main:
      coldkey: "${WALLET_NAME}"
      wallets_dir: "${WALLET_PATH}"
YAML

success "config.yaml written"

info "Installing systemd service..."

cp systemd/easyape.service "$SERVICE_FILE"
sed -i "s|__EASYAPE_ROOT__|${ROOT_DIR}|g" "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable easyape
systemctl restart easyape

success "Installation complete!"
echo "View logs:"
echo "journalctl -u easyape -f"
echo
