import ccxt.async_support as ccxt
import asyncio
import json
import os
from settings import EXCHANGES

FEES_FILE = "exchange_fees.json"
exchange_list = EXCHANGES

async def fetch_fee(exchange_id):
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({'enableRateLimit': True})
        await exchange.load_markets()
        fees = exchange.fees.get('trading', {})
        await exchange.close()
        return {
            'success': True,
            'fees': fees
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

async def main():
    # Cargar archivo si existe
    if os.path.exists(FEES_FILE):
        with open(FEES_FILE, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    else:
        existing_data = {}

    updated_data = existing_data.copy()

    for exchange_id in exchange_list:
        print(f"🔄 Buscando fees para {exchange_id}...")
        # Solo buscar si no está o si falló previamente
        if exchange_id not in existing_data or not existing_data[exchange_id].get("success"):
            result = await fetch_fee(exchange_id)
            updated_data[exchange_id] = result
            print(f"✅ Guardado fees de {exchange_id}" if result["success"] else f"❌ Error en {exchange_id}: {result['error']}")

    # Guardar resultados en JSON
    with open(FEES_FILE, 'w', encoding='utf-8') as f:
        json.dump(updated_data, f, indent=4)

    print("📁 Archivo actualizado:", FEES_FILE)

if __name__ == "__main__":
    asyncio.run(main())
