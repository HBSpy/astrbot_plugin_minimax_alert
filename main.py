from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger

from .api import MiniMaxAPI, QueryError
from .config import ConfigManager
from .parser import DataParser
from .whitelist import WhitelistManager


@register("astrbot_plugin_minimax_alert", "MiniMax_Alert", "查询 MiniMax Token Plan API 用量信息", "v1.0.0")
class MiniMaxAlertPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self._config_manager = ConfigManager(config)
        self._api = MiniMaxAPI()
        self._parser = DataParser()
    
    async def initialize(self):
        await self._api.initialize()
    
    def _check_whitelist(self, event: AstrMessageEvent) -> bool:
        """
        检查用户是否在白名单中

        Args:
            event: 消息事件

        Returns:
            True 如果用户允许访问
        """
        user_sid = str(event.session_id)
        whitelist_manager = self._config_manager.get_whitelist()
        return whitelist_manager.check_whitelist(user_sid)
    
    @filter.command("用量")
    async def query_quota(self, event: AstrMessageEvent):
        """查询配额命令"""
        if not self._check_whitelist(event):
            yield event.plain_result("⚠️ 该功能仅对白名单用户开放")
            return
        
        api_key = self._config_manager.get_api_key()
        region = self._config_manager.get_region()
        group_id = self._config_manager.get_group_id()
        
        if not api_key:
            logger.warning("用户未配置 API Key")
            yield event.plain_result("⚠️ 请先在插件设置中配置 MiniMax API Key")
            return
        
        try:
            logger.info(f"开始查询用量: region={region}, group_id={group_id}")
            quota_data = await self._api.fetch_quota(api_key, region, group_id)
            result = self._parser.parse_quota_data(quota_data)
            yield event.plain_result(result)
        except ValueError as e:
            logger.error(f"配置错误: {str(e)}")
            yield event.plain_result(f"⚠️ 配置错误：{str(e)}")
        except QueryError as e:
            logger.error(f"业务查询错误: {str(e)}")
            yield event.plain_result(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"网络错误: {str(e)}")
            yield event.plain_result(f"❌ 网络错误：{str(e)}")
    
    async def terminate(self):
        await self._api.terminate()
