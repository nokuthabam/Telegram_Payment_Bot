"""
Payment Manager
- Holds wallet address mapping
- Converts GBP → crypto via CoinGecko free API
- Contains blockchain verification helpers (currently unused while manual mode is enabled)
"""

import aiohttp
import logging
from config import Config
import random

logger = logging.getLogger(__name__)

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT_ERC20": "tether",
    "USDT_TRC20": "tether",
    "SOL": "solana",
    "LTC": "litecoin",
    "TRX": "tron",
}

DECIMALS = {
    "BTC": 8,
    "ETH": 6,
    "USDT_ERC20": 2,
    "USDT_TRC20": 2,
    "SOL": 6,
    "LTC": 6,
    "TRX": 2,
}


class PaymentManager:
    def get_wallet(self, coin_key: str) -> str:
        mapping = {
            "BTC": Config.BTC_WALLET,
            "ETH": Config.ETH_WALLET,
            "USDT_ERC20": Config.USDT_ERC20_WALLET,
            "USDT_TRC20": Config.USDT_TRC20_WALLET,
            "SOL": Config.SOL_WALLET,
            "LTC": Config.LTC_WALLET,
            "TRX": Config.TRX_WALLET,
        }
        return mapping.get(coin_key, "N/A")

    def get_all_wallets(self) -> dict:
        return {
            "💵 USDT TRC-20 (TRON)": Config.USDT_TRC20_WALLET,
            "◎ Solana (SOL)": Config.SOL_WALLET,
            "₿ Bitcoin (BTC)": Config.BTC_WALLET,
            "Ξ Ethereum (ETH)": Config.ETH_WALLET,
            "💵 USDT ERC-20 (Ethereum)": Config.USDT_ERC20_WALLET,
            "Ł Litecoin (LTC)": Config.LTC_WALLET,
            "⚡ TRON (TRX)": Config.TRX_WALLET,
        }

    def generate_unique_gbp_amount(self, base_amount_gbp: float, coin_key: str, db) -> tuple[float, float]:
        """
        Adds a unique daily adjustment between £0.01 and £0.50.
        Same amount can be reused on a different day or for a different coin.
        """
        possible_adjustments = list(range(1, 51))
        random.shuffle(possible_adjustments)

        for cents in possible_adjustments:
            adjustment = cents / 100
            final_amount = round(base_amount_gbp + adjustment, 2)

            if not db.amount_used_today(coin_key, final_amount):
                return final_amount, adjustment

        raise ValueError("No unique payment amounts available for this coin today.")

    async def convert_gbp_to_crypto(self, gbp_amount: float, coin_key: str) -> str:
        """
        Fetch live GBP price from CoinGecko and convert GBP → crypto.
        This includes USDT, because the customer pays a GBP-denominated subscription.
        """
        cg_id = COINGECKO_IDS.get(coin_key)
        if not cg_id:
            return f"≈£{gbp_amount:.2f} GBP equivalent"

        try:
            url = f"{Config.COINGECKO_API}/simple/price"
            params = {"ids": cg_id, "vs_currencies": "gbp"}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

            price_gbp = data[cg_id]["gbp"]
            crypto_amount = gbp_amount / price_gbp
            decimals = DECIMALS.get(coin_key, 6)
            ticker = coin_key.split("_")[0]
            return f"{crypto_amount:.{decimals}f} {ticker}"

        except Exception as e:
            logger.warning(f"GBP price fetch failed for {coin_key}: {e}")
            return f"≈£{gbp_amount:.2f} GBP equivalent"

    # ─── Verification helpers ────────────────────────────────────────────────
    def _parse_expected_amount(self, invoice: dict) -> float:
        value = str(invoice["crypto_amount"]).split()[0].replace("≈", "")
        return float(value)

    def _amount_matches(self, received: float, expected: float, tolerance: float = 0.000001) -> bool:
        return received + tolerance >= expected

    async def _get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params, headers=headers) as resp:
                return await resp.json()

    async def _post_json(self, url: str, payload: dict):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                return await resp.json()

    # ─── Dispatcher ───────────────────────────────────────────────────────────
    async def verify_invoice(self, invoice: dict, db) -> tuple[bool, str | None]:
        coin = invoice["coin"]

        if coin == "BTC":
            return await self.verify_blockcypher(invoice, db, chain="btc")
        if coin == "LTC":
            return await self.verify_blockcypher(invoice, db, chain="ltc")
        if coin == "ETH":
            return await self.verify_eth(invoice, db)
        if coin == "USDT_ERC20":
            return await self.verify_usdt_erc20(invoice, db)
        if coin == "TRX":
            return await self.verify_trx(invoice, db)
        if coin == "USDT_TRC20":
            return await self.verify_usdt_trc20(invoice, db)
        if coin == "SOL":
            return await self.verify_sol(invoice, db)

        return False, None

    async def verify_blockcypher(self, invoice: dict, db, chain: str) -> tuple[bool, str | None]:
        expected = self._parse_expected_amount(invoice)
        wallet = invoice["wallet_address"]

        url = f"https://api.blockcypher.com/v1/{chain}/main/addrs/{wallet}/full"
        params = {"limit": 50, "token": Config.BLOCKCYPHER_API_KEY}

        data = await self._get_json(url, params=params)

        for tx in data.get("txs", []):
            tx_hash = tx.get("hash")
            if not tx_hash or db.tx_hash_exists(tx_hash):
                continue
            if tx.get("confirmations", 0) < 1:
                continue

            for output in tx.get("outputs", []):
                addresses = output.get("addresses", [])
                if wallet not in addresses:
                    continue

                received = output.get("value", 0) / 100_000_000
                if self._amount_matches(received, expected):
                    return True, tx_hash

        return False, None

    async def verify_eth(self, invoice: dict, db) -> tuple[bool, str | None]:
        expected = self._parse_expected_amount(invoice)
        wallet = invoice["wallet_address"].lower()

        url = "https://api.etherscan.io/v2/api"
        params = {
            "chainid": "1",
            "module": "account",
            "action": "txlist",
            "address": wallet,
            "page": 1,
            "offset": 50,
            "sort": "desc",
            "apikey": Config.ETHERSCAN_API_KEY,
        }

        data = await self._get_json(url, params=params)

        for tx in data.get("result", []):
            tx_hash = tx.get("hash")
            if not tx_hash or db.tx_hash_exists(tx_hash):
                continue
            if tx.get("isError") == "1":
                continue
            if tx.get("to", "").lower() != wallet:
                continue
            if int(tx.get("confirmations", "0")) < 1:
                continue

            received = int(tx.get("value", "0")) / 10**18
            if self._amount_matches(received, expected):
                return True, tx_hash

        return False, None

    async def verify_usdt_erc20(self, invoice: dict, db) -> tuple[bool, str | None]:
        expected = self._parse_expected_amount(invoice)
        wallet = invoice["wallet_address"].lower()
        usdt_contract = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

        url = "https://api.etherscan.io/v2/api"
        params = {
            "chainid": "1",
            "module": "account",
            "action": "tokentx",
            "contractaddress": usdt_contract,
            "address": wallet,
            "page": 1,
            "offset": 50,
            "sort": "desc",
            "apikey": Config.ETHERSCAN_API_KEY,
        }

        data = await self._get_json(url, params=params)

        for tx in data.get("result", []):
            tx_hash = tx.get("hash")
            if not tx_hash or db.tx_hash_exists(tx_hash):
                continue
            if tx.get("to", "").lower() != wallet:
                continue
            if int(tx.get("confirmations", "0")) < 1:
                continue

            decimals = int(tx.get("tokenDecimal", "6"))
            received = int(tx.get("value", "0")) / (10 ** decimals)

            if self._amount_matches(received, expected, tolerance=0.000001):
                return True, tx_hash

        return False, None

    def _base58check_decode(self, address: str) -> bytes:
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        num = 0

        for char in address:
            num *= 58
            num += alphabet.index(char)

        combined = num.to_bytes((num.bit_length() + 7) // 8, byteorder="big")
        leading_zeroes = len(address) - len(address.lstrip("1"))
        combined = b"\x00" * leading_zeroes + combined

        payload, checksum = combined[:-4], combined[-4:]

        import hashlib
        expected_checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]

        if checksum != expected_checksum:
            raise ValueError("Invalid TRON address checksum")

        return payload

    def _tron_address_to_hex(self, address: str) -> str:
        return self._base58check_decode(address).hex()

    async def verify_trx(self, invoice: dict, db) -> tuple[bool, str | None]:
        expected = self._parse_expected_amount(invoice)
        wallet = invoice["wallet_address"]
        wallet_hex = self._tron_address_to_hex(wallet).lower()

        url = f"https://api.trongrid.io/v1/accounts/{wallet}/transactions"
        headers = {}
        if Config.TRONGRID_API_KEY:
            headers["TRON-PRO-API-KEY"] = Config.TRONGRID_API_KEY

        params = {
            "limit": 50,
            "only_confirmed": "true",
            "order_by": "block_timestamp,desc",
        }

        data = await self._get_json(url, params=params, headers=headers)

        for tx in data.get("data", []):
            tx_hash = tx.get("txID")
            if not tx_hash or db.tx_hash_exists(tx_hash):
                continue

            for contract in tx.get("raw_data", {}).get("contract", []):
                value = contract.get("parameter", {}).get("value", {})
                to_address = value.get("to_address", "").lower()
                amount_sun = value.get("amount")

                if to_address != wallet_hex or amount_sun is None:
                    continue

                received = int(amount_sun) / 1_000_000
                if self._amount_matches(received, expected):
                    return True, tx_hash

        return False, None

    async def verify_usdt_trc20(self, invoice: dict, db) -> tuple[bool, str | None]:
        expected = self._parse_expected_amount(invoice)
        wallet = invoice["wallet_address"]
        usdt_contract = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

        url = f"https://api.trongrid.io/v1/accounts/{wallet}/transactions/trc20"
        headers = {}
        if Config.TRONGRID_API_KEY:
            headers["TRON-PRO-API-KEY"] = Config.TRONGRID_API_KEY

        params = {
            "limit": 50,
            "only_confirmed": "true",
            "contract_address": usdt_contract,
            "order_by": "block_timestamp,desc",
        }

        data = await self._get_json(url, params=params, headers=headers)

        for tx in data.get("data", []):
            tx_hash = tx.get("transaction_id")
            if not tx_hash or db.tx_hash_exists(tx_hash):
                continue
            if tx.get("to", "") != wallet:
                continue

            decimals = int(tx.get("token_info", {}).get("decimals", 6))
            received = int(tx.get("value", "0")) / (10 ** decimals)

            if self._amount_matches(received, expected, tolerance=0.000001):
                return True, tx_hash

        return False, None

    async def verify_sol(self, invoice: dict, db) -> tuple[bool, str | None]:
        expected = self._parse_expected_amount(invoice)
        wallet = invoice["wallet_address"]

        signatures_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [wallet, {"limit": 20}]
        }

        signatures_data = await self._post_json(Config.SOLANA_RPC_URL, signatures_payload)

        for item in signatures_data.get("result", []):
            signature = item.get("signature")
            if not signature or db.tx_hash_exists(signature):
                continue
            if item.get("err") is not None:
                continue

            tx_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0
                    }
                ]
            }

            tx_data = await self._post_json(Config.SOLANA_RPC_URL, tx_payload)
            tx = tx_data.get("result")
            if not tx:
                continue

            message = tx.get("transaction", {}).get("message", {})
            meta = tx.get("meta", {})
            account_keys = message.get("accountKeys", [])
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])

            for index, account in enumerate(account_keys):
                pubkey = account.get("pubkey") if isinstance(account, dict) else account
                if pubkey != wallet:
                    continue
                if index >= len(pre_balances) or index >= len(post_balances):
                    continue

                received = (post_balances[index] - pre_balances[index]) / 1_000_000_000
                if self._amount_matches(received, expected):
                    return True, signature

        return False, None
