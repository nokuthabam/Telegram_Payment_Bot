"""
Configuration — reads from .env or environment variables
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    GROUP_ID: str = os.getenv("GROUP_ID", "")

    # Comma-separated Telegram user IDs, e.g. "123456789,987654321"
    ADMIN_TELEGRAM_IDS: list[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
        if x.strip()
    ]

    # ── Subscription Info ─────────────────────────────────────────────────────
    MEMBERSHIP_PRICE_GBP: float = float(os.getenv("MEMBERSHIP_PRICE_GBP", "100"))
    SUBSCRIPTION_DAYS: int = int(os.getenv("SUBSCRIPTION_DAYS", "30"))

    # ── API Keys ──────────────────────────────────────────────────────────────
    TRONGRID_API_KEY: str = os.getenv("TRONGRID_API_KEY", "")
    ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "")
    BLOCKCYPHER_API_KEY: str = os.getenv("BLOCKCYPHER_API_KEY", "")
    SOLANA_RPC_URL: str = os.getenv("SOLANA_RPC_URL", "")

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # ── Wallet Addresses ──────────────────────────────────────────────────────
    BTC_WALLET: str = os.getenv("BTC_WALLET", "YOUR_BTC_ADDRESS_HERE")
    ETH_WALLET: str = os.getenv("ETH_WALLET", "YOUR_ETH_ADDRESS_HERE")
    USDT_ERC20_WALLET: str = os.getenv("USDT_ERC20_WALLET", "YOUR_ETH_ADDRESS_HERE")
    USDT_TRC20_WALLET: str = os.getenv("USDT_TRC20_WALLET", "YOUR_TRX_ADDRESS_HERE")
    SOL_WALLET: str = os.getenv("SOL_WALLET", "YOUR_SOL_ADDRESS_HERE")
    LTC_WALLET: str = os.getenv("LTC_WALLET", "YOUR_LTC_ADDRESS_HERE")
    TRX_WALLET: str = os.getenv("TRX_WALLET", "YOUR_TRX_ADDRESS_HERE")

    # ── CoinGecko (free, no key needed) ───────────────────────────────────────
    COINGECKO_API: str = "https://api.coingecko.com/api/v3"
