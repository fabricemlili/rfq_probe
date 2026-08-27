import argparse
import asyncio
import os
import sys
import time
import uuid
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

import yaml
from dotenv import load_dotenv
from tabulate import tabulate

from rfq_test.clients.websocket import TakerStreamClient
from rfq_test.config import get_environment_config
from rfq_test.crypto.wallet import Wallet
from rfq_test.utils.price import quantize_to_tick, quantize_quantity

from pyinjective.core.network import Network
from pyinjective.indexer_client import IndexerClient

from rfq_utils import InjectivePriceStream

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe maker quote coverage across all markets")
    p.add_argument("--maker", required=True, help="Injective address of the maker to watch")
    p.add_argument("--direction", default="long", choices=["long", "short"])
    p.add_argument("--quantity", type=float, default=1.0)
    p.add_argument("--margin", type=float, default=5.0)
    p.add_argument("--timeout", type=float, default=10.0, help="Quote collection timeout per market (s)")
    p.add_argument("--delay", type=float, default=0.25, help="Delay between markets (s)")
    p.add_argument("--env", default=None, help="Override RFQ_ENV (TESTNET/MAINNET/LOCAL)")
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_env(env_override: str | None) -> tuple[str, str]:
    """Return (private_key, env_name)."""
    load_dotenv(".env")
    active = (env_override or os.getenv("RFQ_ENV", "")).upper()
    if not active:
        raise SystemExit("Set RFQ_ENV in your .env or pass --env.")
    key = os.getenv(f"{active}_ARB_PRIVATE_KEY") or os.getenv(f"{active}_PRIVATE_KEY")
    if not key:
        raise SystemExit(
            f"Set {active}_ARB_PRIVATE_KEY or {active}_PRIVATE_KEY before running."
        )
    return key, active


def _all_tickers(config_arb: dict) -> list[str]:
    tickers = []
    for group in config_arb.values():
        tickers.extend(group.get("tickers", []))
    return tickers


# ─────────────────────────────────────────────────────────────────────────────
# Probe
# ─────────────────────────────────────────────────────────────────────────────

