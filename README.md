# RetryableAPIClient

A production-grade resilient HTTP client for Python implementing 
exponential backoff with jitter, circuit breaking, intelligent 
rate limit handling, and structured observability.

Built from scratch to understand — not just use — the resilience 
patterns that power systems at Stripe, Netflix, and AWS.


## The Problem This Solves

Every service that calls external APIs faces the same failure modes:

- A downstream service responds slowly — your threads pile up and 
  your service dies, not because your code is broken but because 
  you were too polite to hang up
- A transient network error fails a request that would have 
  succeeded on the second attempt
- A struggling server gets hammered by simultaneous retries from 
  every client — the thundering herd makes recovery impossible
- A dependency goes down completely — without protection, 
  every request to your service hangs waiting for a response 
  that will never come

This client solves all four problems with layered defenses: 
timeout → retry → backoff with jitter → circuit breaking → 
structured observability.



## Architecture

retryable_caller/
├── config.py           # Externalized configuration — zero magic numbers
├── logger.py           # Structured JSON logging with correlation IDs
├── backoff.py          # Exponential backoff with full jitter
├── circuit_breaker.py  # Three-state circuit breaker (CLOSED/OPEN/HALF-OPEN)
├── caller.py           # RetryableAPIClient — Facade over all resilience concerns
└── main.py             # Usage example

Request flow:

client.fetch(url)
      │
      ▼
CircuitBreaker          ← Fail fast if dependency is known to be down
      │
      ▼
call_api_with_retry()   ← Retry with exponential backoff + full jitter
      │                    Respect Retry-After on 429s
      │                    Check idempotency before retrying POST
      ▼
call_api()              ← HTTP call with connection + read timeouts
                           Structured JSON log on every attempt



## Components

**config.py** — Single Config dataclass holding all tunable parameters. 
No magic numbers anywhere in the codebase. Every value has a name 
and a reason.

**logger.py** — JSONFormatter producing structured logs consumable 
directly by Datadog, ELK Stack, and Splunk. Every log line carries 
a correlation ID, timestamp, response time in milliseconds, and 
status code.

**backoff.py** — Exponential backoff with full jitter. Implements the 
strategy validated by AWS research as optimal under load — randomizing 
wait time prevents thundering herd on recovery.

**circuit_breaker.py** — Three-state machine. CLOSED under normal 
operation. OPEN after failure threshold — fails fast without calling 
the dependency. HALF-OPEN after cooldown — tests recovery with a 
single probe request.

**caller.py** — RetryableAPIClient exposes a single fetch() method. 
Facade pattern hiding all resilience complexity from the caller. 
Handles 429 rate limiting by parsing and respecting Retry-After headers.



## Installation

git clone https://github.com/yourusername/retryable-api-caller
cd retryable-api-caller
pip install httpx

## Usage

from retryable_caller.caller import RetryableAPIClient
from retryable_caller.config import Config

config = Config(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    connect_timeout=3.0,
    read_timeout=10.0,
    failure_threshold=5,
    recovery_timeout=30.0
)

client = RetryableAPIClient(config)
response = client.fetch("https://api.example.com/data")



## Example Output

A single request that hits a 503, retries with backoff, 
and succeeds on the second attempt:

{"timestamp": "2024-01-15T14:23:01.123Z", "level": "INFO",
 "correlation_id": "7f3a9b2c", "event": "api_call_attempt",
 "attempt": 1, "url": "https://api.example.com/data",
 "status_code": 503, "response_time_ms": 142}

{"timestamp": "2024-01-15T14:23:03.891Z", "level": "WARNING",
 "correlation_id": "7f3a9b2c", "event": "retry_attempt",
 "attempt": 2, "backoff_ms": 2743,
 "reason": "status_503_retryable"}

{"timestamp": "2024-01-15T14:23:06.634Z", "level": "INFO",
 "correlation_id": "7f3a9b2c", "event": "api_call_success",
 "attempt": 2, "url": "https://api.example.com/data",
 "status_code": 200, "response_time_ms": 98}

A request that exhausts retries and opens the circuit breaker:

{"timestamp": "2024-01-15T14:25:11.001Z", "level": "ERROR",
 "correlation_id": "a9f3c821", "event": "circuit_breaker_opened",
 "consecutive_failures": 5, "threshold": 5,
 "next_probe_after_seconds": 30}



 ## Design Decisions

This section explains the why behind each technical choice. 
These are the decisions I'd defend in a production code review.

**Why exponential backoff instead of fixed delay?**
Fixed delay means all retries hit the server at predictable 
intervals — if the server is struggling, predictable load makes 
recovery harder. Exponential backoff creates increasing breathing 
room, giving the server more time to recover with each attempt.

**Why full jitter specifically?**
Without jitter, clients that started failing at the same moment 
retry at the same moment — the thundering herd problem. AWS 
published research showing full jitter (random between 0 and cap) 
outperforms decorrelated jitter and equal jitter under load. 
The extra randomness is not noise — it's coordinated kindness 
to a recovering server.

**Why separate connect_timeout and read_timeout?**
Connection timeout and read timeout protect against different 
failure modes. A fast connection timeout catches network-level 
failures quickly. A longer read timeout allows legitimate slow 
responses without hanging indefinitely. Conflating them into 
one value forces a tradeoff — either you're too aggressive 
on slow legitimate calls or too patient on hung connections.

**Why check idempotency before retrying?**
Retrying a POST that creates a resource produces duplicates. 
Retrying a payment charge double-bills users. The idempotency 
check is not optional safety theater — it's the line between 
a retry mechanism and a billing bug.

**Why the Facade pattern for the public interface?**
Business logic should not know that retries, circuit breaking, 
and backoff exist. It should call fetch() and receive either 
a response or a clean exception. Leaking resilience implementation 
details into the caller creates coupling — changing retry logic 
requires touching business logic. The Facade isolates that 
completely.

**Why structured JSON logs instead of plain text?**
Plain text logs cannot be queried at scale. JSON logs are 
directly ingestible by Datadog, ELK Stack, and Splunk without 
transformation. Every field — correlation_id, response_time_ms, 
status_code — is a queryable dimension. During a production 
incident, the difference between structured and unstructured 
logs is the difference between a 2-minute diagnosis and a 
2-hour search.

**Why correlation IDs on every request?**
In a system making calls to multiple downstream services, 
a request that touches three services produces log lines 
in three different log streams. Without a shared identifier, 
reconstructing the sequence is impossible at scale. The 
correlation ID is the thread that connects all log lines 
belonging to one request — it's the primitive that 
distributed tracing tools like Jaeger are built on.


## What I Would Add Next

**Prometheus metrics** — Add counters for total requests, total 
retries, circuit breaker state changes, and a histogram for 
response time percentiles. Feeds directly into Grafana dashboards 
and enables SLO alerting.

**Fallback responses** — Return cached or default data when the 
circuit is OPEN instead of raising an exception. Converts hard 
failures into graceful degradation — the system does less 
before it does nothing.

**Full test suite** — Unit tests for every component using pytest 
and respx for HTTP mocking. Property-based tests for backoff 
distribution to verify jitter behavior statistically.

**OpenTelemetry integration** — Replace the custom correlation ID 
with OpenTelemetry trace context. Enables automatic trace 
propagation across service boundaries and compatibility with 
Jaeger, Zipkin, and Datadog APM.
