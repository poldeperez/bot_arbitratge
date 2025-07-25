import json
import websockets
import logging
import asyncio
import os
from config.settings import STALE_TIME, MAX_WS_RECONNECTS
from src.logging_config import setup_logging

sym = os.getenv("SYMBOL", "BTC")

setup_logging(sym)
logger = logging.getLogger(__name__)

# Coinbase Advanced Trade WS without authentication
async def listen_coinbase_order_book(watcher, symbol="BTC-USD", crypto="BTC"):
    url = "wss://advanced-trade-ws.coinbase.com"
    subscribe_msg = [
        {
            "type": "subscribe",
            "product_ids": [symbol],
            "channel": "level2"
        },
        {
            "type": "subscribe",
            "channel": "heartbeats"
        }
    ]
    reconnect_attempts = 0
    update_reconnects = 0
    
    while reconnect_attempts < MAX_WS_RECONNECTS:
        order_book = None
        expected_sequence = 0

        try:
            async with websockets.connect(url, max_size=3 * 1024 * 1024, ping_interval=20, ping_timeout=10) as ws:
                for msg in subscribe_msg:
                    await ws.send(json.dumps(msg))
                print("Connecting to Coinbase WebSocket.")
                while update_reconnects < MAX_WS_RECONNECTS:
                    try:
                        # Check if the watcher status is disconnected while running listener
                        status = watcher.get_status("coinbase")
                        if status == "disconnected" and expected_sequence != 0:
                            logger.warning("Coinbase watcher status set to 'disconnected' by main. Closing WS and reconnecting...")
                            await ws.close()
                            await asyncio.sleep(60)
                            break  # Break inner loop to reconnect
                        
                        msg = await asyncio.wait_for(ws.recv(), timeout=STALE_TIME)
                        data = json.loads(msg)

                        # Handle sequence number for updates
                        sequence_num = data.get("sequence_num")
                        if sequence_num is None:
                            logger.error(f"No sequence_num in message, skipping... Last received message: {data if 'data' in locals() else 'No data variable'}")
                            continue
                        else:
                            if sequence_num != expected_sequence:
                                logger.error(f"Sequence mismatch: expected {expected_sequence}, got {sequence_num}. Reconnecting Websocket...")
                                # Clear coinbase info in watcher
                                watcher.prices.pop("coinbase", None)
                                try:
                                    await ws.close()
                                except Exception as e:
                                    logger.error(f"Error closing websocket: {e}")
                                # Recursive call to restart the listener
                                return await listen_coinbase_order_book(watcher, symbol, crypto)

                        if data.get("channel") == "heartbeats":
                            expected_sequence += 1
                            # Optionally, update a timestamp or status in your watcher here

                        elif data.get("channel") == "l2_data":
                            # Process events
                            for event in data.get("events", []):
                                if event.get("type") == "snapshot":
                                    bids = []
                                    asks = []
                                    for update in event.get("updates", []):
                                        side = update.get("side")
                                        price = update.get("price_level")
                                        qty = update.get("new_quantity")
                                        if side == "bid":
                                            bids.append((price, qty))
                                        elif side == "ask" or side == "offer":
                                            asks.append((price, qty))
                                    order_book = {
                                        'bids': {price: qty for price, qty in bids},
                                        'asks': {price: qty for price, qty in asks}
                                    }
                                    print(f"✅ Coinbase snapshot received. Bids: {len(order_book['bids'])}, Asks: {len(order_book['asks'])}")
                                    if watcher.get_status("coinbase") == "disconnected":
                                        watcher.set_status("coinbase", "connected")
                                        logger.info("Coinbase watcher reconnected after snapshot.")
                                    continue

                                elif event.get("type") == "update":
                                    for update in event.get("updates", []):
                                        side = update.get("side")
                                        price = update.get("price_level")
                                        qty = update.get("new_quantity")
                                        if side == "bid":
                                            if float(qty) == 0:
                                                order_book['bids'].pop(price, None)
                                            else:
                                                order_book['bids'][price] = qty
                                        elif side == "ask" or side == "offer":
                                            if float(qty) == 0:
                                                order_book['asks'].pop(price, None)
                                            else:
                                                order_book['asks'][price] = qty
                                    # Update watcher if there are bids and ask
                                    if order_book['bids'] and order_book['asks']:
                                        bid = max(float(p) for p in order_book['bids'].keys())
                                        ask = min(float(p) for p in order_book['asks'].keys())
                                        current = watcher.prices.get('coinbase')
                                        if current is None or bid != current.get('bid') or ask != current.get('ask'):
                                            watcher.update_price('coinbase', bid, ask)
                                            print(f"{crypto} Coinbase: highest bid={bid}, lowest ask={ask}")
                            expected_sequence += 1
                            update_reconnects = 0


                        elif data.get("channel") == "subscriptions":
                            print(f"Subscription successful for: {data['events'][0]['subscriptions']}")
                            watcher.set_status("coinbase", "connected")
                            reconnect_attempts = 0
                            expected_sequence += 1
                        
                        else:
                            print(f"Wrong channel '{data.get('channel')}', skipping...")
                        

                    except asyncio.TimeoutError:
                        logger.exception(f"No Coinbase order book update for {STALE_TIME} seconds. Reconnecting...")
                        watcher.set_status("coinbase", "disconnected")
                        await ws.close()
                        break
                    except Exception as e:
                        watcher.set_status("coinbase", "disconnected")
                        update_reconnects += 1
                        logger.exception(f"Unexpected error: {e} | Attempt {update_reconnects}/{MAX_WS_RECONNECTS}. Last received message: {data if 'data' in locals() else 'No data variable'}")
                        break

                if update_reconnects >= MAX_WS_RECONNECTS:
                    logger.error(f"Max update attempts ({MAX_WS_RECONNECTS}) reached.")
                    break

        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK) as e:
            logger.exception(f"WebSocket closed: {e}. Attempt {reconnect_attempts}/{MAX_WS_RECONNECTS}. Reconnecting in 5 seconds...")
            watcher.set_status("coinbase", "disconnected")
            reconnect_attempts += 1
            await asyncio.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Attempt {reconnect_attempts}/{MAX_WS_RECONNECTS}. Reconnecting in 5 seconds...")
            watcher.set_status("coinbase", "disconnected")
            reconnect_attempts += 1
            await asyncio.sleep(5)
    logger.error(f"Max reconnect/update attempts ({MAX_WS_RECONNECTS}) reached. Stopping Coinbase order book listener.")
    watcher.set_status("coinbase", "stopped")