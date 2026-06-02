# Telegram Crypto Payment Bot

A Telegram bot that accepts cryptocurrency payments, automatically verifies them on-chain, and grants access to a private Telegram group.

Supports:

* Bitcoin (BTC)
* Ethereum (ETH)
* USDT ERC-20
* USDT TRC-20
* Solana (SOL)
* Litecoin (LTC)
* TRON (TRX)

---

# Features

✅ Create crypto invoices directly in Telegram
✅ Automatic blockchain payment verification
✅ Unique invoice amounts to prevent payment collisions
✅ PostgreSQL database support
✅ Auto-generated private Telegram group invite links
✅ Join-request approval system for verified users only
✅ Multi-coin support across multiple blockchains
✅ Persistent cloud deployment support (Railway, Render, Docker)

---

# Supported Coins & APIs

| Coin | Network  | Verification Provider |
| ---- | -------- | --------------------- |
| BTC  | Bitcoin  | BlockCypher           |
| ETH  | Ethereum | Etherscan             |
| USDT | ERC-20   | Etherscan             |
| USDT | TRC-20   | TronGrid              |
| SOL  | Solana   | Alchemy / Solana RPC  |
| LTC  | Litecoin | BlockCypher           |
| TRX  | TRON     | TronGrid              |

---

# Project Structure

```text
Telegram_Payment_Bot/
├── bot.py
├── config.py
├── payment_manager.py
├── db.py
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

---

# Requirements

* Python 3.11+
* PostgreSQL
* Telegram Bot Token
* Blockchain API keys

---

# Setup

## 1. Create Telegram Bot

Open Telegram and message @BotFather.

Run:

```bash
/newbot
```

Copy your bot token.

---

## 2. Create Telegram Group

* Create your private Telegram group
* Add the bot as an administrator
* Enable:

  * Invite users
  * Manage invite links
  * Approve join requests

Get the group ID.

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Create a `.env` file:

```env
# Telegram
TELEGRAM_BOT_TOKEN=
GROUP_ID=

# PostgreSQL
DATABASE_URL=

# Blockchain APIs
ETHERSCAN_API_KEY=
TRONGRID_API_KEY=
BLOCKCYPHER_API_KEY=
SOLANA_RPC_URL=

# Wallet Addresses
BTC_WALLET=
ETH_WALLET=
USDT_ERC20_WALLET=
USDT_TRC20_WALLET=
SOL_WALLET=
LTC_WALLET=
TRX_WALLET=
```

---

# Running Locally

```bash
python bot.py
```

---

# How It Works

1. User starts the bot
2. User creates an invoice in USD
3. Bot generates a unique payment amount
4. User sends crypto to the provided wallet
5. Bot checks the blockchain automatically
6. Payment is verified
7. Bot sends a private Telegram invite link
8. User submits a join request
9. Bot approves only verified users

---

# Unique Payment Verification

The bot uses small unique invoice adjustments (up to $0.50) to identify payments sent to shared wallet addresses.

Example:

| User   | Invoice    |
| ------ | ---------- |
| User A | 20.13 USDT |
| User B | 20.27 USDT |
| User C | 20.44 USDT |

This prevents invoice collisions while using a single wallet per cryptocurrency.

---

# Deployment

Recommended platforms:

* Railway
* Render
* Fly.io

---

# Railway Deployment

## Create:

* 1 PostgreSQL service
* 1 Python bot service

## Environment Variables

Add all variables from `.env` into Railway Variables.

## Start Command

```bash
python bot.py
```

---

# Docker

Example Dockerfile:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

---

# Security Notes

* NEVER store private keys in the bot
* NEVER commit `.env`
* Rotate API keys if exposed
* Use HTTPS/webhooks in production if scaling
* Use PostgreSQL instead of SQLite for production deployments

---

# Important Disclaimer

This bot is provided as-is.

Always test with small crypto amounts before production use.

Blockchain transactions are irreversible.

