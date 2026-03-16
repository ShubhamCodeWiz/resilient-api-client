# backoff.py
import random

def calculate_backoff(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """
    calculate backoff time for each request.

    base: starting wait time in seconds for attempt 0.
    cap: maximum wait time in seconds regardless of attempt number.

    return value is randomized between 0 and calculated cap.

    """
    return random.uniform(0, min(cap, base * (2**attempt)))
    