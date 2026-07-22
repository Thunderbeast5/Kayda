"""logger_setup.py — Configure loguru for file + console output."""
import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_dir: str = "logs", level: str = "INFO"):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stdout, level=level,
               format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
    logger.add(f"{log_dir}/run.log", level="DEBUG", rotation="50 MB",
               format="{time} | {level} | {message}")
    return logger
