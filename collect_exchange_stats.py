import json
import time
import ccxt.async_support as ccxt
from typing import Dict, Any
import asyncio
import sys


async def test_exchange_latency(
    exchange_id: str, api_config: Dict[str, str]
) -> Dict[str, Any]:
    exchange = None
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class(
            {
                "apiKey": api_config.get("api_key"),
                "secret": api_config.get("secret"),
                "enableRateLimit": True,
            }
        )

        results = {
            "min_public_latency": None,
            "avg_public_latency": None,
            "max_public_latency": None,
            "min_private_latency": None,
            "avg_private_latency": None,
            "max_private_latency": None,
            "error": None,
        }
        public_latencies = []
        try:
            for _ in range(10):
                start_time = time.time()
                await exchange.fetch_ticker("BTC/USDT")
                public_latencies.append(time.time() - start_time)
                await asyncio.sleep(1)

            if public_latencies:
                results.update(
                    {
                        "min_public_latency": min(public_latencies),
                        "avg_public_latency": sum(public_latencies)
                        / len(public_latencies),
                        "max_public_latency": max(public_latencies),
                    }
                )

        except Exception as e:
            print(
                f"Error in public endpoint test for {exchange_id}: {e}", file=sys.stderr
            )
            results["error"] = f"Public endpoint error: {str(e)}"
        private_latencies = []
        if api_config.get("api_key"):
            try:
                for _ in range(10):
                    start_time = time.time()
                    await exchange.fetch_balance()
                    private_latencies.append(time.time() - start_time)
                    await asyncio.sleep(1)

                if private_latencies:
                    results.update(
                        {
                            "min_private_latency": min(private_latencies),
                            "avg_private_latency": sum(private_latencies)
                            / len(private_latencies),
                            "max_private_latency": max(private_latencies),
                        }
                    )

            except Exception as e:
                print(
                    f"Error in private endpoint test for {exchange_id}: {e}",
                    file=sys.stderr,
                )
                if not results["error"]:
                    results["error"] = f"Private endpoint error: {str(e)}"

        return results

    except Exception as e:
        print(f"Error testing exchange {exchange_id}: {e}", file=sys.stderr)
        return {
            "min_public_latency": None,
            "avg_public_latency": None,
            "max_public_latency": None,
            "min_private_latency": None,
            "avg_private_latency": None,
            "max_private_latency": None,
            "error": str(e),
        }

    finally:
        if exchange:
            try:
                await exchange.close()
            except Exception as e:
                print(f"Error closing exchange {exchange_id}: {e}", file=sys.stderr)


async def main():
    try:
        with open("/tmp/exchange_config.json", "r") as f:
            config = json.load(f)

        results = {
            "region": config["region"],
            "timestamp": time.time(),
            "exchanges": {},
        }
        for exchange_id, api_config in config["exchanges"].items():
            try:
                results["exchanges"][exchange_id] = await test_exchange_latency(
                    exchange_id, api_config
                )
            except Exception as e:
                print(f"Error processing exchange {exchange_id}: {e}", file=sys.stderr)
                results["exchanges"][exchange_id] = {
                    "min_public_latency": None,
                    "avg_public_latency": None,
                    "max_public_latency": None,
                    "min_private_latency": None,
                    "avg_private_latency": None,
                    "max_private_latency": None,
                    "error": str(e),
                }
        with open("/tmp/exchange_stats.json", "w") as f:
            json.dump(results, f, indent=2)

    except Exception as e:
        print(f"Error in main: {e}", file=sys.stderr)
        with open("/tmp/exchange_stats.json", "w") as f:
            json.dump(
                {
                    "error": str(e),
                    "timestamp": time.time(),
                    "region": config.get("region", "unknown"),
                },
                f,
                indent=2,
            )


if __name__ == "__main__":
    asyncio.run(main())
