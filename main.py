# main.py
"""
End-to-end demo of the RetryableAPIClient.
Demonstrates: successful call, circuit breaker triggering, and OPEN state blocking.
Run with: python main.py
"""
import asyncio
from caller import RetryableAPIClient
from config import APIClientConfig
from circuit_breaker import CircuitOpenError

GOOD_URL = "https://jsonplaceholder.typicode.com/posts/1"
BAD_URL  = "https://jsonplaceholder.typicode.com/posts/999999"  # returns 404


async def main():
    # Low thresholds so the demo runs fast
    config = APIClientConfig(failure_threshold=2, cooldown_seconds=10.0)
    client = RetryableAPIClient(config=config)

    # ── Stage 1: Successful call ──────────────────────────────────────────────
    print("\n── Stage 1: Successful call ──")
    try:
        response = await client.fetch("GET", GOOD_URL)
        print(f"  ✓ Success — status {response.status_code}")
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")

    # ── Stage 2: Trigger failures to open the circuit ─────────────────────────
    print("\n── Stage 2: Triggering failures to open circuit ──")
    for attempt in range(1, 4):
        try:
            response = await client.fetch("GET", BAD_URL)
            print(f"  Attempt {attempt} — status {response.status_code}")
        except CircuitOpenError as e:
            print(f"  Attempt {attempt} — Circuit OPEN, request blocked: {e}")
        except Exception as e:
            print(f"  Attempt {attempt} — Failed: {type(e).__name__}: {e}")

    # ── Stage 3: Confirm circuit is OPEN — even good URL is blocked ───────────
    print("\n── Stage 3: Good URL blocked by open circuit ──")
    try:
        await client.fetch("GET", GOOD_URL)
    except CircuitOpenError as e:
        print(f"  ✓ Circuit correctly blocked the request: {e}")
    except Exception as e:
        print(f"  Other error: {e}")

    # ── Stage 4: Wait for cooldown and watch circuit recover ──────────────────
    print("\n── Stage 4: Waiting 11s for cooldown, then testing recovery ──")
    await asyncio.sleep(11)
    try:
        response = await client.fetch("GET", GOOD_URL)
        print(f"  ✓ Circuit recovered — status {response.status_code}")
    except Exception as e:
        print(f"  ✗ Still failing: {e}")


if __name__ == "__main__":
    asyncio.run(main())