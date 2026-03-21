import logging
import sys


# Configure structured logging
def setup_logging(log_level: str = "INFO") -> None:
    """
    Configures structured logging for the application.
    """
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Silence overly verbose loggers if needed
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
