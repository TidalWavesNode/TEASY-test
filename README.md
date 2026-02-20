<img width="1792" height="576" alt="generated-image (2)" src="https://github.com/user-attachments/assets/79ded78c-0d2d-4354-ae46-861875905787" />

## 🦍 EasyApe – Setup Guide

EasyApe is a chat-based staking assistant that lets you **stake and unstake TAO directly from Telegram or Discord** using simple commands.

Designed for simplicity, safety, and beginner-friendly deployment.

---

## 📑 Table of Contents

- [🧠 What EasyApe Does](#-what-easyape-does)
- [✨ What You Should Expect](#-what-you-should-expect)
- [✅ System Requirements](#-system-requirements)
- [🚀 Installation (Fresh VPS)](#-installation-fresh-vps)
  - [1️⃣ Connect to your VPS](#1️⃣-connect-to-your-vps)
  - [2️⃣ Clone EasyApe](#2️⃣-clone-easyape)
  - [3️⃣ Run Installer](#3️⃣-run-installer)
- [🤖 Telegram Setup](#-telegram-setup)
  - [Step 1 – Create a Telegram Bot](#step-1--create-a-telegram-bot)
  - [Step 2 – Copy Bot Token](#step-2--copy-bot-token)
  - [Step 3 – Get Your Telegram User ID](#step-3--get-your-telegram-user-id)
- [💬 Discord Setup (Not Tested)](#-discord-setup-not-tested)
  - [Step 1 – Create Discord Application](#step-1--create-discord-application)
  - [Step 2 – Add Bot](#step-2--add-bot)
  - [Step 3 – Copy Bot Token](#step-3--copy-bot-token-1)
  - [Step 4 – Invite Bot to Server](#step-4--invite-bot-to-server)
  - [Step 5 – Get Your Discord User ID](#step-5--get-your-discord-user-id)
- [⚙️ Default Configuration Explained](#️-default-configuration-explained)
- [🔐 Wallet Setup](#-wallet-setup)
- [🧪 Dry Mode (Safe Testing)](#-dry-mode-safe-testing)
- [▶️ Managing EasyApe](#️-managing-easyape)
- [💬 Commands Cheat Sheet](#-commands-cheat-sheet)
- [📊 Portfolio & Performance Commands](#-portfolio--performance-commands)
  - [🏦 balance](#-balance)
  - [📈 pnl](#-pnl)
  - [💹 roi](#-roi)
  - [📜 history](#-history)
- [⚠️ Safety Best Practices](#️-safety-best-practices)
- [🔒 Security Notes](#-security-notes)
- [⚠️ Disclaimer](#️-disclaimer)
- [💚 Support EasyApe 💚](#-support-easyape-)

---

## 🧠 What EasyApe Does

EasyApe connects your Telegram or Discord account to your Bittensor wallet and:

✔ Parses simple commands like `stake 0.5 31` (action amount subnet)
✔ Shows a clear transaction summary  
✔ Tracks portfolio performance  
✔ Calculates PnL & ROI  
✔ Stores transaction history  
✔ Utilizes Bittensor SDK for speed

---

## ✨ What You Should Expect

When you send a command such as:

```
stake 0.1 31
```

EasyApe responds with:

• Action summary  
• Wallet being used  
• Subnet (netuid)  
• Validator  
• Amount  

👉 Commands are designed to be short and human-friendly.

---

## ✅ System Requirements

EasyApe runs best on:

✔ Ubuntu 20.04+ VPS  
✔ Python 3.10+  
✔ Internet connection  

You do **NOT** need to manually install bittensor/btcli.  
The installer handles everything automatically.

---

## 🚀 Installation (Fresh VPS)

### 1️⃣ Connect to your VPS

```bash
ssh root@your_server_ip
```

---

### 2️⃣ Clone EasyApe

```bash
git clone https://github.com/TidalWavesNode/EasyApe.git
cd EasyApe
```

---

### 3️⃣ Run Installer

```bash
chmod +x scripts/install_easyape.sh
./scripts/install_easyape.sh
```

Installer will automatically:

✔ Create isolated Python environment (.venv)  
✔ Install dependencies    
✔ Prompt for bot tokens  
✔ Configure wallet & defaults  
✔ Install systemd service  

---

## 🤖 Telegram Setup

### Step 1 – Create a Telegram Bot

1. Open Telegram  
2. Search for **BotFather**  
3. Click **Start**  
4. Send:

```
/newbot
```

5. Choose a bot name  
6. Choose a username (must end with `bot`)  

---

### Step 2 – Copy Bot Token

BotFather will return:

```
123456:ABC-DEF...
```

👉 Copy this token  
👉 Paste into EasyApe installer  

---

### Step 3 – Get Your Telegram User ID

1. Search Telegram for **@userinfobot**  
2. Click **Start**  
3. Copy your numeric ID  

Example:

```
Id: 123456789
```

👉 Paste into EasyApe installer  

---

## 💬 Discord Setup (Not Tested)

### Step 1 – Create Discord Application

1. Visit: https://discord.com/developers/applications  
2. Click **New Application**  
3. Name → Create  

---

### Step 2 – Add Bot

Application → Bot → **Add Bot** → Confirm  

---

### Step 3 – Copy Bot Token

Bot → Reset Token → Copy  

👉 Paste into EasyApe installer  

---

### Step 4 – Invite Bot to Server

OAuth2 → URL Generator:

Scopes:  
✔ bot  

Permissions:  
✔ Send Messages  
✔ Read Messages  

Open generated URL → Invite bot  

---

### Step 5 – Get Your Discord User ID

1. Discord Settings → Advanced  
2. Enable **Developer Mode**  
3. Right-click username → Copy ID  

👉 Paste into EasyApe installer  

---

## ⚙️ Default Configuration Explained

During install you may be asked:

```
Default netuid (leave blank for none):
```

If you **set a default netuid**:

✔ You can type:

```
stake 0.1
```

If you **leave blank**:

✔ Include subnet:

```
stake 0.1 31
```

---

## 🔐 Wallet Setup

Installer will ask:

```
Create a NEW wallet now?
```

If YES:

✔ Runs wallet creation  
✔ Displays recovery phrase  
✔ Pauses for confirmation  

⚠️ Losing this phrase = permanent loss of funds  

If NO:

✔ Existing wallet name is requested  

👉 EasyApe supports **passwordless wallets**.

---

## 🧪 Dry Mode (Safe Testing)

Edit `config.yaml`:

```yaml
app:
  mode: dry
```

EasyApe will simulate actions without executing real stakes.

---

## ▶️ Managing EasyApe

Check bot status:

```bash
systemctl status easyape.service
```

Restart bot:

```bash
systemctl restart easyape.service
```

Stop bot:

```bash
systemctl stop easyape.service
```

---

## 💬 Commands Cheat Sheet

Stake:

```
stake 0.5 31
```

Unstake:

```
unstake 0.25 31
```

Balance / Portfolio:

```
balance
```

View Profit & Loss:

```
pnl
```

View ROI:

```
roi
```

Transaction History:

```
history
```

Help:

```
help
```

---

## 📊 Portfolio & Performance Commands

### 🏦 **balance**
Shows:

✔ Free TAO balance  
✔ Alpha holdings per subnet  
✔ Current TAO value  
✔ Entry price  
✔ Unrealized PnL  

---

### 📈 **pnl**
Displays:

✔ Profit / Loss per subnet  
✔ Total portfolio PnL  
✔ Gain / loss indicators  

---

### 💹 **roi**
Shows:

✔ Return on Investment  
✔ Percentage performance  
✔ Efficiency of deployed TAO  

---

### 📜 **history**
Lists:

✔ Stakes  
✔ Unstakes  
✔ Amounts  
✔ Subnets  
✔ Execution record  

Useful for auditing and tracking activity.

---

## ⚠️ Safety Best Practices

✔ Start with small TAO amounts  
✔ Protect bot tokens  
✔ Secure wallet recovery phrase  
✔ Use dry mode if unsure  

---

## 🔒 Security Notes

EasyApe:

✔ Does NOT store private keys  
✔ Uses SDK for signing  
✔ Does NOT bypass wallet security  
✔ Can NOT transfer funds out

Wallet safety remains handled by btcli / Bittensor SDK.

---

## ⚠️ Disclaimer

EasyApe is provided for educational and experimental purposes only.  
Nothing within this project constitutes financial, investment, legal, or tax advice.

Use at your own risk.  
You are solely responsible for your staking decisions and wallet security.

Cryptocurrency and staking involve risk, including potential loss of funds.

---

## 💚 Support EasyApe 💚

If you find EasyApe helpful and would like to support development:

**Consider donating TAO or Alpha tokens**

Donation address:

```
5DqjE7Farmhto8gxkHPfZEj6sUEE1UCvdYMRqkBsgT1X3AaP
```

🦍 Your support helps maintain and improve EasyApe 🦍
