import logging
from pathlib import Path

class MaxLevelFilter(logging.Filter):
    def __init__(self, level):
        self.level = level
    def filter(self, record):
        return record.levelno < self.level

def setup_logging():
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Info handler
    try:
        info_handler = logging.FileHandler(logs_dir / "arb_op.log")
    except Exception as e:
        print(f"Failed to create log file handler: {e}")
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    info_handler.addFilter(MaxLevelFilter(logging.ERROR))

    # Error handler
    try:
        error_handler = logging.FileHandler(logs_dir / "arb_error.log")
    except Exception as e:
        print(f"Failed to create log file handler: {e}")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))

    # Avoid duplicate handlers
    if not root_logger.hasHandlers():
        root_logger.addHandler(info_handler)
        root_logger.addHandler(error_handler)