import asyncio
import json
import websockets
import aiohttp
import zlib
import logging
import time
from config.settings import STALE_TIME, MAX_WS_RECONNECTS
from src.logging_config import setup_logging


setup_logging()
logger = logging.getLogger(__name__)

depth = 25  # depth for Kraken order book

async def fetch_kraken_snapshot(symbol):
    # Kraken REST API for order book snapshot
    url = f"https://api.kraken.com/0/public/Depth"
    params = {
        "pair": symbol,
        "count": depth
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            print(f"Fetched Kraken snapshot for {symbol}")
            if 'result' not in data:
                print(f"Kraken REST error: {data.get('error', data)}")
                return None
            # The result is {"result": {"SYMBOL": {"bids": [...], "asks": [...]}}}
            book = list(data['result'].values())[0]
            return book


async def listen_kraken_order_book(watcher, symbol=["BTC/USDT"]):
    # Kraken WebSocket API v2 endpoint
    ws_url = "wss://ws.kraken.com/v2"
    # Kraken expects symbols like XBT/USDT, ETH/USDT, etc.
    subscribe_msg = {
        "method": "subscribe",
        "params": {
            "channel": "book",
            "symbol": symbol,
            "depth": depth,
            "snapshot": True
        }
    }
    reconnect_attempts = 0
    update_reconnects = 0
    
    while reconnect_attempts < MAX_WS_RECONNECTS:
        snapshot = None
        order_book = None
        last_checksum = None
        subscribed = False

        try:
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps(subscribe_msg))
                print("Connected to Kraken orderbook WS, subscribing...")
                watcher.set_status("kraken", "connected")
                reconnect_attempts = 0
                ping_id = 1
                while update_reconnects < MAX_WS_RECONNECTS:
                    try:
                        # Wait for a message or timeout for ping
                        recv_task = asyncio.create_task(ws.recv())
                        done, pending = await asyncio.wait(
                            [recv_task],
                            timeout=10,
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in pending:
                            task.cancel()
                        if done:
                            msg = done.pop().result()
                            data = json.loads(msg, parse_float=str)
                            # Handle pong
                            if isinstance(data, dict) and data.get("method") == "pong":
                                print(f"Received pong from Kraken: {data}")
                                continue
                            # Wait for subscription acknowledgment
                            if not subscribed:
                                if data.get('result', {}).get("channel") == "book" and data.get("success") == True:
                                    print(f"✅ Subscribed to Kraken book for {symbol}")
                                    subscribed = True
                                continue
                            # Wait for the first snapshot
                            if snapshot is None:
                                if data.get("channel") == "book" and data.get("type") == "snapshot":
                                    # Kraken v2 book snapshot is inside data['data'][0]
                                    snapshot = data['data'][0]
                                    bids = [(str(b['price']), str(b['qty'])) for b in snapshot.get('bids', [])]
                                    asks = [(str(a['price']), str(a['qty'])) for a in snapshot.get('asks', [])]
                                    order_book = {
                                        'bids': {price: qty for price, qty in bids},
                                        'asks': {price: qty for price, qty in asks}
                                    }
                                    last_checksum = snapshot.get('checksum')
                                    print(f"✅ Kraken snapshot received. checksum = {last_checksum}")
                                else:
                                    continue
                            # Process updates
                            if data.get("channel") == "book" and data.get("type") == "update":
                                update = data['data'][0]
                                for price, qty in [(str(b['price']), str(b['qty'])) for b in update.get('bids', [])]:
                                    if float(qty) == 0:
                                        order_book['bids'].pop(price, None)
                                    else:
                                        order_book['bids'][price] = qty
                                for price, qty in [(str(a['price']), str(a['qty'])) for a in update.get('asks', [])]:
                                    if float(qty) == 0:
                                        order_book['asks'].pop(price, None)
                                    else:
                                        order_book['asks'][price] = qty
                                # Truncate order book to depth 25
                                if len(order_book['bids']) > depth:
                                    #print(f"Truncating bids to depth {depth}")
                                    order_book['bids'] = dict(sorted(order_book['bids'].items(), key=lambda x: -float(x[0]))[:depth])
                                if len(order_book['asks']) > depth:
                                    #print(f"Truncating asks to depth {depth}")
                                    order_book['asks'] = dict(sorted(order_book['asks'].items(), key=lambda x: float(x[0]))[:depth])
                                # Check checksum
                                # new_checksum = update.get('checksum')
                                # if new_checksum is not None:
                                #     checksum_str = build_checksum_str(order_book)
                                #     computed_checksum = zlib.crc32(checksum_str.encode())
                                #     print(f"Kraken checksum, str: {checksum_str} computed: {computed_checksum}, received: {new_checksum}")
                                #     if computed_checksum != new_checksum:
                                #         print(f"❌ Kraken checksum mismatch! Local: {computed_checksum}, Exchange: {new_checksum}. Refetching snapshot...")
                                #         snapshot = await fetch_kraken_snapshot(symbol)
                                #         order_book = {
                                #             'bids': {price: qty for price, qty, *_ in snapshot['bids']},
                                #             'asks': {price: qty for price, qty, *_ in snapshot['asks']}
                                #         }
                                #         last_checksum = None
                                #         continue
                                #     last_checksum = new_checksum
                                # Update watcher with best bid/ask
                                if order_book['bids'] and order_book['asks']:
                                    best_bid = max(order_book['bids'].keys(), key=lambda x: float(x))
                                    best_ask = min(order_book['asks'].keys(), key=lambda x: float(x))
                                    bid = float(best_bid)
                                    ask = float(best_ask)
                                    current = watcher.prices.get('kraken')
                                    if current is None or current['bid'] != bid or current['ask'] != ask:
                                        watcher.update_price('kraken', bid, ask)
                                        print(f"Kraken Watcher updated: highest bid={bid}, lowest ask={ask}")
                        else:
                            # No message in 10 seconds, send ping
                            ping_msg = {
                                "method": "ping",
                                "req_id": ping_id
                            }
                            await ws.send(json.dumps(ping_msg))
                            logger.info(f"Sent ping to Kraken (req_id={ping_id}) after 10s of inactivity")
                            # Wait for pong for up to 5 seconds
                            pong_received = False
                            pong_deadline = time.time() + 5
                            while time.time() < pong_deadline:
                                try:
                                    pong_msg = await asyncio.wait_for(ws.recv(), timeout=pong_deadline - time.time())
                                    pong_data = json.loads(pong_msg)
                                    if pong_data.get("method") == "pong" and pong_data.get("req_id") == ping_id:
                                        logger.info(f"Received pong from Kraken (req_id={ping_id})")
                                        pong_received = True
                                        break
                                except asyncio.TimeoutError:
                                    break
                            ping_id += 1
                            if not pong_received:
                                logger.exception(f"No pong received. Reconnecting...")
                                watcher.set_status("kraken", "disconnected")
                                update_reconnects += 1
                                break  # Exit inner while to reconnect
                    except asyncio.TimeoutError:
                        logger.exception("Timeout waiting for message from Kraken, reconnecting...")
                        watcher.set_status("kraken", "disconnected")
                        break  # Exit inner while to reconnect
                    except Exception as e:
                        watcher.set_status("kraken", "disconnected")
                        update_reconnects += 1
                        logger.exception(f"Unexpected error: {e} | Attempt {update_reconnects}/{MAX_WS_RECONNECTS}. Last received message: {data if 'data' in locals() else 'No data variable'}")
                        break

                if update_reconnects >= MAX_WS_RECONNECTS:
                    logger.error(f"Max update attempts ({MAX_WS_RECONNECTS}) reached.")
                    break

        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK) as e:
            logger.exception(f"WebSocket closed: {e}. Attempt {reconnect_attempts}/{MAX_WS_RECONNECTS}. Reconnecting in 5 seconds...")
            watcher.set_status("kraken", "disconnected")
            reconnect_attempts += 1
            await asyncio.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Attempt {reconnect_attempts}/{MAX_WS_RECONNECTS}. Reconnecting in 5 seconds... Last received message: {data if 'data' in locals() else 'No data variable'}")
            watcher.set_status("kraken", "disconnected")
            reconnect_attempts += 1
            await asyncio.sleep(5)
    logger.error(f"Max reconnect/update attempts ({MAX_WS_RECONNECTS}) reached. Stopping Kraken order book listener.")
    watcher.set_status("kraken", "stopped")

def build_checksum_str(order_book):
    def clean(val):
        # Remove decimal and leading zeros
        s = str(val).replace('.', '')
        return s.lstrip('0') or '0'
    asks = sorted(order_book['asks'].items(), key=lambda x: float(x[0]))
    bids = sorted(order_book['bids'].items(), key=lambda x: -float(x[0]))
    parts = []
    for price, qty in asks:
        parts.append(f"{clean(price)}{clean(qty)}")
    for price, qty in bids:
        parts.append(f"{clean(price)}{clean(qty)}")
    return ''.join(parts)