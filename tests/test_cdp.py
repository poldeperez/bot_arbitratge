from coinbase.websocket import WSClient
import time

api_key = "organizations/b8b1b26d-8537-4e6c/apiKeys/837b-c2213ff5f9b0"
api_secret = """-----BEGIN EC PRIVATE KEY-----
Ynvov6nW6VTMakcPeXwYXO5bNFhs3RXQ3TA8diVKZLBZGG4Q4U3gfivcdQucXnfMXSuxLFO905yGLRT8OpAIWQ==
-----END EC PRIVATE KEY-----"""

def on_message(msg):
    print("Mensaje recibido:", msg)

client = WSClient(
    api_key=api_key,
    api_secret=api_secret,
    on_message=on_message
)

# open the connection and subscribe to the ticker and heartbeat channels for BTC-USD and ETH-USD
client.open()
client.subscribe(product_ids=["BTC-USD", "ETH-USD"], channels=["ticker", "heartbeats"])

# wait 10 seconds
time.sleep(10)

# unsubscribe from the ticker channel and heartbeat channels for BTC-USD and ETH-USD, and close the connection
client.unsubscribe(product_ids=["BTC-USD", "ETH-USD"], channels=["ticker", "heartbeats"])
client.close()
