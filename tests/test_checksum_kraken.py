import zlib
import binascii

message = {'channel': 'book', 'type': 'snapshot', 'data': [{'symbol': 'BTC/USDT', 'bids': [{'price': '105906.7', 'qty': '0.09440620'}, {'price': '105901.7', 'qty': '0.02297789'}, {'price': '105901.6', 'qty': '0.09441075'}, {'price': '105901.4', 'qty': '0.02400000'}, {'price': '105897.8', 'qty': '0.01980353'}, {'price': '105897.6', 'qty': '0.01877140'}, {'price': '105894.1', 'qty': '0.00590000'}, {'price': '105894.0', 'qty': '0.06080500'}, {'price': '105892.9', 'qty': '0.05700000'}, {'price': '105889.1', 'qty': '0.00630000'}, {'price': '105888.7', 'qty': '0.05665135'}, {'price': '105888.1', 'qty': '0.13300000'}, {'price': '105887.4', 'qty': '0.04700000'}, {'price': '105887.3', 'qty': '0.04300000'}, {'price': '105886.7', 'qty': '0.14160549'}, {'price': '105885.9', 'qty': '0.01844747'}, {'price': '105885.6', 'qty': '0.54379100'}, {'price': '105879.5', 'qty': '0.28806464'}, {'price': '105876.7', 'qty': '0.14164938'}, {'price': '105875.9', 'qty': '0.04300000'}, {'price': '105875.2', 'qty': '0.63442300'}, {'price': '105871.6', 'qty': '0.10427740'}, {'price': '105868.3', 'qty': '0.02821348'}, {'price': '105865.3', 'qty': '0.04300000'}, {'price': '105864.7', 'qty': '0.81568600'}], 'asks': [{'price': '105906.8', 'qty': '0.05665135'}, {'price': '105910.0', 'qty': '0.70000000'}, {'price': '105910.6', 'qty': '0.06080300'}, {'price': '105911.3', 'qty': '0.28682600'}, {'price': '105915.8', 'qty': '0.00061514'}, {'price': '105916.6', 'qty': '0.09439743'}, {'price': '105918.9', 'qty': '0.54378900'}, {'price': '105921.1', 'qty': '0.09439338'}, {'price': '105925.8', 'qty': '0.04300000'}, {'price': '105926.0', 'qty': '0.09438908'}, {'price': '105927.7', 'qty': '0.02821348'}, {'price': '105930.1', 'qty': '0.00700000'}, {'price': '105933.5', 'qty': '0.00920000'}, {'price': '105934.5', 'qty': '0.00297419'}, {'price': '105935.3', 'qty': '0.05700000'}, {'price': '105937.1', 'qty': '0.00090000'}, {'price': '105937.2', 'qty': '0.19500000'}, {'price': '105937.6', 'qty': '0.05727740'}, {'price': '105938.1', 'qty': '0.04300000'}, {'price': '105941.7', 'qty': '0.00943915'}, {'price': '105943.3', 'qty': '0.63448600'}, {'price': '105944.5', 'qty': '0.86664740'}, {'price': '105944.6', 'qty': '0.14155866'}, {'price': '105944.9', 'qty': '0.02831660'}, {'price': '105948.7', 'qty': '0.04300000'}], 'checksum': 4162058887}]}


message__ ={
   "channel": "book",
   "type": "snapshot",
   "data": [
      {
         "symbol": "BTC/USD",
         "bids": [
            {
               "price": "45283.5",
               "qty": "0.10000000"
            },
            {
               "price": "45283.4",
               "qty": "1.54582015"
            },
            {
               "price": "45282.1",
               "qty": "0.10000000"
            },
            {
               "price": "45281.0",
               "qty": "0.10000000"
            },
            {
               "price": "45280.3",
               "qty": "1.54592586"
            },
            {
               "price": "45279.0",
               "qty": "0.07990000"
            },
            {
               "price": "45277.6",
               "qty": "0.03310103"
            },
            {
               "price": "45277.5",
               "qty": "0.30000000"
            },
            {
               "price": "45277.3",
               "qty": "1.54602737"
            },
            {
               "price": "45276.6",
               "qty": "0.15445238"
            }
         ],
         "asks": [
            {
               "price": "45285.2",
               "qty": "0.00100000"
            },
            {
               "price": "45286.4",
               "qty": "1.54571953"
            },
            {
               "price": "45286.6",
               "qty": "1.54571109"
            },
            {
               "price": "45289.6",
               "qty": "1.54560911"
            },
            {
               "price": "45290.2",
               "qty": "0.15890660"
            },
            {
               "price": "45291.8",
               "qty": "1.54553491"
            },
            {
               "price": "45294.7",
               "qty": "0.04454749"
            },
            {
               "price": "45296.1",
               "qty": "0.35380000"
            },
            {
               "price": "45297.5",
               "qty": "0.09945542"
            },
            {
               "price": "45299.5",
               "qty": "0.18772827"
            }
         ],
         "checksum": 3310070434
      }
   ]
}

def build_checksum_str(order_book):
    def clean(val):
        # Remove decimal and leading zeros
        s = str(val).replace('.', '')
        return s.lstrip('0') or '0'
    asks = sorted(order_book['asks'], key=lambda x: float(x['price']))
    bids = sorted(order_book['bids'], key=lambda x: -float(x['price']))
    parts = []
    for entry in asks:
        price, qty = entry['price'], entry['qty']
        print(f"Kraken ask: {price} qty: {qty}")
        print(f"Kraken ask clean: {clean(price)} qty: {clean(qty)}")
        parts.append(f"{clean(price)}{clean(qty)}")
    for entry in bids:
        price, qty = entry['price'], entry['qty']
        parts.append(f"{clean(price)}{clean(qty)}")
    return ''.join(parts)

def check(order_book):
   new_checksum = order_book.get('checksum')
   if new_checksum is not None:
      checksum_str = build_checksum_str(order_book)
      #computed_checksum = zlib.crc32(checksum_str.encode())
      checksum_input = f"{checksum_str}".encode('utf-8')
      computed_checksum = binascii.crc32(checksum_input)
      print(f"Kraken checksum, str: {checksum_str} computed: {computed_checksum}, received: {new_checksum}")
      if computed_checksum != new_checksum:
         print(f"❌ Kraken checksum mismatch! Local: {computed_checksum}, Exchange: {new_checksum}. Refetching snapshot...")
                    

if __name__ == "__main__":
    check(message['data'][0])