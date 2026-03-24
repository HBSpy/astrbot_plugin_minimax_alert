import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from astrbot.api import logger


class QueryError(Exception):
    """查询业务异常"""
    pass


ERROR_MESSAGES = {
    400: ("请求参数错误", "请检查 API Key 和配置是否正确"),
    401: ("认证失败", "API Key 无效或已过期，请检查配置"),
    403: ("无访问权限", "该 API Key 没有访问权限，请确认账户状态"),
    404: ("接口不存在", "API 地址有误，请检查版本配置"),
    429: ("请求过于频繁", "已达 API 调用限制，请稍后再试"),
    500: ("服务器内部错误", "MiniMax 服务器异常，请稍后重试"),
    502: ("网关错误", "MiniMax 服务暂时不可用，请稍后重试"),
    503: ("服务不可用", "MiniMax 服务维护中，请稍后重试"),
}


class MiniMaxAPI:
    """MiniMax API 客户端"""
    
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
    
    async def initialize(self):
        """初始化 API 客户端"""
        logger.info("MiniMax Alert 插件初始化中...")
        await self._ensure_session()
    
    async def _ensure_session(self):
        """确保 session 存在"""
        if self._session is None or self._session.closed:
            logger.info("创建懒初始化 ClientSession")
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
    
    def _get_api_url(self, region: str, group_id: str) -> tuple[str, Dict[str, str]]:
        """
        获取 API URL 和参数
        
        Args:
            region: 区域（国内/国际）
            group_id: Group ID（国际版必需）
            
        Returns:
            (url, params) 元组
            
        Raises:
            ValueError: 配置错误
        """
        params: Dict[str, str] = {}
        if region == "国内":
            url = "https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains"
        elif region == "国际":
            if not group_id:
                raise ValueError("国际版需要填写 GroupId")
            url = "https://platform.minimax.io/v1/api/openplatform/coding_plan/remains"
            params["GroupId"] = group_id
        else:
            raise ValueError("REGION 请选择 '国内' 或 '国际'")
        return url, params
    
    async def fetch_quota(self, api_key: str, region: str, group_id: str) -> Dict[str, Any]:
        """
        获取配额信息
        
        Args:
            api_key: API 密钥
            region: 区域
            group_id: Group ID
            
        Returns:
            API 返回的数据字典
            
        Raises:
            QueryError: 查询失败
        """
        await self._ensure_session()
        
        url, params = self._get_api_url(region, group_id)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"发起 API 请求: url={url}, params={params}")
        
        try:
            async with self._session.get(url, headers=headers, params=params) as response:
                logger.info(f"收到响应状态码: {response.status}")
                
                if response.status == 200:
                    try:
                        data = await response.json()
                        data_keys = len(data) if isinstance(data, (dict, list)) else 0
                        logger.info(f"API 请求成功，返回数据包含 {data_keys} 个字段")
                        return data
                    except (aiohttp.ContentTypeError, ValueError) as e:
                        logger.error(f"JSON 解析失败: {str(e)}")
                        raise QueryError("API 返回数据格式异常，请稍后重试") from e
                else:
                    title, suggestion = ERROR_MESSAGES.get(
                        response.status, ("未知错误", "请稍后重试")
                    )
                    logger.error(f"API 请求失败: 状态码={response.status}, title={title}, suggestion={suggestion}")
                    
                    try:
                        error_data = await response.json()
                        detail = error_data.get("base_resp", {}).get("status_msg", "")
                    except Exception:
                        detail = await response.text()
                    
                    error_msg = f"{title}：{detail}" if detail else title
                    error_msg_full = f"{error_msg}\n💡 建议：{suggestion}"
                    logger.error(f"API 错误详情: {error_msg_full}")
                    raise QueryError(error_msg_full)
        except QueryError:
            raise
        except aiohttp.ClientConnectorError as e:
            logger.error(f"网络连接失败: {str(e)}")
            raise QueryError("网络连接失败，请检查网络或 MiniMax 服务状态") from e
        except TimeoutError as e:
            logger.error(f"请求超时: {str(e)}")
            raise QueryError("请求超时，请检查网络连接后重试") from e
        except Exception as e:
            logger.error(f"未知错误: {str(e)}")
            raise QueryError(f"请求失败：{str(e)}") from e
    
    async def terminate(self):
        """关闭会话"""
        if self._session and not self._session.closed:
            logger.info("正在关闭 ClientSession...")
            await self._session.close()
            self._session = None
            logger.info("ClientSession 已关闭")
        else:
            logger.info("ClientSession 无需关闭（已为空或已关闭）")
