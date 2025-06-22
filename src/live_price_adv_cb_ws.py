import json
import websockets

# Coinbase Advanced Trade WS without authentication
async def listen_coinbase_order_book(watcher, symbol="BTC-USD"):
    url = "wss://advanced-trade-ws.coinbase.com"
    subscribe_msg = {
        "type": "subscribe",
        "product_ids": [symbol],
        "channel": "level2"
    }
    order_book = None
    expected_sequence = 0

    async with websockets.connect(url, max_size=10 * 1024 * 1024) as ws:
        await ws.send(json.dumps(subscribe_msg))
        print("Connecting to Coinbase WebSocket.")
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)

                # Handle sequence number for updates
                sequence_num = data.get("sequence_num")
                if sequence_num is None:
                    print("No sequence_num in message, skipping...")
                    continue
                else:
                    if sequence_num != expected_sequence:
                        print(f"Sequence mismatch: expected {expected_sequence}, got {sequence_num}. Reconnecting Websocket...")
                        # Clear coinbase info in watcher
                        if hasattr(watcher, "prices") and "coinbase" in watcher.prices:
                            watcher.prices.pop("coinbase")
                        try:
                            await ws.close()
                        except Exception as e:
                            print(f"Error closing websocket: {e}")
                        # Recursive call to restart the listener
                        return await listen_coinbase_order_book(watcher, symbol)

                if data.get("channel") == "l2_data":
                    # Process events
                    for event in data.get("events", []):
                        if event.get("type") == "snapshot":
                            bids = []
                            asks = []
                            for update in event.get("updates", []):
                                side = update.get("side")
                                price = update.get("price_level")
                                qty = update.get("new_quantity")
                                if side == "bid":
                                    bids.append((price, qty))
                                elif side == "ask" or side == "offer":
                                    asks.append((price, qty))
                            order_book = {
                                'bids': {price: qty for price, qty in bids},
                                'asks': {price: qty for price, qty in asks}
                            }
                            print(f"✅ Coinbase snapshot received. Bids: {len(order_book['bids'])}, Asks: {len(order_book['asks'])}")
                            continue

                        elif event.get("type") == "update":
                            for update in event.get("updates", []):
                                side = update.get("side")
                                price = update.get("price_level")
                                qty = update.get("new_quantity")
                                if side == "bid":
                                    if float(qty) == 0:
                                        order_book['bids'].pop(price, None)
                                    else:
                                        order_book['bids'][price] = qty
                                elif side == "ask" or side == "offer":
                                    if float(qty) == 0:
                                        order_book['asks'].pop(price, None)
                                    else:
                                        order_book['asks'][price] = qty
                            # Update watcher if there are bids and asks
                            if order_book['bids'] and order_book['asks']:
                                best_bid = max(order_book['bids'].keys(), key=lambda x: float(x))
                                best_ask = min(order_book['asks'].keys(), key=lambda x: float(x))
                                bid = float(best_bid)
                                ask = float(best_ask)
                                current = watcher.prices.get('coinbase')
                                if current is None or bid != current.get('bid') or ask != current.get('ask'):
                                    watcher.update_price('coinbase', bid, ask)
                                    print(f"Coinbase watcher updated: highest bid={bid}, lowest ask={ask}")
                    expected_sequence += 1


                elif data.get("channel") == "subscriptions":
                    print(f"Subscription successful for: {data['events'][0]['subscriptions']}")
                    expected_sequence += 1
                
                else:
                    print(f"Wrong channel '{data.get('channel')}', skipping...")

            except json.JSONDecodeError:
                print("Error al parsear el mensaje JSON.")
            except websockets.exceptions.ConnectionClosed as e:
                print(f"Conexión cerrada: {e}")
                break
            except Exception as e:
                print(f"Error inesperado: {e}")
                raise