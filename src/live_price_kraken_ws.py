import asyncio
import json
import websockets
import aiohttp
import zlib

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

    snapshot = None
    order_book = None
    last_checksum = None
    subscribed = False

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps(subscribe_msg))
                print("Connected to Kraken orderbook WS, subscribing...")

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg, parse_float=str)
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
        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK) as e:
            print(f"WebSocket closed: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Unexpected error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

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