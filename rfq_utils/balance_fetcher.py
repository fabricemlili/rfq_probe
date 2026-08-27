from rfq_test.crypto.wallet import Wallet
from pyinjective.async_client_v2 import AsyncClient


async def get_balances(async_client: AsyncClient, wallet: Wallet) -> dict:
    """Fetches the balances of the wallet's subaccounts."""
    denoms = {
        "inj": ("INJ", 18),
        "erc20:0xa00C59fF5a080D2b954d0c75e46E22a0c371235a": ("USDC", 6),     # mainnet USDC
        "erc20:0x0C382e685bbeeFE5d3d9C29e29E341fEE8E84C5d": ("USDC", 6),     # testnet USDC
        "peggy0x87aB3B4C8661e07D6372361211B96ed4Dc36B1B5": ("USDT", 6),
        "factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/usdc": ("USDC COSMOS", 6),
    }

    resp = await async_client.fetch_bank_balances(wallet.inj_address)
    balances = {
        denoms.get(b["denom"], (b["denom"], 0))[0]:
        int(b["amount"]) / (10 ** denoms.get(b["denom"], (b["denom"], 0))[1])
        for b in resp["balances"]
    }

    return balances