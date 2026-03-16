# logger.py
import logging
import json
from datetime import datetime
import uuid

class JSONFormatter(logging.Formatter):
    """
    it converts records into json logs
    """

    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger_name": record.name,
            "correlation_id": getattr(record, "correlation_id", "none"),
            "response_time_ms": getattr(record, "response_time_ms", "none")
        }

        return json.dumps(log_record)


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    it will setup the logger for each file

    args: 
        - name: taking filename as a parameter 
        - level: taking level name 
    """


    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:

        handler = logging.FileHandler("app.log")
        handler.setFormatter(JSONFormatter())

        logger.addHandler(handler)

    return logger

def get_correlation_id() -> str:
    """
    returns the correlation_id for each request
    """
    return str(uuid.uuid4())



