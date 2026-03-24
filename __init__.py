try:
    from .main import MiniMaxAlertPlugin
    __all__ = ["MiniMaxAlertPlugin"]
except ImportError as e:
    from astrbot.api import logger
    __all__ = []
    logger.warning(f"无法加载 MiniMaxAlertPlugin: {e}")
