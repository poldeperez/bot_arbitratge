import json
import websockets
import asyncio
import logging
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def listen_bybit_order_book(watcher, symbol="BTCUSDT"):
    ws_url = "wss://stream.bybit.com/v5/public/spot"
    topic = f"orderbook.50.{symbol.upper()}"
    subscribe_msg = {
        "op": "subscribe",
        "args": [topic]
    }
    snapshot = None
    last_update_id = None
    order_book = None
    subscribed = False

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps(subscribe_msg))
                watcher.set_status("bybit", "connected")
                print("Connecting to Bybit orderbook WS")
                
                while True:
                    try:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        
                        if last_update_id is None:
                            # Only process snapshot or wait for snapshot before deltas
                            if subscribed is False and data.get("success") is True:
                                subscribed = True
                                continue
                            if subscribed is False and data.get("success") is not True:
                                logger.error(f"Bybit subscription failed: {data}")
                                watcher.set_status("bybit", "disconnected")
                                break
                            if data.get("type") == "snapshot":
                                snapshot = data['data']
                                last_update_id = int(snapshot['u'])
                                print(f"First Bybit snapshot received. u = {last_update_id}")
                                order_book = {
                                    'bids': {price: qty for price, qty in snapshot['b']},
                                    'asks': {price: qty for price, qty in snapshot['a']}
                                }
                            # If not snapshot, skip until snapshot is received
                            continue
                        u = int(data['data']['u'])
                        if data.get("topic") != topic or u <= last_update_id:
                            continue
                        if data.get("type") == "snapshot" or u == 1:
                            snapshot = data['data']
                            last_update_id = int(snapshot['u'])
                            print(f"Reset Bybit snapshot received. u = {last_update_id}")
                            order_book = {
                                'bids': {price: qty for price, qty in snapshot['b']},
                                'asks': {price: qty for price, qty in snapshot['a']}
                            }
                            continue
                        # Process deltas
                        if data.get("type") == "delta":   
                            for price, qty in data['data']['b']:
                                if float(qty) == 0:
                                    order_book['bids'].pop(price, None)
                                else:
                                    order_book['bids'][price] = qty
                            for price, qty in data['data']['a']:
                                if float(qty) == 0:
                                    order_book['asks'].pop(price, None)
                                else:
                                    order_book['asks'][price] = qty

                        last_update_id = u

                        # Update watcher with best bid/ask
                        if order_book['bids'] and order_book['asks']:
                            best_bid = max(order_book['bids'].keys(), key=lambda x: float(x))
                            best_ask = min(order_book['asks'].keys(), key=lambda x: float(x))
                            bid = float(best_bid)
                            ask = float(best_ask)
                            current = watcher.prices.get('bybit')
                            if current is None or current['bid'] != bid or current['ask'] != ask:
                                watcher.update_price('bybit', bid, ask)
                                print(f"Bybit Watcher updated: highest bid={bid}, lowest ask={ask}")
                    except Exception as e:
                        watcher.set_status("bybit", "disconnected")
                        logger.exception(f"Bybit orderbook error: {e}")
                        break # Exit inner loop to reconnect

        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK) as e:
            logger.exception(f"WebSocket closed: {e}. Reconnecting in 5 seconds...")
            watcher.set_status("bybit", "disconnected")
            await asyncio.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Reconnecting in 5 seconds...")
            watcher.set_status("bybit", "disconnected")
            await asyncio.sleep(5)