async def probe_market(
    ticker: str,
    market_id: str,
    price_stream: InjectivePriceStream,
    taker_stream: TakerStreamClient,
    wallet: Wallet,
    target_maker: str,
    args: argparse.Namespace,
) -> dict:
    """Send one RFQ for *ticker* and return a result dict."""
    result = {
        "ticker": ticker,
        "market_id": market_id[:12] + "…",
        "mark_price": None,
        "rfq_id": None,
        "total_quotes": 0,
        "maker_responded": False,
        "maker_price": None,
        "all_makers": [],
        "error": None,
    }

    # ── mark price ──────────────────────────────────────────────────────────
    try:
        mark_price = Decimal(str(price_stream.get(ticker)))
    except RuntimeError:
        result["error"] = "no mark price"
        return result

    result["mark_price"] = float(mark_price)

    # ── worst price ─────────────────────────────────────────────────────────
    worst_price_margin_bps = 200  # generous so we get quotes
    if args.direction == "long":
        worst_price = mark_price * (1 + Decimal(worst_price_margin_bps) / 10000)
        rounding = ROUND_CEILING
    else:
        worst_price = mark_price * (1 - Decimal(worst_price_margin_bps) / 10000)
        rounding = ROUND_FLOOR

    price_tick = price_stream.min_price_tick_sizes[market_id]
    worst_price = quantize_to_tick(worst_price, price_tick, rounding=rounding)

    quantity = Decimal(str(args.quantity))
    margin = Decimal(str(args.margin))
    taker_qty = max(quantity, margin / Decimal(worst_price))
    taker_qty_str = quantize_quantity(
        taker_qty, price_stream.min_quantity_tick_sizes[market_id]
    )

    # ── send request ─────────────────────────────────────────────────────────
    client_id = str(uuid.uuid4())
    expiry_ms = int(time.time() * 1000) + 300_0000

    request_data = {
        "request_address": wallet.inj_address,
        "client_id": client_id,
        "market_id": market_id,
        "direction": args.direction,
        "margin": str(margin),
        "quantity": taker_qty_str,
        "worst_price": str(worst_price),
        "expiry": expiry_ms,
    }

    try:
        ack = await taker_stream.send_request(
            request_data, wait_for_response=True, response_timeout=5.0
        )
        if not ack or ack.get("type") != "ack":
            result["error"] = f"no ACK (got {ack})"
            return result
        rfq_id = int(ack["rfq_id"])
        result["rfq_id"] = rfq_id
    except Exception as exc:
        result["error"] = f"send failed: {exc}"
        return result

    # ── collect quotes ───────────────────────────────────────────────────────
    try:
        quotes = await taker_stream.collect_quotes(
            rfq_id=rfq_id, timeout=args.timeout, min_quotes=1
        )
    except Exception as exc:
        result["error"] = f"collect failed: {exc}"
        return result

    result["total_quotes"] = len(quotes)
    result["all_makers"] = [q["maker"] for q in quotes]

    target_lower = target_maker.lower()
    for q in quotes:
        if q["maker"].lower() == target_lower:
            result["maker_responded"] = True
            result["maker_price"] = q["price"]
            break

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    args = parse_args()

    with open("config.yaml") as f:
        config_arb = yaml.safe_load(f)

    pk, rfq_env = _load_env(args.env)
    wallet = Wallet.from_private_key(pk)
    print(f"Taker address : {wallet.inj_address}")
    print(f"Target maker  : {args.maker}")
    print(f"Environment   : {rfq_env}")
    print(f"Direction     : {args.direction}")
    print()

    # ── network ──────────────────────────────────────────────────────────────
    if rfq_env == "TESTNET":
        network = Network.testnet()
    elif rfq_env == "MAINNET":
        network = Network.mainnet()
    elif rfq_env == "LOCAL":
        network = Network.local()
    else:
        raise SystemExit(f"Unknown RFQ_ENV: {rfq_env}")

    # ── indexer ───────────────────────────────────────────────────────────────
    print("Connecting to indexer…")
    while True:
        try:
            indexer = IndexerClient(network)
            await indexer.fetch_info()
            break
        except Exception:
            await asyncio.sleep(2)
    print("Indexer ready.\n")

    # ── price stream ──────────────────────────────────────────────────────────
    config_env = get_environment_config()
    price_stream = InjectivePriceStream(indexer=indexer)
    await price_stream.start()
    print("Waiting 5 s for initial price data…")
    await asyncio.sleep(5)

    # ── taker stream ──────────────────────────────────────────────────────────
    taker_stream = TakerStreamClient(
        base_url=config_env.indexer.ws_endpoint,
        request_address=wallet.inj_address,
        timeout=30.0,
    )
    await taker_stream.connect()
    print("Taker stream connected.\n")

    # ── probe each market ─────────────────────────────────────────────────────
    tickers = _all_tickers(config_arb)
    results = []

    for i, ticker in enumerate(tickers, 1):
        market_id = price_stream.ticker_to_id.get(ticker)
        if not market_id:
            results.append({
                "ticker": ticker,
                "market_id": "—",
                "mark_price": None,
                "rfq_id": None,
                "total_quotes": 0,
                "maker_responded": False,
                "maker_price": None,
                "all_makers": [],
                "error": "market not found",
            })
            continue

        print(f"[{i}/{len(tickers)}] {ticker}…", end=" ", flush=True)
        r = await probe_market(
            ticker=ticker,
            market_id=market_id,
            price_stream=price_stream,
            taker_stream=taker_stream,
            wallet=wallet,
            target_maker=args.maker,
            args=args,
        )
        results.append(r)

        # live feedback
        if r["error"]:
            status = f"ERROR: {r['error']}"
        elif r["maker_responded"]:
            status = f"✓  maker quoted @ {r['maker_price']}  ({r['total_quotes']} quote(s) total)"
        elif r["total_quotes"] > 0:
            status = f"✗  no quote from target  ({r['total_quotes']} quote(s) from others)"
        else:
            status = "✗  no quotes at all"

        print(status)

        if i < len(tickers):
            await asyncio.sleep(args.delay)

    # ── cleanup ───────────────────────────────────────────────────────────────
    await taker_stream.close()
    await price_stream.stop()

    # ── summary table ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"RESULTS  —  maker: …{args.maker[-8:]}")
    print("=" * 70)

    responded = [r for r in results if r["maker_responded"]]
    no_response = [r for r in results if not r["maker_responded"] and not r["error"]]
    errors = [r for r in results if r["error"]]

    table_rows = []
    for r in results:
        if r["error"]:
            status_str = f"ERROR: {r['error']}"
        elif r["maker_responded"]:
            status_str = f"QUOTED @ {r['maker_price']}"
        else:
            status_str = f"MISSING  ({r['total_quotes']} other quote(s))"

        table_rows.append([
            r["ticker"],
            f"{r['mark_price']:.4f}" if r["mark_price"] else "—",
            r["rfq_id"] or "—",
            r["total_quotes"],
            "YES" if r["maker_responded"] else "no",
            status_str,
        ])

    print(tabulate(
        table_rows,
        headers=["Ticker", "Mark Price", "RFQ ID", "# Quotes", "Maker OK", "Status"],
        tablefmt="simple",
    ))

    print(f"\nSummary: {len(responded)}/{len(results)} ({len(responded)/len(results)*100:.2f}%) markets quoted by target maker")
    if no_response:
        print("\nMarkets where maker did NOT respond:")
        for r in no_response:
            others = ", ".join(f"…{m[-5:]}" for m in r["all_makers"]) or "none"
            print(f"  • {r['ticker']}  (other makers: {others})")
    if errors:
        print("\nMarkets with errors:")
        for r in errors:
            print(f"  • {r['ticker']}: {r['error']}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
