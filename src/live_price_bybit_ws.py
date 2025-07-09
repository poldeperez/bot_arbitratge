import json
import websockets
import asyncio
import logging
from config.settings import STALE_TIME, MAX_WS_RECONNECTS
from src.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def listen_bybit_order_book(watcher, symbol="BTCUSDT"):
    ws_url = "wss://stream.bybit.com/v5/public/spot"
    topic = f"orderbook.50.{symbol.upper()}"
    subscribe_msg = {
        "op": "subscribe",
        "args": [topic]
    }
    reconnect_attempts = 0
    update_reconnects = 0

    while reconnect_attempts < MAX_WS_RECONNECTS:
        snapshot = None
        last_update_id = None
        order_book = None
        subscribed = False

        try:
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps(subscribe_msg))
                watcher.set_status("bybit", "connected")
                reconnect_attempts = 0
                print("Connecting to Bybit orderbook WS")
                
                while update_reconnects < MAX_WS_RECONNECTS:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=STALE_TIME)
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
                            watcher.set_status("binance", "disconnected")
                            snapshot = data['data']
                            last_update_id = int(snapshot['u'])
                            print(f"Reset Bybit snapshot received. u = {last_update_id}")
                            order_book = {
                                'bids': {price: qty for price, qty in snapshot['b']},
                                'asks': {price: qty for price, qty in snapshot['a']}
                            }
                            watcher.set_status("binance", "connected")
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
                    except asyncio.TimeoutError:
                        logger.exception(f"No Bybit order book update for {STALE_TIME} seconds. Reconnecting...")
                        watcher.set_status("bybit", "disconnected")
                        await ws.close()
                        break
                    except Exception as e:
                        watcher.set_status("bybit", "disconnected")
                        update_reconnects += 1
                        logger.exception(f"Bybit orderbook error: {e} | Reconnecting attempt {update_reconnects}/{MAX_WS_RECONNECTS} | Last received message: {data if 'data' in locals() else 'No data variable'}")
                        break # Exit inner loop to reconnect

                if update_reconnects >= MAX_WS_RECONNECTS:
                    logger.error(f"Max update attempts ({MAX_WS_RECONNECTS}) reached.")
                    break

        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK) as e:
            logger.exception(f"WebSocket closed: {e}. Attempt {reconnect_attempts}/{MAX_WS_RECONNECTS}. Reconnecting in 5 seconds...")
            watcher.set_status("bybit", "disconnected")
            reconnect_attempts += 1
            await asyncio.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Attempt {reconnect_attempts}/{MAX_WS_RECONNECTS}. Reconnecting in 5 seconds...")
            watcher.set_status("bybit", "disconnected")
            reconnect_attempts += 1
            await asyncio.sleep(5)
    logger.error(f"Max reconnect/update attempts ({MAX_WS_RECONNECTS}) reached. Stopping Bybit order book listener.")
    watcher.set_status("bybit", "stopped")