# main.py

import asyncio
import time
import json
import logging
from logging_config import setup_logging
from live_price_binance_ws import listen_binance_order_book
from live_price_bybit_ws import listen_bybit_order_book
from live_price_kraken_ws import listen_kraken_order_book
from live_price_adv_cb_ws import listen_coinbase_order_book


# Set up logging
setup_logging()
logger = logging.getLogger(__name__)

# live_price_watcher
class LivePriceWatcher:
    def __init__(self):
        self.prices = {}  # {exchange_id: {'bid': x, 'ask': y, 'timestamp': t, 'status': 'connected'/'disconnected'}}

    def update_price(self, exchange, bid, ask):
        # Set status to connected on price update
        self.prices[exchange] = {'bid': bid, 'ask': ask, 'timestamp': time.time(), 'status': 'connected'}

    def set_status(self, exchange, status):
        if exchange in self.prices:
            self.prices[exchange]['status'] = status
        else:
            self.prices[exchange] = {'bid': None, 'ask': None, 'timestamp': None, 'status': status}

    def get_status(self, exchange):
        return self.prices.get(exchange, {}).get('status', 'disconnected')

    def get_best_opportunity(self):
        best_bid = {'exchange': None, 'price': -1}
        best_ask = {'exchange': None, 'price': float('inf')}

        for exchange_id, price in self.prices.items():
            if price.get('status') != 'connected':
                continue
            if price['bid'] is None or price['ask'] is None:
                continue
            if price['bid'] > best_bid['price'] and price['bid'] > 0:
                best_bid = {'exchange': exchange_id, 'price': price['bid']}
            if price['ask'] < best_ask['price'] and price['ask'] > 0:
                best_ask = {'exchange': exchange_id, 'price': price['ask']}

        return best_bid, best_ask
    
    
async def check_opportunity_loop(watcher, taker_fee=0.001):
    logger.info("Starting check_opportunity_loop")
    while True:
        # Only run if at least two exchanges are connected
        connected_exchanges = [ex for ex, data in watcher.prices.items() if data.get('status') == 'connected']
        if len(connected_exchanges) < 2:
            await asyncio.sleep(0.5)
            continue
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
        await asyncio.sleep(0.5)  # Sleep for X seconds to avoid busy waiting


async def main():
    try:
        watcher = LivePriceWatcher()
        await asyncio.gather(
            # listen_coinbase_order_book(watcher, symbol="ETH-USD"),
            # listen_binance_order_book(watcher, symbol="ethusdt"),
            listen_bybit_order_book(watcher, symbol="ETHUSDT"),
            # listen_kraken_order_book(watcher, symbol=["ETH/USDT"]),
            check_opportunity_loop(watcher, taker_fee=0.001)
        )
    except asyncio.CancelledError:
        print("Tasks cancelled, exiting main")
    
    except Exception as e:
        logger.exception(f"Unhandled exception in main(): {e}")
        print(f"Unhandled exception: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"Fatal error: {e}")