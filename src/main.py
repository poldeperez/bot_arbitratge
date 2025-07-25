# main.py

import asyncio
import time
import json
import logging
import os
import sys
import redis
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
setup_logging(symbol)
logger = logging.getLogger(__name__)

# live_price_watcher
class LivePriceWatcher:
    def __init__(self, symbol_name):
        self.symbol = symbol_name
        self.prices = {}  # {exchange_id: {'bid': x, 'ask': y, 'timestamp': t, 'status': 'connected'/'disconnected'}}
        
        self.redis_client = None
        self._setup_redis()

        # Path del archivo de status
        self.status_file = f"/app/logs/status_{self.symbol}.json"
        # En desarrollo local, usar path local
        if not os.path.exists("/app/logs"):
            self.status_file = f"logs/status_{self.symbol}.json"

    def _setup_redis(self):
        """Configura conexión Redis con fallback"""
        try:
            redis_url = os.getenv('REDIS_URL')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            
            # Test connection
            self.redis_client.ping()
            logger.info(f"Redis connected successfully for {self.symbol}")
            
        except Exception as e:
            logger.warning(f"Redis connection failed for {self.symbol}: {e}")
            logger.warning(f"Falling back to JSON files")
            self.redis_client = None
    
    def _write_status_redis(self):
        """Escribe estado a Redis con TTL"""
        if not self.redis_client:
            return False
            
        try:
            status_data = {
                'symbol': self.symbol,
                'last_update': time.time(),
                'last_update_readable': time.strftime('%Y-%m-%d %H:%M:%S'),
                'exchanges': self.prices
            }
            
            # Escribir con TTL de 60 segundos
            key = f"status:{self.symbol}"
            self.redis_client.setex(key, 60, json.dumps(status_data))
            
            # También escribir datos individuales para queries más fáciles
            for exchange, data in self.prices.items():
                exchange_key = f"exchange:{self.symbol}:{exchange}"
                self.redis_client.setex(exchange_key, 60, json.dumps(data))
            
            return True
            
        except Exception as e:
            logger.error(f"Error writing to Redis: {e}")
            return False
    
    def _write_status_file(self):
        """Escribe el estado actual del exchange a archivo JSON"""
        try:
            # Crear directorio si no existe
            os.makedirs(os.path.dirname(self.status_file), exist_ok=True)
            
            # Preparar datos con metadatos
            status_data = {
                'symbol': self.symbol,
                'last_update': time.time(),
                'last_update_readable': time.strftime('%Y-%m-%d %H:%M:%S'),
                'exchanges': self.prices
            }
            
            # Escribir atómicamente (write temp + rename)
            temp_file = f"{self.status_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(status_data, f, indent=2)
            
            # Rename atómico
            os.rename(temp_file, self.status_file)
            
        except Exception as e:
            logger.error(f"Error writing status file {self.status_file}: {e}")

    def _update_status(self):
        """Actualiza estado usando Redis primero, JSON como fallback"""
        redis_success = self._write_status_redis()
        # Solo usar archivo si Redis falló
        if not redis_success:
            file_success = self._write_status_file()

        if not redis_success and not file_success:
            logger.error(f"Failed to write status for {self.symbol}")
    
    def update_price(self, exchange, bid, ask):
        # Set status to connected on price update
        self.prices[exchange] = {'bid': bid, 'ask': ask, 'timestamp': time.time(), 'status': 'connected'}
        if self.redis_client:
            self._update_status()

    def set_status(self, exchange, status):
        if exchange in self.prices:
            self.prices[exchange]['status'] = status
        else:
            self.prices[exchange] = {'bid': None, 'ask': None, 'timestamp': None, 'status': status}
        if self.redis_client:
            self._update_status()

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
                listen_coinbase_order_book(watcher, symbol=config['coinbase'], crypto=sym_key),
                listen_binance_order_book(watcher, symbol=config['binance'], crypto=sym_key),
                # listen_bybit_order_book(watcher, symbol=config['bybit'], crypto=sym_key),
                # listen_kraken_order_book(watcher, symbol=config['kraken'], crypto=sim_key),
                # listen_kucoin_order_book(watcher, symbol=config['kucoin'], crypto=sym_key),
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