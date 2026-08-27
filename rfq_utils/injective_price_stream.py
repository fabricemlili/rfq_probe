import asyncio
from typing import Any, Dict
from decimal import Decimal
from typing import Any, Dict

from rfq_test.utils.price import quantize_to_tick
from pyinjective.indexer_client import IndexerClient
# from rfq_utils.price_csv_logger import PriceLogger


DEFAULT_MAX_MARKET_IDS_PER_STREAM = 40


class InjectivePriceStream:
    """Streams oracle prices for derivative markets and provides price access."""
    
    def __init__(self, indexer: IndexerClient, csv_path: str = "prices.csv"):
        self.indexer = indexer
        self.prices: dict[str, float] = {}
        self.price_tasks: list[asyncio.Task] = []
        self.max_market_ids_per_stream = DEFAULT_MAX_MARKET_IDS_PER_STREAM
        self.subscribers: dict[str, list[asyncio.Queue]] = {}
        # self.logger = PriceLogger(csv_path=csv_path)
        self.id_to_ticker: dict[str, str] = {}
        self.ticker_to_id: dict[str, str] = {}
        self.min_price_tick_sizes: dict[str, Decimal] = {}
        self.min_quantity_tick_sizes: dict[str, Decimal] = {}

    async def _initialize(self):
        resp_markets = await self.indexer.fetch_derivative_markets(market_statuses=["active"])
        self.id_to_ticker = {m['marketId']: m['ticker'] for m in resp_markets['markets']}
        self.ticker_to_id = {m['ticker']: m['marketId'] for m in resp_markets['markets']}
        self.min_price_tick_sizes = {
            m['marketId']: Decimal(m['minPriceTickSize']) / (Decimal(10) ** m["oracleScaleFactor"])
            for m in resp_markets['markets']
        }
        self.min_quantity_tick_sizes = {
            m['marketId']: Decimal(m['minQuantityTickSize'])
            for m in resp_markets['markets']
        }

        # print ticker
        # print("📈 Active markets:")
        # for market_id, ticker in self.id_to_ticker.items():
        #     print(f"{ticker} ({market_id})")

    def subscribe(self, asset: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        self.subscribers.setdefault(asset, []).append(q)

        if asset in self.prices:
            q.put_nowait(self.prices[asset])

        return q

    def unsubscribe(self, asset: str, queue: asyncio.Queue) -> None:
        subs = self.subscribers.get(asset)
        if subs:
            try:
                subs.remove(queue)
            except ValueError:
                pass
            if not subs:
                del self.subscribers[asset]

    async def start(self):
        """Initialize markets and start price streaming."""
        await self._initialize()
        # self.logger.start()
        
        all_market_ids = list(self.id_to_ticker.keys())
        chunks = [
            all_market_ids[i : i + self.max_market_ids_per_stream]
            for i in range(0, len(all_market_ids), self.max_market_ids_per_stream)
        ]
        print(f"📊 Streaming {len(all_market_ids)} markets in {len(chunks)} stream(s)")
        
        self.price_tasks = [asyncio.create_task(self._stream(chunk)) for chunk in chunks]
    
    async def stop(self):
        """Stop price streaming and cleanup."""
        for task in self.price_tasks:
            task.cancel()
        self.price_tasks = []
        # self.logger.stop()

    async def _price_event_processor(self, event: Dict[str, Any]):
        market_id = event['marketId']
        timestamp = event['timestamp']
        price = float(quantize_to_tick(
            event["price"],
            self.min_price_tick_sizes[market_id]
        ))

        asset = self.id_to_ticker.get(market_id)
        if not asset:
            return

        self.prices[asset] = price
        # self.logger.log(timestamp, asset, price)

        subs = self.subscribers.get(asset, [])
        for q in subs:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(price)

    async def _stream(self, market_ids: list[str]):
        while True:
            try:
                await self.indexer.listen_oracle_prices_by_markets_updates(
                    market_ids=market_ids,
                    callback=self._price_event_processor,
                    on_end_callback=None,
                    on_status_callback=None,
                )
            except Exception as e:
                print(f"Price stream error ({len(market_ids)} markets):", e)
                await asyncio.sleep(1)

    def get(self, asset: str) -> float:
        price = self.prices.get(asset)
        if price is None:
            raise RuntimeError("Price not ready for asset: %s" % asset)
        return price
