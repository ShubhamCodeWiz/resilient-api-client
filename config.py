from dataclasses import dataclass

@dataclass
class APIClientConfig:
    """
    Central configuration for RetryableAPIClient — all tunable settings in one place.
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    connect_timeout: int = 5
    read_timeout: int = 10
    write_timeout: int = 10
    pool_timeout: int = 5
    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    

