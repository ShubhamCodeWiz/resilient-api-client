# caller.py
import httpx
from logger import setup_logger, get_correlation_id
from backoff import calculate_backoff
import asyncio
import time
from circuit_breaker import CircuitBreaker
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from config import APIClientConfig

# FIX 1: Logger is set up at module level — this is correct.
# But correlation ID must NOT be here — it must be generated fresh per request.
logger = setup_logger(__name__)


class RetryableAPIClient:
    def __init__(self, config: APIClientConfig ):
        self.config = config
        self.circuit_breaker = CircuitBreaker(failure_threshold=config.failure_threshold,
                            cooldown_seconds=config.cooldown_seconds)
        
        self.timeout = httpx.Timeout(
        connect=config.connect_timeout,
        read=config.read_timeout,
        write=config.write_timeout,
        pool=config.pool_timeout
        )

    async def fetch(self, method: str, url: str, **kwargs) -> httpx.Response:
        return await call_api_with_retry(
            method=method,
            url=url,
            timeout = self.timeout,
            circuit_breaker=self.circuit_breaker,
            max_retries=self.config.max_retries,
            base_delay=self.config.base_delay,
            max_delay=self.config.max_delay,
            **kwargs
        )
    
        

async def call_api(
    method: str,
    url: str,
    correlation_id: str,  # FIX 4: Accept correlation_id as parameter so caller and retry function share the same ID
    timeout: httpx.Timeout,
    **kwargs
)-> httpx.Response:
    """
    Sends a GET request to the given URL.

    Args:
        url: the endpoint to call
        correlation_id: shared request ID for tracing across log lines
        timeout: httpx.Timeout object controlling connect/read/write/pool timeouts

    Returns:
        httpx.Response on success

    Raises:
        httpx.HTTPStatusError: if server returns 4xx or 5xx
        httpx.TimeoutException: if request exceeds timeout
        httpx.RequestError: if network or connection error occurs
    """
    start = time.perf_counter()

    try:
        logger.info(
            "Sending GET request",
            extra={"correlation_id": correlation_id, "url": url}
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Response received successfully",
                extra={
                    "correlation_id": correlation_id,
                    "status_code": response.status_code,
                    "response_time_ms": round(elapsed_ms, 2)
                }
            )
            return response

    except httpx.HTTPStatusError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000

        # FIX 3: Use WARNING not ERROR — this is a single failure, may be retried.
        # ERROR is reserved for when we fully give up (in call_api_with_retry).
        logger.warning(
            "HTTP error response received",
            extra={
                "correlation_id": correlation_id,
                "status_code": e.response.status_code,
                "response_time_ms": round(elapsed_ms, 2)
            }
        )
        raise

    except httpx.TimeoutException as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.warning(
            "Request timed out",
            extra={
                "correlation_id": correlation_id,
                "response_time_ms": round(elapsed_ms, 2)
            }
        )
        raise

    except httpx.RequestError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "Network or request error — cannot reach server",
            extra={
                "correlation_id": correlation_id,
                "url": url,
                "response_time_ms": round(elapsed_ms, 2)
            }
        )
        raise


def should_retry(status_code: int) -> bool:
    """
    Returns True if the status code warrants a retry.
    Retries on 429 (rate limited) and all 5xx (server errors).
    Never retries on 4xx (client mistakes).
    """
    return status_code == 429 or status_code >= 500


async def call_api_with_retry(
    method: str,
    url: str,
    timeout: httpx.Timeout,
    circuit_breaker: CircuitBreaker | None = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    **kwargs
)-> httpx.Response:
    """
    Calls an API with exponential backoff retry logic.

    Args:
        url: the endpoint to call
        max_retries: maximum number of attempts before giving up
        base_delay: starting wait time in seconds for attempt 0
        max_delay: maximum wait time in seconds regardless of attempt number

    Retries on: 429, 5xx, TimeoutException
    Stops immediately on: 4xx, RequestError

    Raises:
        httpx.HTTPStatusError
        httpx.TimeoutException
        httpx.RequestError
    """
    # FIX 1: Generate correlation_id HERE — once per retry cycle, not at module level.
    # This means every call to call_api_with_retry() gets its own unique trace ID.
    # All log lines from this one request (including retries) share the same ID.
    correlation_id = get_correlation_id()

    for attempt in range(max_retries):
        logger.info(
            "Attempt started",
            extra={
                "correlation_id": correlation_id,
                "attempt": attempt + 1,
                "max_retries": max_retries
            }
        )

        try:
            # FIX 4: Pass correlation_id into call_api so both functions log the same ID
            if circuit_breaker:
                response = await circuit_breaker.call(call_api, method, url, correlation_id, timeout, **kwargs)
            else:
                response = await call_api(method, url, correlation_id, timeout, **kwargs)
                
            return response

        except httpx.HTTPStatusError as e:
            status = e.response.status_code

            if not should_retry(status):
                logger.warning(
                    "Non-retryable HTTP status — aborting",
                    extra={
                        "correlation_id": correlation_id,
                        "status_code": status,
                    },
                )
                raise

            if attempt == max_retries - 1:
                logger.error(
                    "Max retries exhausted after HTTP error",
                    extra={
                        "correlation_id": correlation_id,
                        "status_code": status,
                        "attempts": max_retries,
                    },
                )
                raise

            # default values
            wait = None
            message = "Retrying after HTTP error"

            # handle rate limit
            if status == 429:
                wait = get_retry_after(e.response)

                if wait is not None:
                    message = "Rate limited by server — respecting Retry-After header"

            # fallback to exponential backoff
            if wait is None:
                wait = calculate_backoff(attempt, base_delay, max_delay)

            # single structured log
            logger.warning(
                message,
                extra={
                    "correlation_id": correlation_id,
                    "status_code": status,
                    "wait_seconds": round(wait, 2),
                    "next_attempt": attempt + 2,
                },
            )

            # single sleep
            await asyncio.sleep(wait)
        except httpx.TimeoutException:
            if attempt == max_retries - 1:
                # Last attempt failed — ERROR because we fully gave up
                logger.error(
                    "Max retries exhausted after timeout",
                    extra={
                        "correlation_id": correlation_id,
                        "attempts": max_retries
                    }
                )
                raise

            wait = calculate_backoff(attempt, base_delay, max_delay)

            # FIX 2: One structured log line per retry — removed duplicate f-string log
            logger.warning(
                "Retrying after timeout",
                extra={
                    "correlation_id": correlation_id,
                    "wait_seconds": round(wait, 2),
                    "next_attempt": attempt + 2
                }
            )
            await asyncio.sleep(wait)

        except httpx.RequestError:
            # Network failure — not retryable, already logged in call_api()
            raise

    raise RuntimeError("Retry loop exited unexpectedly — should never reach here")

    
def get_retry_after(response: httpx.Response) -> float | None:
    """
    --Extract the retry-after header from http response 
        and return the number of seconds a client has to wait for retrying.

    Args:
        response (httpx.Response): The HTTP response object.

    Returns:
        float | None: Number of seconds to wait before retrying, or None
        if the Retry-After header is not present or invalid.
    """

    retry_after = response.headers.get("Retry-After")

    if retry_after is None:
        return None

    # Try parsing as integer seconds
    try:
        return float(int(retry_after))
    except ValueError:
        pass

    # Try parsing as HTTP date
    try:
        retry_datetime = parsedate_to_datetime(retry_after)

        now = datetime.now(timezone.utc)

        wait_time = (retry_datetime - now).total_seconds()

        return max(wait_time, 0)

    except Exception:
        logger.warning("Failed to parse Retry-After header", extra={"value": retry_after})
        return None
    
