import json
import websockets
import aiohttp
import http.client
import logging
import time
import asyncio
import os
from config.settings import STALE_TIME, MAX_WS_RECONNECTS
from src.logging_config import setup_logging
from src.kcsign import KcSigner
from dotenv import load_dotenv

load_dotenv('./venv/.env')

sym = os.getenv("SYMBOL", "BTC")

setup_logging(sym)
logger = logging.getLogger(__name__)

async def get_token():
    conn = http.client.HTTPSConnection("api.kucoin.com")
    payload = ''
    headers = {}
    conn.request("POST", "/api/v1/bullet-public", payload, headers)
    res = conn.getresponse()
    data = res.read()
    data_json = json.loads(data.decode("utf-8"))
    return data_json

async def fetch_snapshot(symbol):
    KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
    KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET")
    KUCOIN_API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE")
    if not all([KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE]):
        raise ValueError("ERROR: Kucoin API credentials not found in environment variables")
    url_path = f"/api/v3/market/orderbook/level2?symbol={symbol.upper()}"
    url = f"https://api.kucoin.com{url_path}"
    signer = KcSigner(
        api_key= KUCOIN_API_KEY,
        api_secret= KUCOIN_API_SECRET,
        api_passphrase= KUCOIN_API_PASSPHRASE
    )
    # Genera headers
    method = "GET"
    plain = f"{method}{url_path}"
    headers = signer.headers(plain)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            snapshot = await resp.json()
            return snapshot
        

