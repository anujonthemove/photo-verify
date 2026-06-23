import os
import logging

from app.constants import LOGS_DIR
from app.state import _state

_loggers: dict = {}  # log_path → logging.Logger

def _get_logger() -> logging.Logger:
    ts   = _state.get('session_ts', '') or _state.get('active_cache', '')
    base = (os.path.splitext(os.path.basename(ts))[0] + '.log') if ts else 'photoverify.log'
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, base)
    if log_path not in _loggers:
        logger = logging.getLogger(f'photoverify.{log_path}')
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(log_path, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)-5s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        logger.addHandler(handler)
        _loggers[log_path] = logger
    return _loggers[log_path]

def _log(msg: str, level: int = logging.ERROR):
    try:
        _get_logger().log(level, msg)
    except Exception as e:
        print(f"  Log write failed: {e}")
