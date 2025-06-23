# main.py

import asyncio
import time
import json
import logging
from pathlib import Path
from live_price_binance_ws import listen_binance_order_book
from live_price_bybit_ws import listen_bybit_order_book
from live_price_kraken_ws import listen_kraken_order_book
from live_price_adv_cb_ws import listen_coinbase_order_book


# Ensure logs directory exists
(Path(__file__).parent.parent / "logs").mkdir(parents=True, exist_ok=True)
print("Logs directory path:", Path(__file__).parent.parent / "logs")

class LivePriceWatcher:
    def __init__(self):
        self.prices = {}  # {exchange_id: {'bid': x, 'ask': y, timestamp: t}}

    def update_price(self, exchange, bid, ask):
        self.prices[exchange] = {'bid': bid, 'ask': ask, 'timestamp': time.time()}

    def get_best_opportunity(self):
        best_bid = {'exchange': None, 'price': -1}
        best_ask = {'exchange': None, 'price': float('inf')}

        for exchange_id, price in self.prices.items():
            if price['bid'] > best_bid['price'] and price['bid'] > 0:
                best_bid = {'exchange': exchange_id, 'price': price['bid']}
            if price['ask'] < best_ask['price'] and price['ask'] > 0:
                best_ask = {'exchange': exchange_id, 'price': price['ask']}

        return best_bid, best_ask
    
    
async def check_opportunity_loop(watcher, taker_fee=0.001):
    logger = logging.getLogger("arbitrage")
    logger.setLevel(logging.INFO)
    # Dynamically resolve the logs directory relative to this file
    log_path = Path(__file__).parent.parent / "logs" / "arbitrage_opportunities.log"
    try:
        handler = logging.FileHandler(log_path)
    except Exception as e:
        print(f"Failed to create log file handler: {e}")
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    if not logger.hasHandlers():
        logger.addHandler(handler)
    count = 0
    logger.info("Logger test: This should appear in the log file.")
    while True:
        start_time = time.time()
        bid, ask = watcher.get_best_opportunity()
        if bid['exchange'] and ask['exchange']:
            adj_bid = bid['price'] * (1 - taker_fee)
            adj_ask = ask['price'] * (1 + taker_fee)
            profit = round(adj_bid, 2) - round(adj_ask, 2)
            if profit > 0:
                logger.info(f"Arbitrage opportunity! Profit: {profit:.2f} USDT | Buy on {ask['exchange']} at {ask['price']} | Sell on {bid['exchange']} at {bid['price']} | Prices: {json.dumps(watcher.prices)}")
                print(f"Arbitrage opportunity! Profit: {profit:.2f} USDT")
                print(f"Buy on {ask['exchange']} at {ask['price']} | Sell on {bid['exchange']} at {bid['price']}")
                print(json.dumps(watcher.prices, indent=2))
        end_time = time.time()
        duration = end_time - start_time
        print(f"check_opportunity_loop iteration took {duration:.6f}")
        count += 1
        if count > 1000:
            logger.info("Logging 1000 opportunities, exiting")
            count=0
        await asyncio.sleep(0.1)  # Sleep for X seconds to avoid busy waiting


async def main():
    try:
        watcher = LivePriceWatcher()
        await asyncio.gather(
            listen_coinbase_order_book(watcher, symbol="ETH-USD"),
            listen_binance_order_book(watcher, symbol="ethusdt"),
            listen_bybit_order_book(watcher, symbol="ETHUSDT"),
            listen_kraken_order_book(watcher, symbol=["ETH/USDT"]),
            check_opportunity_loop(watcher, taker_fee=0.001)
        )
    except asyncio.CancelledError:
        print("Tasks cancelled, exiting main")
    
    except Exception as e:
        logging.exception(f"Unhandled exception in main: {e}")
        print(f"Unhandled exception: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        print(f"Fatal error: {e}")