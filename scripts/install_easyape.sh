#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# EasyApe Installer  v2
# Supports: fresh install | upgrade | repair
# No longer requires Bittensor SDK — uses Bittensor Python SDK directly
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

die()     { echo -e "${RED}❌  $1${NC}" >&2; exit 1; }
info()    { echo -e "${BLUE}➜  $1${NC}"; }
success() { echo -e "${GREEN}✅  $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠️   $1${NC}"; }
header()  { echo -e "\n${CYAN}${BOLD}$1${NC}"; echo -e "${CYAN}$(printf '─%.0s' {1..50})${NC}"; }

clear
echo -e "${CYAN}${BOLD}"
cat << 'BANNER'
  ______                          _
 |  ____|                /\      | |
 | |__   __ _ ___ _   _ /  \  _ | |__   ___
 |  __| / _` / __| | | / /\ \| '_ \ / _ \
 | |___| (_| \__ \ |_| / ____ \ |_) |  __/
 |______\__,_|___/\__, /_/    \_____/ \___|
                   __/ |
                  |___/    🦍 Text to Stake v2
BANNER
echo -e "${NC}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
CONFIG_FILE="${ROOT_DIR}/config.yaml"
SERVICE_FILE="/etc/systemd/system/easyape.service"
PYTHON_MIN="3.10"

# ── Mode detection ─────────────────────────────────────────────────────────────
header "Installation Mode"

EXISTING=false
[[ -d "$VENV_DIR" || -f "$CONFIG_FILE" ]] && EXISTING=true
MODE="fresh"

if $EXISTING; then
  warn "Existing EasyApe installation found."
  echo
  echo "  1) Upgrade   — pull latest code, reinstall packages, keep config"
  echo "  2) Repair    — recreate venv, reinstall packages, keep config"
  echo "  3) Reinstall — full clean install (config will be rewritten)"
  echo
  read -r -p "$(echo -e "${CYAN}Choice [1]: ${NC}")" choice || true
  choice="${choice:-1}"
  case "$choice" in
    1) MODE="upgrade"   ;;
    2) MODE="repair"    ;;
    3) MODE="fresh"     ;;
    *) die "Invalid choice" ;;
  esac
fi
info "Mode: ${BOLD}${MODE}${NC}"

# ── System packages ────────────────────────────────────────────────────────────
header "System Packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl
success "System packages ready"

# ── Python version check ───────────────────────────────────────────────────────
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_OK=$(python3 -c "import sys; print('yes' if sys.version_info >= (3,10) else 'no')")
if [[ "$PY_OK" != "yes" ]]; then
  die "Python ${PYTHON_MIN}+ required (found ${PY_VER}). Install python3.10 or newer."
fi
success "Python ${PY_VER} ✓"

# ── Virtual environment ────────────────────────────────────────────────────────
header "Python Environment"

if [[ "$MODE" == "fresh" || "$MODE" == "repair" ]]; then
  info "Creating virtual environment…"
  rm -rf "$VENV_DIR"
  python3 -m venv "$VENV_DIR" || die "Failed to create virtual environment"
else
  info "Using existing virtual environment"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip --quiet
success "Virtual environment ready"

# ── Source update (upgrade mode) ───────────────────────────────────────────────
if [[ "$MODE" == "upgrade" && -d "${ROOT_DIR}/.git" ]]; then
  header "Updating Source"
  git -C "$ROOT_DIR" fetch origin || warn "git fetch failed"
  git -C "$ROOT_DIR" pull        || warn "git pull failed"
  success "Source updated"
fi

# ── Install dependencies ───────────────────────────────────────────────────────
header "Installing Dependencies"
info "Installing Python packages (this may take a minute)…"
pip install -r "${ROOT_DIR}/requirements.txt" --quiet
pip install -e "${ROOT_DIR}" --quiet
success "Dependencies installed"

# Verify SDK
python3 -c "import bittensor; print('  SDK version:', bittensor.__version__)" \
  || die "bittensor SDK failed to import"
success "Bittensor SDK ready"

PYTHON_PATH="${VENV_DIR}/bin/python"

# ── Config setup ───────────────────────────────────────────────────────────────
if [[ "$MODE" != "fresh" && -f "$CONFIG_FILE" ]]; then
  header "Configuration"
  info "Preserving existing config.yaml"

else
  header "Bot Configuration"

  # Telegram
  echo
  info "Telegram Setup"
  echo
  ENABLE_TELEGRAM=false
  TELEGRAM_TOKEN=""
  TELEGRAM_USER_IDS="[]"

  read -r -p "$(echo -e "${CYAN}Enable Telegram bot? [Y/n]: ${NC}")" ans || true
  ans="${ans:-Y}"
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    ENABLE_TELEGRAM=true
    echo
    read -r -p "Telegram Bot Token: " TELEGRAM_TOKEN
    echo
    echo "Get your Telegram User ID from @userinfobot"
    read -r -p "Your Telegram User ID: " TG_ID
    TELEGRAM_USER_IDS="  - ${TG_ID}"
  fi

  # Discord
  echo
  info "Discord Setup"
  echo
  ENABLE_DISCORD=false
  DISCORD_TOKEN=""
  DISCORD_USER_IDS="[]"

  read -r -p "$(echo -e "${CYAN}Enable Discord bot? [y/N]: ${NC}")" ans || true
  ans="${ans:-N}"
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    ENABLE_DISCORD=true
    echo
    read -r -p "Discord Bot Token: " DISCORD_TOKEN
    echo
    echo "Enable Developer Mode in Discord → right-click your username → Copy ID"
    read -r -p "Your Discord User ID: " DC_ID
    DISCORD_USER_IDS="  - ${DC_ID}"
  fi

  # Wallet
  echo
  info "Wallet Setup"
  echo
  read -r -p "Wallet name [EasyApe]: " WALLET_NAME
  WALLET_NAME="${WALLET_NAME:-EasyApe}"

  WALLET_PATH="/root/.bittensor/wallets"
  read -r -p "Wallet path [${WALLET_PATH}]: " wp
  WALLET_PATH="${wp:-${WALLET_PATH}}"

  DEFAULT_NETUID=""
  read -r -p "Default netuid (leave blank for none): " DEFAULT_NETUID || true

  echo
  read -r -p "$(echo -e "${CYAN}Create a new passwordless coldkey now? [Y/n]: ${NC}")" ans || true
  ans="${ans:-Y}"
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    echo
    info "Creating coldkey '${WALLET_NAME}'…"
    "${VENV_DIR}/bin/python" -c "
import bittensor as bt
w = bt.Wallet(name='${WALLET_NAME}', path='${WALLET_PATH}')
w.create_coldkey(use_password=False, overwrite=False)
print('Coldkey address:', w.coldkey.ss58_address)
" || warn "Wallet creation failed — you can create one manually later"
  fi

  # Write config
  echo
  info "Writing config.yaml…"

  NETUID_LINE=""
  [[ -n "$DEFAULT_NETUID" ]] && NETUID_LINE="      default_netuid: ${DEFAULT_NETUID}"

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
${TELEGRAM_USER_IDS}
  discord_user_ids:
${DISCORD_USER_IDS}

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
${NETUID_LINE}
      validator_all: tao.bot

defaults:
  netuid:
  validator: tao.bot

validators:
  delegates_fallback_url: https://raw.githubusercontent.com/opentensor/bittensor-delegates/main/public/delegates.json
  cache_ttl_minutes: 60
  aliases:
    tao.bot: 5E2LP6EnZ54m3wS8s1yPvD5c3xo71kQroBw7aUVK32TKeZ5u
YAML

  chmod 600 "$CONFIG_FILE"
  success "config.yaml written"
fi

# ── Validate config ────────────────────────────────────────────────────────────
header "Validating Config"
"${PYTHON_PATH}" -m stakechat_bot.main --config "${CONFIG_FILE}" --doctor \
  || warn "Doctor check had warnings — review config.yaml"

# ── systemd service ────────────────────────────────────────────────────────────
header "systemd Service"

cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=EasyApe - Text to Stake
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=10

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=${ROOT_DIR}/src
Environment=PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=HOME=/root

ExecStart=${PYTHON_PATH} -u -m stakechat_bot.main --config ${CONFIG_FILE}

Restart=always
RestartSec=5
User=root
Group=root
StandardOutput=journal
StandardError=journal
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable easyape.service
systemctl restart easyape.service

sleep 2
if systemctl is-active --quiet easyape.service; then
  success "easyape.service is RUNNING"
else
  warn "easyape.service may not be running — check: journalctl -u easyape -n 50"
fi

# ── Shell convenience ─────────────────────────────────────────────────────────
header "Shell Setup"

BASHRC="${HOME}/.bashrc"
BLOCK_START="# >>> EasyApe managed block >>>"
BLOCK_END="# <<< EasyApe managed block <<<"

sed -i "/${BLOCK_START}/,/${BLOCK_END}/d" "$BASHRC"

cat >> "$BASHRC" <<SHELL

${BLOCK_START}
if [ -d "${ROOT_DIR}/.venv" ]; then
  source "${ROOT_DIR}/.venv/bin/activate" 2>/dev/null || true
fi
alias easyape-status="systemctl status easyape.service"
alias easyape-logs="journalctl -u easyape.service -f"
alias easyape-restart="systemctl restart easyape.service"
${BLOCK_END}
SHELL

success "Shell aliases added (easyape-status, easyape-logs, easyape-restart)"

# ── Done ──────────────────────────────────────────────────────────────────────
echo
echo -e "${CYAN}${BOLD}$(printf '═%.0s' {1..50})${NC}"
echo -e "${GREEN}${BOLD}  🦍 EasyApe installed successfully!${NC}"
echo -e "${CYAN}${BOLD}$(printf '═%.0s' {1..50})${NC}"
echo
echo -e "  Config:   ${BOLD}${CONFIG_FILE}${NC}"
echo -e "  Logs:     ${BOLD}journalctl -u easyape -f${NC}"
echo -e "  Restart:  ${BOLD}systemctl restart easyape${NC}"
echo
echo -e "${YELLOW}  Commands in Telegram/Discord:${NC}"
echo -e "    stake 0.5 31       — stake 0.5 TAO into subnet 31"
echo -e "    unstake 0.25 31    — unstake 0.25 TAO worth from subnet 31"
echo -e "    unstake all 31     — unstake ALL alpha from subnet 31  ✨"
echo -e "    balance            — view full portfolio"
echo -e "    pnl                — profit & loss"
echo -e "    roi                — return on investment"
echo -e "    history            — last 20 transactions"
echo -e "    help               — all commands"
echo
echo -e "${YELLOW}  Donate TAO / Alpha:${NC}"
echo -e "    5DqjE7Farmhto8gxkHPfZEj6sUEE1UCvdYMRqkBsgT1X3AaP"
echo
read -r -p "$(echo -e "${CYAN}Press ENTER to finish…${NC}")" || true
