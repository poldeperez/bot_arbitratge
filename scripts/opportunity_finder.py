import ccxt.async_support as ccxt
import asyncio
import logging
from config.settings import INTER_LOGGING_PATH, EXCHANGES
import json
import time
import csv


__all__ = [
    'OpportunityFinder',
    'get_opportunity_for_market'
]

file_logger = logging.getLogger(INTER_LOGGING_PATH + __name__)

def load_exchange_fees(path='exchange_fees.json'):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        file_logger.warning(f"Could not load fees: {e}")
        return {}

def get_taker_fee(exchange_id: str) -> float:
    EXCHANGE_FEES = load_exchange_fees()
    try:
        return EXCHANGE_FEES[exchange_id]["fees"]["taker"]
    except KeyError:
        return 0.0
    
def save_opportunity(opportunity, filename="opportunities.csv"):
    with open(filename, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            time.strftime('%Y-%m-%d %H:%M:%S'),
            opportunity['ticker'],
            opportunity['lowest_ask']['exchange'].id,
            opportunity['lowest_ask']['price'],
            opportunity['highest_bid']['exchange'].id,
            opportunity['highest_bid']['price'],
            opportunity['highest_bid']['price'] - opportunity['lowest_ask']['price']
        ])

class InterExchangeAdapter(logging.LoggerAdapter):

    def __init__(self, logger, extra):
        super(InterExchangeAdapter, self).__init__(logger, extra)

    def process(self, msg, kwargs):
        return f"Invocation#{self.extra['invocation_id']} - Market#{self.extra['market']} - {msg}", kwargs


class OpportunityFinder:

    def __init__(self, market_name, exchanges=None, name=True, invocation_id=0):
        """
        An object of type OpportunityFinder finds the largest price disparity between exchanges for a given
        cryptocurrency market by finding the exchange with the lowest market ask price and the exchange with the
        highest market bid price.
        """
        self.adapter = InterExchangeAdapter(file_logger, {'invocation_id': invocation_id, 'market': market_name})
        self.adapter.debug(f'Initializing OpportunityFinder for {market_name}')

        if exchanges is None:
            self.adapter.warning('Parameter name\'s being false has no effect.')

        if name:
            exchanges = [getattr(ccxt, exchange_id)() for exchange_id in exchanges]

        self.exchange_list = exchanges
        self.market_name = market_name
        self.highest_bid = {'exchange': None, 'price': -1}
        self.lowest_ask = {'exchange': None, 'price': float('Inf')}
        self.adapter.debug(f'Initialized OpportunityFinder for {market_name}')

    async def _test_bid_and_ask(self, exchange):
        """
        Retrieves the bid and ask for self.market_name on self.exchange_name. If the retrieved bid > self.highest_bid,
        sets self.highest_bid to the retrieved bid. If retrieved ask < self.lowest ask, sets self.lowest_ask to the
        retrieved ask.
        """
        self.adapter.info(f'Checking if {exchange.id} qualifies for the highest bid or lowest ask for {self.market_name}')
        if not isinstance(exchange, ccxt.Exchange):
            raise ValueError("exchange is not a ccxt Exchange instance.")

        
        try:
            self.adapter.info(f'Fetching ticker from {exchange.id} for {self.market_name}')
            ticker = await exchange.fetch_ticker(self.market_name)
            self.adapter.info(f'Fetched ticker from {exchange.id} for {self.market_name}')
            
            raw_ask = ticker['ask']
            raw_bid = ticker['bid']
            fee = get_taker_fee(exchange.id.lower())
            adjusted_ask = round(raw_ask * (1 + fee), 2) if raw_ask else float("inf")
            adjusted_bid = round(raw_bid * (1 - fee), 2) if raw_bid else -1

            if adjusted_bid > self.highest_bid['price']:
                self.highest_bid = {
                    'price': adjusted_bid,
                    'exchange': exchange,
                    'raw_price': raw_bid,
                    'fee': fee
                }

            if adjusted_ask < self.lowest_ask['price']:
                self.lowest_ask = {
                    'price': adjusted_ask,
                    'exchange': exchange,
                    'raw_price': raw_ask,
                    'fee': fee
                }
            self.adapter.debug(f"Fee for {exchange.id}: {fee} (raw ask: {raw_ask}, adjusted: {adjusted_ask})")
            self.adapter.info(f'Checked if exchange {exchange.id} qualifies for the highest bid or lowest ask for market {self.market_name}')
        except Exception as e:
            self.adapter.error(f"Error processing exchange {exchange.id}: {e}")
        finally:
            self.adapter.debug(f'Closing connection to {exchange.id}')
            await exchange.close()
            self.adapter.debug(f'Closed connection to {exchange.id}')

    async def find_min_max(self):
        tasks = [asyncio.create_task(self._test_bid_and_ask(exchange_name)) for exchange_name in self.exchange_list]
        await asyncio.gather(*tasks)

        return {'highest_bid': self.highest_bid,
                'lowest_ask': self.lowest_ask,
                'ticker': self.market_name}


async def get_opportunity_for_market(ticker, exchanges=None, name=True, invocation_id=0):
    file_logger.info(f'Invocation#{invocation_id} - Searching lowest ask and highest bid for {ticker}')
    finder = OpportunityFinder(ticker, exchanges=exchanges, name=name)
    result = await finder.find_min_max()
    file_logger.info(f"Invocation#{invocation_id} - Found lowest ask ({result['lowest_ask']['exchange']} - {result['lowest_ask']['price']}) and highest bid ({result['highest_bid']['exchange']} - {result['highest_bid']['price']}) for {ticker}")
    return result

# Execution of main

async def main():
    # Define aquí el ticker (par de criptomonedas) y los exchanges que quieres comparar
    ticker = 'ETH/USDT'
    exchange_list = EXCHANGES
    start = time.time()
    try:
        opportunity = await get_opportunity_for_market(ticker, exchange_list, name=True)
        elapsed = time.time() - start
        profit = opportunity['highest_bid']['price'] - opportunity['lowest_ask']['price']
        if profit > 0:
            file_logger.info(f"Opportunity found! Profit: {profit:.2f} USDT")
            file_logger.info(f"Highest Bid: {opportunity['highest_bid']['price']} in {opportunity['highest_bid']['exchange'].id}")
            file_logger.info(f"Lowest Ask: {opportunity['lowest_ask']['price']} in {opportunity['lowest_ask']['exchange'].id}")
            save_opportunity(opportunity)
        else:
            file_logger.info("No profitable opportunity found.")
        file_logger.info(f"Datos recibidos en {elapsed:.3f} segundos")
    except Exception as e:
        file_logger.error(f"Error al buscar oportunidad: {e}")


if __name__ == "__main__":
    # Configurar logging para consola y archivo
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("log_op_finder.txt", encoding="utf-8")
        ]
    )
    
    asyncio.run(main())