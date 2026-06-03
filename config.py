"""
Configuration — reads from .env or environment variables
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    GROUP_ID = os.getenv("GROUP_ID")
    TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY", "")
    ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
    BLOCKCYPHER_API_KEY = os.getenv("BLOCKCYPHER_API_KEY", "")
    SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")
    # ── Wallet Addresses ──────────────────────────────────────────────────────
    # Replace these with YOUR real wallet addresses before deploying!
    BTC_WALLET:        str = os.getenv("BTC_WALLET",        "YOUR_BTC_ADDRESS_HERE")
    ETH_WALLET:        str = os.getenv("ETH_WALLET",        "YOUR_ETH_ADDRESS_HERE")
    USDT_ERC20_WALLET: str = os.getenv("USDT_ERC20_WALLET", "YOUR_ETH_ADDRESS_HERE")   # same as ETH
    USDT_TRC20_WALLET: str = os.getenv("USDT_TRC20_WALLET", "YOUR_TRX_ADDRESS_HERE")   # same as TRX
    SOL_WALLET:        str = os.getenv("SOL_WALLET",        "YOUR_SOL_ADDRESS_HERE")
    LTC_WALLET:        str = os.getenv("LTC_WALLET",        "YOUR_LTC_ADDRESS_HERE")
    TRX_WALLET:        str = os.getenv("TRX_WALLET",        "YOUR_TRX_ADDRESS_HERE")

    # ── CoinGecko (free, no key needed) ───────────────────────────────────────
    COINGECKO_API: str = "https://api.coingecko.com/api/v3"

    # ── Database ──────────────────────────────────────────────────────────────
    DB_PATH: str = os.getenv("DB_PATH", "payments.db")