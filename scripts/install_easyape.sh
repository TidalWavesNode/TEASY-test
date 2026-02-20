#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
CONFIG_FILE="${ROOT_DIR}/config.yaml"
ENV_FILE="${ROOT_DIR}/.env"
SERVICE_FILE="/etc/systemd/system/easyape.service"
WALLETS_DIR="/root/.bittensor/wallets"

DEFAULT_VALIDATOR="5E2LP6EnZ54m3wS8s1yPvD5c3xo71kQroBw7aUVK32TKeZ5u"

CYAN="\033[0;36m"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
NC="\033[0m"

info()    { echo -e "${CYAN}➜${NC}  $1"; }
success() { echo -e "${GREEN}✅${NC}  $1"; }
warn()    { echo -e "${RED}⚠️${NC}   $1"; }
note()    { echo -e "${YELLOW}ℹ️${NC}   $1"; }

clear
echo
echo -e "${CYAN}🦍 EasyApe Installer${NC}"
echo "──────────────────────────────────────────────────"

echo
info "Preparing Python environment..."

python3 -m venv "$VENV_DIR" || true
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt
"$VENV_DIR/bin/pip" install -e .

success "Environment ready"

echo
info "Scanning Bittensor wallets..."

if [[ -d "$WALLETS_DIR" ]]; then
    mapfile -t WALLETS < <(find "$WALLETS_DIR" -mindepth 1 -maxdepth 1 -type d -printf "%f\n")
else
    WALLETS=()
fi

echo
if [[ ${#WALLETS[@]} -gt 0 ]]; then
    note "Detected wallets:"
    i=1
    for w in "${WALLETS[@]}"; do
        echo "   [$i] $w"
        ((i++))
    done
    echo "   [N] Create new wallet"
else
    note "No wallets found"
    echo "   [N] Create new wallet"
fi

echo
read -r -p "Select wallet: " WALLET_SELECTION

if [[ "$WALLET_SELECTION" =~ ^[0-9]+$ ]] && [[ ${#WALLETS[@]} -gt 0 ]]; then
    WALLET_NAME="${WALLETS[$((WALLET_SELECTION-1))]}"
    echo
    success "Using existing wallet: $WALLET_NAME"

    read -r -s -p "Wallet password (leave blank if none): " WALLET_PASSWORD
    echo
else
    echo
    read -r -p "New wallet name [EasyApe]: " WALLET_NAME
    WALLET_NAME="${WALLET_NAME:-EasyApe}"

    read -r -s -p "Set wallet password (optional): " WALLET_PASSWORD
    echo

    info "Creating new coldkey..."

    "$VENV_DIR/bin/python" <<PY
import bittensor as bt

wallet = bt.Wallet(name="${WALLET_NAME}", path="${WALLETS_DIR}")
mnemonic = wallet.create_new_coldkey(
    use_password=bool("${WALLET_PASSWORD}"),
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
PY

    echo
    read -r -p "Press ENTER after safely storing mnemonic..."
fi

# ─────────────────────────────────────────────
# ✅ UPDATED VALIDATOR BLOCK (ONLY CHANGE)
# ─────────────────────────────────────────────

echo
echo -e "${CYAN}Validator Configuration${NC}"
echo "──────────────────────────────────────────────────"

note "EasyApe requires a default validator hotkey."
note "This is where your TAO will be delegated by default."
echo
note "👉 You may PASTE your preferred validator hotkey below."
note "👉 Or press ENTER to use the recommended default (tao.bot):"
echo
echo "   ${DEFAULT_VALIDATOR}"
echo

while true; do
    read -r -p "Default validator hotkey: " VALIDATOR_INPUT
    VALIDATOR_INPUT="${VALIDATOR_INPUT:-$DEFAULT_VALIDATOR}"

    if [[ "$VALIDATOR_INPUT" =~ ^[1-9A-HJ-NP-Za-km-z]{47,48}$ ]]; then
        break
    fi

    echo
    warn "Invalid SS58 address format"
    note "Validator hotkeys are typically 48 characters"
    note "Example: 5Fxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    echo
done

echo
success "Validator selected:"
echo "   $VALIDATOR_INPUT"

# ─────────────────────────────────────────────

echo
info "Saving environment configuration..."

cat > "$ENV_FILE" <<ENV
EASYAPE_WALLET_NAME=${WALLET_NAME}
EASYAPE_WALLET_PASSWORD=${WALLET_PASSWORD}
ENV

chmod 600 "$ENV_FILE"

success ".env written"

echo
read -r -p "Enable Telegram bot? [Y/n]: " ENABLE_TELEGRAM
ENABLE_TELEGRAM="${ENABLE_TELEGRAM:-Y}"

TELEGRAM_TOKEN=""
TELEGRAM_IDS_BLOCK="    []"

if [[ "$ENABLE_TELEGRAM" =~ ^[Yy]$ ]]; then
    ENABLE_TELEGRAM="true"
    read -r -p "Telegram Bot Token: " TELEGRAM_TOKEN
    read -r -p "Telegram User ID: " TG_ID
    TELEGRAM_IDS_BLOCK="    - ${TG_ID}"
else
    ENABLE_TELEGRAM="false"
fi

echo
info "Writing config.yaml..."

cat > "$CONFIG_FILE" <<YAML
app:
  mode: live
  require_confirmation: true

defaults:
  netuid: 31
  validator: default

validators:
  default: ${VALIDATOR_INPUT}

telegram:
  enabled: ${ENABLE_TELEGRAM}
  bot_token: "${TELEGRAM_TOKEN}"

auth:
  telegram_user_ids:
${TELEGRAM_IDS_BLOCK}

btcli:
  default_wallet: main
  wallets:
    main:
      coldkey: "${WALLET_NAME}"
      wallets_dir: "${WALLETS_DIR}"
YAML

success "config.yaml written"

echo
info "Installing systemd service..."

cp systemd/easyape.service "$SERVICE_FILE"
sed -i "s|__EASYAPE_ROOT__|${ROOT_DIR}|g" "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable easyape
systemctl restart easyape

success "Service installed & started"

echo
success "EasyApe installation complete!"
echo
echo "📜 Logs:"
echo "journalctl -u easyape -f"
echo
