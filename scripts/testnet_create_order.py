import ccxt

# === 1. Configura tus claves de testnet ===
api_key = 'Iy9PVW0ydD18KfydWqbspxCOfVrtpbyxXzFKqcN5gAuy8TvuxXUBKfLUZACN7tLj'
api_secret = '14cHyfOg9o7eos0OAXTBXl5n82AN1clj3lkkSE2e3Z8TanNbfYZdEsjYclLu9D59'

# === 2. Inicializa Binance en testnet ===
binance = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',  # Spot market
    }
})

# Activa el modo testnet de forma segura
binance.set_sandbox_mode(True)

# === 3. Cargar mercados ===
markets = binance.load_markets()

# === 4. Definir el par y cantidad ===
symbol = 'BTC/USDT'
amount = 10  # Ajusta según tu balance de testnet

# === 5. Crear orden de compra de mercado ===
try:
    print("🟢 Creando orden de compra...")
    order = binance.create_order(
        symbol=symbol,
        type='market',
        side='buy',
        amount=amount
    )
    print("✅ Orden creada:")
    print(order)

except ccxt.BaseError as e:
    print("❌ Error al crear la orden:")
    print(str(e))

# === 6. Consultar balance ===
print("\n💰 Consultando balance actual:")
balance = binance.fetch_balance()
print(balance['total']['USDT'])
print(balance['total']['BTC'])   # Puedes ver balance por moneda: balance['total']['BTC'], etc.
