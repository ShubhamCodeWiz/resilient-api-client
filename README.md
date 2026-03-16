Python • Resilience Patterns • Circuit Breaker • Exponential Backoff • Observability

![Python](https://img.shields.io/badge/python-3.10+-blue)
![HTTP Client](https://img.shields.io/badge/type-resilient--http--client-green)
![Status](https://img.shields.io/badge/status-learning--project-orange)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

A production-grade resilient HTTP client for Python implementing 
exponential backoff with jitter, circuit breaking, intelligent 
rate limit handling, and structured observability.



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
**timeout → retry → backoff with jitter → circuit breaking → structured observability.**



## Architecture


retryable_caller/
├── config.py
├── logger.py
├── backoff.py
├── circuit_breaker.py
├── caller.py
└── main.py


### Request Flow

```mermaid
flowchart TD

A[client.fetch(url)]
B[Circuit Breaker]
C[call_api_with_retry]
D[Exponential Backoff + Jitter]
E[call_api HTTP request]
F{Response Status}
G[Return Success]
H[Retry]
I[Circuit Opens]

A --> B
B --> C
C --> D
D --> E
E --> F
F -->|200 OK| G
F -->|Retryable Error 5xx / Network| H
H --> C
F -->|Too Many Failures| I

This shows the layered resilience:

Circuit breaker protects failing dependencies

Retry logic handles transient failures

Exponential backoff prevents thundering herd

Structured logging records every attempt

Components

config.py — Single Config dataclass holding all tunable parameters.
No magic numbers anywhere in the codebase. Every value has a name
and a reason.

logger.py — JSONFormatter producing structured logs consumable
directly by Datadog, ELK Stack, and Splunk. Every log line carries
a correlation ID, timestamp, response time in milliseconds, and
status code.

backoff.py — Exponential backoff with full jitter. Implements the
strategy validated by AWS research as optimal under load — randomizing
wait time prevents thundering herd on recovery.

circuit_breaker.py — Three-state machine. CLOSED under normal
operation. OPEN after failure threshold — fails fast without calling
the dependency. HALF-OPEN after cooldown — tests recovery with a
single probe request.

caller.py — RetryableAPIClient exposes a single fetch() method.
Facade pattern hiding all resilience complexity from the caller.
Handles 429 rate limiting by parsing and respecting Retry-After headers.

Installation
git clone https://github.com/ShubhamCodeWiz/resilient-api-client
cd resilient-api-client
pip install httpx
Usage
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
Example Output

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
Design Decisions

This section explains the why behind each technical choice.

These are the decisions I'd defend in a production code review.

Why exponential backoff instead of fixed delay?

Fixed delay means all retries hit the server at predictable
intervals — if the server is struggling, predictable load makes
recovery harder. Exponential backoff creates increasing breathing
room, giving the server more time to recover with each attempt.

Why full jitter specifically?

Without jitter, clients that started failing at the same moment
retry at the same moment — the thundering herd problem.

AWS research showed full jitter performs best under load.

Why separate connect_timeout and read_timeout?

Connection timeout and read timeout protect against different
failure modes.

Connection timeout → network failure detection
Read timeout → slow server protection

Why check idempotency before retrying?

Retrying a POST that creates a resource produces duplicates.
Retrying a payment charge double-bills users.

Idempotency checks prevent catastrophic business bugs.

Why the Facade pattern?

Business logic should not know retries exist.

It should simply call:

fetch()

and receive either:

a response

or a clean exception

Why structured JSON logs?

Plain text logs cannot be queried at scale.

JSON logs are directly ingestible by:

Datadog

ELK Stack

Splunk

Why correlation IDs?

Without correlation IDs, logs across services cannot be linked.

Correlation IDs are the primitive that distributed tracing
systems like Jaeger are built on.

What I Would Add Next

Prometheus metrics

Counters for:

total requests

retries

circuit breaker opens

response time histograms

Fallback responses

Return cached or default data when the circuit is OPEN.

Full test suite

Using:

pytest

respx for HTTP mocking

OpenTelemetry integration

Replace correlation IDs with OpenTelemetry trace context to enable distributed tracing.
