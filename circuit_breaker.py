import enum 
import time
from logger import setup_logger


logger = setup_logger(__name__)

#  -- Representing circuit breaker all the states.
class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitOpenError(Exception):
    """Raised when a request is blocked because the circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """
    -- CircuitBreaker pattern implementation.
            --> it is used to protect other microservices from a faulty downstream API.

    -- States:
        -> CLOSED: all microservices is working intently.

        -> OPEN: all the upstream API request is getting immediately failed because faulty microservies gets disconnected from them.

        -> HALF_OPEN: after cooldown period one test request will be send, to decide whether to reset cooldown or closed it.
    
    """
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0):
        """
        intialize the circuit breaker with failure threshold and cooldown period.

        args:
            failure_threshold: number of consecutive failures before opening the circuit.
            cooldown_seconds: time to wait before transitioning from OPEN to HALF_OPEN state.
        """
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None


    
    def _on_success(self):
        """
        if request succeed then it is closed state.
        reset failure count.
        """
        self.failure_count = 0

        if self.state == CircuitState.HALF_OPEN:
            logger.warning("transitioning from HALF_OPEN to CLOSED")
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        """
        if request failed and failure_count > failure_threshold then it is open state.
        record last_failure_time.
        """
        self.failure_count += 1

        if self.failure_count >= self.failure_threshold: 
            if self.state != CircuitState.OPEN:
                logger.error("circuit opened due to failure")
                self.last_failure_time = time.time()
                self.state = CircuitState.OPEN



    async def call(self, func, *args, **kwargs):
        """
        -- it is a wrapper function with circuit breaker feature.

        args:
            func-> it is a function that gets the power of  circuit breaker.
            *args -> position args
            **kwargs -> keywords args
        """

        if self.state == CircuitState.OPEN:

            if self.last_failure_time:
                # to avoid None addition
                if self.last_failure_time + self.cooldown_seconds > time.time():
                    raise CircuitOpenError("Circuit is open - request blocked")
                else:
                    logger.warning("circuit is reached into half open state")
                    self.state = CircuitState.HALF_OPEN
                
            
        try:
            response = await func(*args, **kwargs)
            self._on_success()
            return response
        
        except Exception:
            self._on_failure()
            raise




