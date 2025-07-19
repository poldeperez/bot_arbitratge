# main.py

import asyncio
import time
import json
import logging
import os
import sys
from src.logging_config import setup_logging
from src.live_price_binance_ws import listen_binance_order_book
from src.live_price_bybit_ws import listen_bybit_order_book
from src.live_price_kraken_ws import listen_kraken_order_book
from src.live_price_adv_cb_ws import listen_coinbase_order_book
from src.live_price_kucoin_ws import listen_kucoin_order_book
from config.settings import STALE_TIME


def get_symbol():
    # Prioridad: argumento de línea de comandos > variable de entorno > ETH por defecto
    if len(sys.argv) > 1:
        return sys.argv[1].upper()
    return os.getenv("SYMBOL", "BTC").upper()

symbol = get_symbol()

# Set up logging
sym = os.getenv("SYMBOL", "BTC")
setup_logging(sym)
logger = logging.getLogger(__name__)

# live_price_watcher
class LivePriceWatcher:
    def __init__(self, symbol_name):
        self.symbol = symbol_name
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
        return self.prices.get(exchange, {}).get('status', None)

    def get_best_opportunity(self):
        best_bid = {'exchange': None, 'price': -1}
        best_ask = {'exchange': None, 'price': float('inf')}

        for exchange_id, price in self.prices.items():
            if price.get('status') != 'connected':
                continue
            if price['bid'] is None or price['ask'] is None:
                continue
            if price['bid'] > best_bid['price'] and price['bid'] > 0:
                best_bid = {'exchange': exchange_id, 'price': price['bid'], 'timestamp': price['timestamp']}
            if price['ask'] < best_ask['price'] and price['ask'] > 0:
                best_ask = {'exchange': exchange_id, 'price': price['ask'], 'timestamp': price['timestamp']}

        return best_bid, best_ask
    
    
async def check_opportunity_loop(watcher, taker_fee=0.001):
    logger.info(f"Starting check_opportunity_loop for {watcher.symbol}")
    first_opportunity = None
    opportunity = None
    op_count = 0
    while True:
        # Only run if at least two exchanges are connected
        connected_exchanges = [ex for ex, data in watcher.prices.items() if data.get('status') == 'connected']
        if len(connected_exchanges) < 2:
            await asyncio.sleep(0.5)
            continue
        bid, ask = watcher.get_best_opportunity()
        if bid['exchange'] and ask['exchange']:
            current_time = time.time()
            adj_bid = bid['price'] * (1 - taker_fee)
            adj_ask = ask['price'] * (1 + taker_fee)
            profit = round(adj_bid, 2) - round(adj_ask, 2)
            if profit > 0:
                opportunity = (
                    ask['exchange'], ask['price'], ask['timestamp'], 
                    bid['exchange'], bid['price'], bid['timestamp']
                )
                # First opportunity profit found
                if first_opportunity is None:
                    print(f"First opportunity found")
                    first_opportunity = opportunity
                
                # Best bid or best ask has not changed in the last STALE_TIME seconds
                if abs(opportunity[2] - opportunity[5]) > STALE_TIME or current_time - opportunity[2] > STALE_TIME or current_time - opportunity[5] > STALE_TIME:
                    logger.warning(f"{watcher.symbol} Opportunity stale: {opportunity}")
                    # PENDING: Reconnect to the exchange in question
                    if opportunity[2] > opportunity[5]:
                        watcher.set_status(bid['exchange'], 'disconnected')
                        logger.warning(f"Disconnecting {bid['exchange']} due to stale opportunity")
                    else:
                        watcher.set_status(ask['exchange'], 'disconnected')
                        logger.warning(f"Disconnecting {ask['exchange']} due to stale opportunity")
                    continue

                # Check if this is the first opportunity exchanges
                if opportunity[0] == first_opportunity[0] and opportunity[3] == first_opportunity[3]:
                    # PENDING: handle same opportunity
                    print(f"Same opportunity found: {opportunity}")
                if opportunity[0] != first_opportunity[0] or opportunity[3] != first_opportunity[3]:
                    print("reset first opportunity")
                    first_opportunity = None

                logger.info(f"{watcher.symbol} Arbitrage opportunity! Profit: {profit:.2f} USDT | Buy on {ask['exchange']} at {ask['price']} | Sell on {bid['exchange']} at {bid['price']} | Current time: {current_time} | Prices: {json.dumps(watcher.prices)}")
                print(f"Arbitrage opportunity! Profit: {profit:.2f} USDT")
                print(f"Buy on {ask['exchange']} at {ask['price']} | Sell on {bid['exchange']} at {bid['price']}")
                print(json.dumps(watcher.prices, indent=2))
        await asyncio.sleep(0.5)  # Sleep for X seconds to avoid busy waiting


async def main():
    try:
        symbols = {
            symbol: {
                'coinbase': f"{symbol}-USD",
                'binance': f"{symbol.lower()}usdt",
                'bybit': f"{symbol}USDT",
                'kraken': [f"{symbol}/USDT"],
                'kucoin': f"{symbol}-USDT"
            }
        }
        tasks = []
        for sym_key, config in symbols.items():
            watcher = LivePriceWatcher(sym_key)
            tasks.extend([
                # listen_coinbase_order_book(watcher, symbol=config['coinbase'], crypto=sym_key),
                # listen_binance_order_book(watcher, symbol=config['binance'], crypto=sym_key),
                # listen_bybit_order_book(watcher, symbol=config['bybit'], crypto=sym_key),
                # listen_kraken_order_book(watcher, symbol=config['kraken'], crypto=sim_key),
                listen_kucoin_order_book(watcher, symbol=config['kucoin'], crypto=sym_key),
                check_opportunity_loop(watcher, taker_fee=0.0006)
            ])
    
        await asyncio.gather(*tasks)

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