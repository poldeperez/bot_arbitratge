import json
import websockets
import aiohttp
import logging
import asyncio
from config.settings import STALE_TIME, MAX_WS_RECONNECTS
from src.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# Binance ticker WS
async def listen_binance(watcher, symbol="btcusdt"):
    url = f"wss://stream.binance.com:9443/ws/{symbol}@bookTicker"
    async with websockets.connect(url) as ws:
        print("Connected to Binance WebSocket.")
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            bid = float(data['b'])
            ask = float(data['a'])
            current = watcher.prices.get('binance')
            if current is None or current['bid'] != bid or current['ask'] != ask:
                watcher.update_price('binance', bid, ask)

# Binance Depth Order Book WS
async def fetch_snapshot(symbol):
    url = f"https://api.binance.com/api/v3/depth?symbol={symbol.upper()}&limit=100"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def listen_binance_order_book(watcher, symbol="btcusdt", crypto="BTC", **kwargs):
    depth_url = f"wss://stream.binance.com:9443/ws/{symbol}@depth@100ms"
    reconnect_attempts = 0
    snap_reconnects = 0
    update_reconnects = 0

    while reconnect_attempts < MAX_WS_RECONNECTS:
        buffer = []
        snapshot = None
        last_update_id = None
        order_book = None

        try:
            async with websockets.connect(depth_url) as ws:
                print("Connecting to Binance depth stream")

                if snap_reconnects >= MAX_WS_RECONNECTS:
                    logger.error(f"Max Snapshot fetching attempts ({MAX_WS_RECONNECTS}) reached.")
                    break
                
                # 1. Buffer messages while fetching snapshot
                while snapshot is None and snap_reconnects < MAX_WS_RECONNECTS:
                    try:
                        msg = await ws.recv()
                        data_b = json.loads(msg)
                        buffer.append(data_b)
                        # Try to fetch snapshot after first message
                        if snapshot is None:
                            snapshot = await fetch_snapshot(symbol)
                            last_update_id = snapshot['lastUpdateId']
                            print(f"✅ Snapshot recibido. lastUpdateId = {last_update_id}")
                            order_book = {
                                'bids': {price: qty for price, qty in snapshot['bids']},
                                'asks': {price: qty for price, qty in snapshot['asks']}
                            }
                    except Exception as e:
                        snap_reconnects += 1
                        logger.exception(f"Error while buffering: {e} | Reconnecting... Last received message: {data_b if 'data_b' in locals() else 'No data variable'}")
                        watcher.set_status("binance", "disconnected")
                        snapshot = None 
                        await ws.close()
                        break  # Exit the buffering loop and reconnect

                # 2. Process buffered messages after snapshot
                if snapshot is not None:
                    # Discard events where u <= lastUpdateId
                    buffer = [data for data in buffer if data['u'] > last_update_id]
                    # Find the first event where U <= lastUpdateId+1 <= u
                    start_index = None
                    for i, data in enumerate(buffer):
                        U = data['U']
                        u = data['u']
                        if U <= last_update_id + 1 <= u:
                            start_index = i
                            break
                    if start_index is not None:
                        # Apply all events from start_index onwards
                        for data in buffer[start_index:]:
                            for price, qty in data['b']:
                                if float(qty) == 0:
                                    order_book['bids'].pop(price, None)
                                else:
                                    order_book['bids'][price] = qty
                            for price, qty in data['a']:
                                if float(qty) == 0:
                                    order_book['asks'].pop(price, None)
                                else:
                                    order_book['asks'][price] = qty
                            last_update_id = data['u']
                    buffer = None  # Free memory
                    if watcher.get_status("binance") == "disconnected":
                        logger.info("Binance reconnected after disconnect.")
                    watcher.set_status("binance", "connected")
                    reconnect_attempts = 0
                
                # 3. Process new messages as usual
                if update_reconnects >= MAX_WS_RECONNECTS:
                    logger.error(f"Max update reconnect attempts ({MAX_WS_RECONNECTS}) reached.")
                    break

                while snapshot is not None:
                    try:
                        # Check if the watcher status is disconnected while running listener
                        status = watcher.get_status("binance")
                        if status == "disconnected" and last_update_id is not None:
                            logger.warning("Binance watcher status set to 'disconnected' by main. Closing WS and reconnecting...")
                            await ws.close()
                            await asyncio.sleep(60)
                            break  # Break inner loop to reconnect

                        msg = await asyncio.wait_for(ws.recv(), timeout=STALE_TIME)
                        data = json.loads(msg)

                        u = data['u']
                        U = data['U']
                        if u <= last_update_id:
                            print(f"Skipping update {u} as it is not newer than last_update_id {last_update_id}")
                            continue
                        if U > last_update_id + 1:
                            logger.exception(f"Desync binance detected, reseting order book with snapshot...")
                            watcher.set_status("binance", "disconnected")
                            snapshot = await fetch_snapshot(symbol)
                            last_update_id = snapshot['lastUpdateId']
                            print(f"✅ Nuevo snapshot recibido {snapshot['lastUpdateId']}")
                            order_book = {
                                'bids': {price: qty for price, qty in snapshot['bids']},
                                'asks': {price: qty for price, qty in snapshot['asks']}
                            }
                            watcher.set_status("binance", "connected")
                            continue
                        for price, qty in data['b']:
                            if float(qty) == 0:
                                order_book['bids'].pop(price, None)
                            else:
                                order_book['bids'][price] = qty
                        for price, qty in data['a']:
                            if float(qty) == 0:
                                order_book['asks'].pop(price, None)
                            else:
                                order_book['asks'][price] = qty
                        last_update_id = u

                        # 4. Obtain best bid/ask and update
                        best_bid = max(order_book['bids'].keys(), key=lambda x: float(x))
                        best_ask = min(order_book['asks'].keys(), key=lambda x: float(x))

                        bid = float(best_bid)
                        ask = float(best_ask)

                        current = watcher.prices.get('binance')

                        if current is None or current['bid'] != bid or current['ask'] != ask:
                            watcher.update_price('binance', bid, ask)
                            print(f"{crypto} Binance: highest bid={bid}, lowest ask={ask}")
                            update_reconnects = 0 

                    except asyncio.TimeoutError:
                        logger.exception(f"No Binance order book update for {STALE_TIME} seconds. Reconnecting...")
                        watcher.set_status("binance", "disconnected")
                        await ws.close()
                        break
                    except Exception as e:
                        update_reconnects += 1
                        logger.exception(f"Unexpected error: {e} | Reconnecting attempt {update_reconnects}/{MAX_WS_RECONNECTS} | Last received message: {data if 'data' in locals() else 'No data variable'}")
                        watcher.set_status("binance", "disconnected")
                        await ws.close()
                        break
        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK) as e:
                        logger.exception(f"WebSocket closed: {e}. Attempt {reconnect_attempts}/{MAX_WS_RECONNECTS}. Reconnecting in 5 seconds...")
                        watcher.set_status("binance", "disconnected")
                        reconnect_attempts += 1
                        break
        except Exception as e:
            reconnect_attempts += 1
            logger.exception(f"Failed to connect to Binance WS: {e}. Attempt {reconnect_attempts}/{MAX_WS_RECONNECTS}. Reconnecting in 5 seconds...")
            watcher.set_status("binance", "disconnected")
            await asyncio.sleep(5)
    logger.error(f"Max reconnect attempts ({MAX_WS_RECONNECTS}) reached. Stopping Binance order book listener.")
    watcher.set_status("binance", "stopped")