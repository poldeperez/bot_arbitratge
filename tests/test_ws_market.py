import asyncio
import websockets
import json

async def test_binance_ws():
    url = "wss://stream.binance.com:9443/ws/btcusdt@trade"
    last_price = None
    try:
        async with websockets.connect(url) as ws:
            print("✅ Conectado a Binance WebSocket. Esperando datos...")
            while True:
                message = await ws.recv()
                data = json.loads(message)
                price = data.get("p")  # El precio viene como string

                if price != last_price:
                    print(f"📈 Nuevo precio BTC/USDT: {price}")
                    last_price = price
    except Exception as e:
        print(f"❌ Error al conectar: {e}")

async def test_coinbase_ws(symbol="BTC-USD"):
    url = "wss://ws-feed.exchange.coinbase.com"
    subscribe_message = {
        "type": "subscribe",
        "channels": [{"name": "matches", "product_ids": [symbol]}]
    }
    last_price = None

    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps(subscribe_message))
            print(f"✅ Conectado a Coinbase WebSocket para {symbol}. Esperando datos...")
            while True:
                message = await ws.recv()
                data = json.loads(message)

                if data.get("type") == "match" and data.get("product_id") == symbol:
                    price = data.get("price")  # Precio como string

                    if price != last_price:
                        print(f"📈 Nuevo precio {symbol}: {price}")
                        last_price = price
    except Exception as e:
        print(f"❌ Error al conectar: {e}")
                


if __name__ == "__main__":
    # asyncio.run(test_binance_ws())
    asyncio.run(test_coinbase_ws("BTC-USD"))
