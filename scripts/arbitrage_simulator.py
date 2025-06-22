import ccxt
from tabulate import tabulate

def simulate_trade(exchange: str, symbol: str, side: str, amount: float, order_type: str, limit_price: float = None, depth: int = 10):
    """
    Simula una orden de compra o venta con datos reales de un exchange.

    Parámetros:
        - exchange (str): nombre del exchange (ej: 'binance', 'kraken')
        - symbol (str): par de trading (ej: 'BTC/USDT')
        - side (str): 'buy' o 'sell'
        - amount (float): cantidad a comprar o vender
        - order_type (str): 'market' o 'limit'
        - limit_price (float): requerido para orden límite
        - depth (int): profundidad del order book

    Retorna:
        - avg_price (float): precio promedio de ejecución
        - filled_amount (float): cantidad ejecutada
        - slippage_info (str): texto explicativo
    """

    # === 1. Inicializar exchange
    try:
        ex = getattr(ccxt, exchange.lower())
        ex_obj = ex()
        symbol = symbol.upper()
    except AttributeError:
        return None, 0, f"❌ Exchange '{exchange}' no soportado por ccxt."
    
    # === 1.1 Verificar si el símbolo existe en el exchange
    ex_obj.load_markets()
    if symbol not in ex_obj.markets:
        return None, 0, f"❌ Símbolo '{symbol}' no válido en {ex_obj.name}."
    
    # === 2. Obtener order book
    try:
        ticker = ex_obj.fetch_ticker(symbol)
        book = ex_obj.fetch_order_book(symbol, limit=depth)
        asks = [{"price": price, "amount": vol} for price, vol in book['asks']]
        bids = [{"price": price, "amount": vol} for price, vol in book['bids']]

        # Mostrar precio, asks (ventas) y bids (compras)
        print(f"📈 Precio actual (último trade): {ticker['last']} USDT")
        print(f"🟢 Mejor precio de compra (bid): {ticker['bid']} USDT")
        print(f"🔴 Mejor precio de venta (ask): {ticker['ask']} USDT")
        print(f"📊 Volumen 24h: {ticker['baseVolume']} BTC")
        print(f"\n📘 ORDER BOOK: {ex_obj.name.upper()} {symbol}")
        print(f"\n🔴 Asks (vendedores):")
        for price, amount in book['asks']:
            print(f"Precio: {price:.2f} USDT | Cantidad: {amount} BTC")

        print("\n🟢 Bids (compradores):")
        for price, amount in book['bids']:
            print(f"Precio: {price:.2f} USDT | Cantidad: {amount} BTC")
    except Exception as e:
        return None, 0, f"❌ Error al obtener order book: {e}"
    
    levels = asks if side == 'buy' else bids
    remaining = amount
    total_cost = 0
    total_filled = 0

    # === 3. Filtrar si es limit order
    if order_type == 'limit':
        if limit_price is None:
            raise ValueError("Se requiere 'limit_price' para orden límite.")
        if side == 'buy':
            levels = [l for l in levels if l["price"] <= limit_price]
        else:
            levels = [l for l in levels if l["price"] >= limit_price]

    # === 4. Simulación de ejecución
    for level in levels:
        price = level["price"]
        available = level["amount"]
        trade_size = min(remaining, available)
        total_cost += trade_size * price
        remaining -= trade_size
        total_filled += trade_size
        if remaining <= 0:
            break

    # === 5. Resultados
    if total_filled == 0:
        return 0, 0, "❌ No se pudo ejecutar ninguna parte de la orden."

    avg_price = total_cost / total_filled
    slippage = "✔️ Orden completada."
    if total_filled < amount:
        slippage = f"⚠️ Solo se ejecutó {total_filled:.4f} de {amount}. Parcial."

    return avg_price, total_filled, slippage

if __name__ == "__main__":
    precio, ejecutado, nota = simulate_trade(
        exchange='binance',
        symbol='BTC/USDT',
        side='buy',
        amount=1.5,
        order_type='market'
    )
    print(f"🟢 MARKET: Ejecutado {ejecutado} BTC a promedio {precio:.2f} USD — {nota}")

    preciok, ejecutadok, notak = simulate_trade(
        exchange='coinbase',
        symbol='BTC/USDT',
        side='buy',
        amount=1.5,
        order_type='market'
    )
    print(f"🟢 MARKET: Ejecutado {ejecutadok} BTC a promedio {preciok:.2f} USD — {notak}")
