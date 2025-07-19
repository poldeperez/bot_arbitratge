import base64
import hashlib
import hmac
import time
import logging
import os
import asyncio
import aiohttp
from src.logging_config import setup_logging

sym = os.getenv("SYMBOL", "BTC")

setup_logging(sym)
logger = logging.getLogger(__name__)

"""
KcSigner contains information about `apiKey`, `apiSecret`, `apiPassPhrase`, and `apiKeyVersion`
and provides methods to sign and generate headers for API requests.
"""

class KcSigner:
    def __init__(self, api_key: str, api_secret: str, api_passphrase: str, broker_name: str = "",
                 broker_partner: str = "", broker_key: str = ""):
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.api_passphrase = api_passphrase or ""
        if api_passphrase and api_secret:
            self.api_passphrase = self.sign(api_passphrase.encode('utf-8'), api_secret.encode('utf-8'))
        if not all([api_key, api_secret, api_passphrase]):
            logging.warning("API token is empty. Access is restricted to public interfaces only.")
        self.broker_name = broker_name
        self.broker_partner = broker_partner
        self.broker_key = broker_key

    def sign(self, plain: bytes, key: bytes) -> str:
        hm = hmac.new(key, plain, hashlib.sha256)
        return base64.b64encode(hm.digest()).decode()

    """
    Headers method generates and returns a map of signature headers needed for API authorization
    It takes a plain string as an argument to help form the signature. The outputs are set of API headers,
    """

    def headers(self, plain: str) -> dict:
        timestamp = str(int(time.time() * 1000))
        signature = self.sign((timestamp + plain).encode('utf-8'), self.api_secret.encode('utf-8'))

        return {
            "KC-API-KEY": self.api_key,
            "KC-API-PASSPHRASE": self.api_passphrase,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-SIGN": signature,
            "KC-API-KEY-VERSION": "3"
        }

    def broker_headers(self, plain: str) -> dict:
        timestamp = str(int(time.time() * 1000))
        signature = self.sign((timestamp + plain).encode(), self.api_secret.encode())

        if self.broker_partner is None or self.broker_name is None or self.broker_partner is None:
            raise RuntimeError("Broker information cannot be empty")

        partner_signature = self.sign((timestamp + self.broker_partner + self.api_key).encode(),
                                      self.api_secret.encode())

        return {
            "KC-API-KEY": self.api_key,
            "KC-API-PASSPHRASE": self.api_passphrase,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-SIGN": signature,
            "KC-API-KEY-VERSION": "3",
            "KC-API-PARTNER": self.broker_partner,
            "KC-BROKER-NAME": self.broker_name,
            "KC-API-PARTNER-VERIFY": "true",
            "KC-API-PARTNER-SIGN": partner_signature
        }
    

API_KEY = "6877b282c714e80001eeac9d"
KUCOIN_API_SECRET = "55456214-961a-44f5-bac7-ed0ae1de4e19"
KUCOIN_API_PASSPHRASE = "arbitratge"

async def fetch_snapshot(symbol):
    url_path = f"/api/v3/market/orderbook/level2?symbol={symbol.upper()}"
    url = f"https://api.kucoin.com{url_path}"
    signer = KcSigner(
        api_key= API_KEY,
        api_secret= KUCOIN_API_SECRET,
        api_passphrase= KUCOIN_API_PASSPHRASE
    )
    # Prepara los datos para la firma
    # Genera headers
    method = "GET"
    plain = f"{method}{url_path}"
    headers = signer.headers(plain)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            snapshot = await resp.json()
            logger.info(f"Kucoin snapshot response: {snapshot}")
            return snapshot
        

async def main():
    try:
        symbol = "BTC-USDT"  # Example symbol, replace with actual symbol as needed
        snapshot = await fetch_snapshot(symbol)
        print(f"Snapshot for {symbol}: {snapshot}")
    except Exception as e:
        logger.exception(f"Error fetching snapshot: {e}")
        print(f"Error fetching snapshot: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"Fatal error: {e}")