async def listen_kucoin_order_book(watcher, symbol="BTC-USDT", crypto="BTC", **kwargs):
    token_response = await get_token()
    token = token_response['data']['token']
    if token:
        print(f"Kucoin token OK")
    url = f"wss://ws-api-spot.kucoin.com?token={token}&connectId=00001"
    subscribe_msg = {
        "id": "00001",
        "type": "subscribe",
        "topic": f"/market/level2:{symbol}",
        "privateChannel": False,
        "response": True
    }
    reconnect_attempts = 0
    snap_reconnects = 0
    update_reconnects = 0

    while reconnect_attempts < MAX_WS_RECONNECTS:
        buffer = []
        snapshot = None
        sequence = None
        order_book = None
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(subscribe_msg))
                print("Connecting to Kucoin WS...")
                
                if snap_reconnects >= MAX_WS_RECONNECTS:
                    logger.error(f"Max Snapshot fetching attempts ({MAX_WS_RECONNECTS}) reached.")
                    break

                # 1. Buffer messages while fetching snapshot
                while snapshot is None and snap_reconnects < MAX_WS_RECONNECTS:
                    try:
                        async def buffer_messages():
                            while not snapshot_ready:
                                msg = await ws.recv()
                                data_b = json.loads(msg)
                                buffer.append(data_b)
                        
                        snapshot_ready = False
                        buffer_task = asyncio.create_task(buffer_messages())

                        # Time to buffer messages
                        await asyncio.sleep(1) 

                        snapshot = await fetch_snapshot(symbol)
                        sequence = int(snapshot['data']['sequence'])
                        snapshot_ready = True
                        await buffer_task  
                        print(f"Snapshot recibido. {sequence=}")
                        order_book = {
                            'bids': {price: qty for price, qty in snapshot['data']['bids']},
                            'asks': {price: qty for price, qty in snapshot['data']['asks']}
                        }
                    except Exception as e:
                        snap_reconnects += 1
                        logger.exception(f"Error while buffering: {e} | Reconnecting... Last snapshot sequence number: {sequence if 'sequence' in locals() else 'No data variable'}")
                        watcher.set_status("kucoin", "disconnected")
                        snapshot = None 
                        await ws.close()
                        break  # Exit the buffering loop and reconnect

                # 2. Process buffered messages after snapshot
                if snapshot is not None:
                    # Discard events where sequenceEnd <= sequence
                    buffer = [data for data in buffer if data['type'] not in ('welcome', 'ack') and data['data']['sequenceEnd'] > sequence]
                    # Find the first event where sequenceStart <= sequence+1 <= sequenceEnd
                    start_index = None
                    for i, data in enumerate(buffer):
                        start_id = data['data']['sequenceStart']
                        end_id = data['data']['sequenceEnd']
                        if start_id <= sequence + 1 <= end_id:
                            start_index = i
                            break
                    if start_index is not None:
                        # Apply all events from start_index onwards
                        for data in buffer[start_index:]:
                            for price, qty, _ in data['data']['changes']['bids']:
                                if float(qty) == 0:
                                    order_book['bids'].pop(price, None)
                                else:
                                    order_book['bids'][price] = qty
                            for price, qty, _ in data['data']['changes']['asks']:
                                if float(qty) == 0:
                                    order_book['asks'].pop(price, None)
                                else:
                                    order_book['asks'][price] = qty
                            sequence = int(data['data']['sequenceEnd'])
                    buffer = None  # Free memory
                    if watcher.get_status("kucoin") == "disconnected":
                        logger.info("Kucoin reconnected after disconnect.")
                    watcher.set_status("kucoin", "connected")
                    reconnect_attempts = 0

                # 3. Process new messages as usual
                if update_reconnects >= MAX_WS_RECONNECTS:
                    logger.error(f"Max update reconnect attempts ({MAX_WS_RECONNECTS}) reached.")
                    break

                while snapshot is not None:
                    try:
                        # Check if the watcher status is disconnected while running listener
                        status = watcher.get_status("kucoin")
                        if status == "disconnected" and sequence is not None:
                            logger.warning("Kucoin watcher status set to 'disconnected' by main. Closing WS and reconnecting...")
                            await ws.close()
                            await asyncio.sleep(60)
                            break  # Break inner loop to reconnect

                        msg = await asyncio.wait_for(ws.recv(), timeout=STALE_TIME)
                        data = json.loads(msg)
                        #print(f"Received Kucoin message: {data}")

                        if data['type'] == 'welcome' or data['type'] == 'ack':
                            continue
                        
                        start_id = data['data']['sequenceStart']
                        end_id = data['data']['sequenceEnd']
                        if end_id <= sequence:
                            print(f"Skipping update {end_id} as it is not newer than last_update_id {sequence}")
                            continue
                        if start_id > sequence + 1:
                            print(f"{start_id=} > snapshot {sequence + 1=}, desync detected, resetting order book with snapshot...")
                            logger.exception(f"Desync kucoin detected, reseting order book with snapshot...")
                            watcher.set_status("kucoin", "disconnected")
                            snapshot = await fetch_snapshot(symbol)
                            sequence = int(snapshot['data']['sequence'])
                            print(f"✅ Nuevo snapshot recibido {sequence}")
                            order_book = {
                                'bids': {price: qty for price, qty in snapshot['data']['bids']},
                                'asks': {price: qty for price, qty in snapshot['data']['asks']}
                            }
                            watcher.set_status("kucoin", "connected")
                            continue
                        for price, qty, _ in data['data']['changes']['bids']:
                            if float(qty) == 0:
                                order_book['bids'].pop(price, None)
                            else:
                                order_book['bids'][price] = qty
                        for price, qty, _ in data['data']['changes']['asks']:
                            if float(qty) == 0:
                                order_book['asks'].pop(price, None)
                            else:
                                order_book['asks'][price] = qty
                        sequence = end_id

                        # 4. Obtain best bid/ask and update
                        bid = max(float(p) for p in order_book['bids'].keys())
                        ask = min(float(p) for p in order_book['asks'].keys())

                        current = watcher.prices.get('kucoin')

                        if current is None or current['bid'] != bid or current['ask'] != ask:
                            watcher.update_price('kucoin', bid, ask)
                            print(f"{crypto} Kucoin: highest bid={bid}, lowest ask={ask}")
                            update_reconnects = 0 

                    except asyncio.TimeoutError:
                        logger.exception(f"No Kucoin order book update for {STALE_TIME} seconds. Reconnecting...")
                        watcher.set_status("kucoin", "disconnected")
                        await ws.close()
                        break
                    except Exception as e:
                        update_reconnects += 1
                        logger.exception(f"Unexpected error: {e} | Reconnecting attempt {update_reconnects}/{MAX_WS_RECONNECTS} | Last received message: {data if 'data' in locals() else 'No data variable'}")
                        watcher.set_status("kucoin", "disconnected")
                        await ws.close()
                        break
                    
        except Exception as e:
            print(f"Error in Kucoin WS: {e}")