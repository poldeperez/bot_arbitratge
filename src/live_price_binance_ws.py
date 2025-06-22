import json
import websockets
import aiohttp

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

async def fetch_ticker(symbol):
    url = f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol.upper()}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def listen_binance_order_book(watcher, symbol="btcusdt"):
    depth_url = f"wss://stream.binance.com:9443/ws/{symbol}@depth@100ms"

    buffer = []
    snapshot = None
    last_update_id = None
    order_book = None

    async with websockets.connect(depth_url) as ws:
        print("Connected to Binance depth stream")

        # 1. Buffer messages while fetching snapshot
        while snapshot is None:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                buffer.append(data)
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
                print(f"Error while buffering: {e}")
                continue

        # 2. Process buffered messages after snapshot
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

        # 3. Process new messages as usual
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                #print(f"Received message: {data}")

                u = data['u']
                U = data['U']
                if u <= last_update_id:
                    print(f"Skipping update {u} as it is not newer than last_update_id {last_update_id}")
                    continue
                if U > last_update_id + 1:
                    print("❌ Desync detectado, reseteando...")
                    snapshot = await fetch_snapshot(symbol)
                    last_update_id = snapshot['lastUpdateId']
                    print(f"✅ Nuevo snapshot recibido {snapshot['lastUpdateId']}")
                    order_book = {
                        'bids': {price: qty for price, qty in snapshot['bids']},
                        'asks': {price: qty for price, qty in snapshot['asks']}
                    }
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

                # 4. Obtener mejor bid/ask y actualizar
                best_bid = max(order_book['bids'].keys(), key=lambda x: float(x))
                best_ask = min(order_book['asks'].keys(), key=lambda x: float(x))

                bid = float(best_bid)
                ask = float(best_ask)

                current = watcher.prices.get('binance')
                if current is None or current['bid'] != bid or current['ask'] != ask:
                    watcher.update_price('binance', bid, ask)
                    print(f"Binance Watcher updated: highest bid={bid}, lowest ask={ask}")
                    ticker = await fetch_ticker(symbol)
                    print(f"Binance Ticker: bid = {ticker['bidPrice']}, ask = {ticker['askPrice']}")

            except json.JSONDecodeError:
                print("Error decoding JSON.")
            except websockets.exceptions.ConnectionClosed as e:
                print(f"WebSocket closed: {e}")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
