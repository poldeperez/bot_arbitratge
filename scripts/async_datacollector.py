import asyncio
import ccxt.async_support as ccxt  # Importar versión async de ccxt
import time

# Comisiones por exchange
fees = {
        "binance": 0.001,
        "kraken": 0.0026,
        "coinbase": 0.005,
        "bitstamp": 0.005
    }

async def fetch_ticker(exchange_id, symbol):
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class()
    try:
        ticker = await exchange.fetch_ticker(symbol)
        return {
            "exchange": exchange_id,
            "timestamp": ticker['timestamp'],
            "bid": ticker['bid'],
            "ask": ticker['ask'],
            "price": ticker['last']
        }
    except Exception as e:
        return {"exchange": exchange_id, "error": str(e)}
    finally:
        await exchange.close()

async def main():
    symbol = "BTC/USDT"
    exchanges = ["binance", "kraken", "coinbase", "bitstamp"]

    start = time.time()
    tasks = [fetch_ticker(e, symbol) for e in exchanges]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start

    clean_results = []
    print(f"\n📡 Datos recibidos en {elapsed:.3f} segundos:\n")
    for r in results:
        if "error" in r:
            print(f"❌ {r['exchange'].capitalize()}: {r['error']}")
        else:
            print(f"✅ {r['exchange'].capitalize()}: Bid {r['bid']} | Ask {r['ask']} | Timestamp: {r['timestamp']}")
            clean_results.append(r)  # solo los válidos
    
    # Lógica de arbitraje: encontrar el bid más alto y ask más bajo
    if len(clean_results) >= 2:
        highest_bid = max(clean_results, key=lambda x: x["bid"])
        lowest_ask = min(clean_results, key=lambda x: x["ask"])

        buy_price = lowest_ask["ask"]
        sell_price = highest_bid["bid"]
        buy_fee = fees.get(lowest_ask["exchange"], 0)
        sell_fee = fees.get(highest_bid["exchange"], 0)

        effective_buy = buy_price * (1 + buy_fee)
        effective_sell = sell_price * (1 - sell_fee)
        profit = effective_sell - effective_buy
        spread_pct = (profit / effective_buy) * 100

        print(f"   Comprar en {lowest_ask['exchange'].capitalize()} a {buy_price:.2f} USD (fee {buy_fee*100:.2f}%)")
        print(f"   Vender en {highest_bid['exchange'].capitalize()} a {sell_price:.2f} USD (fee {sell_fee*100:.2f}%)")
        print(f"   ➕ Precio efectivo compra: {effective_buy:.2f}")
        print(f"   ➖ Precio efectivo venta:  {effective_sell:.2f}")
        print(f"   💰 Beneficio neto: {profit:.2f} USD ({spread_pct:.4f}%)")

        if profit > 0:
            print("\n💰 Oportunidad de arbitraje:")
        else:
            print("\n❌ No hay oportunidad de arbitraje rentable.")
    else:
        print("⚠️ No hay suficientes datos válidos para calcular el arbitraje.")

if __name__ == "__main__":
    asyncio.run(main())