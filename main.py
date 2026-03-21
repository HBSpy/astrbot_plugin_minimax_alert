from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger
import aiohttp
from datetime import datetime, timezone



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


@register("astrbot_plugin_minimax_alert", "MiniMax_Alert", "查询 MiniMax Token Plan API 用量信息", "v1.0.0")
class MiniMaxAlertPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._session: aiohttp.ClientSession | None = None

    async def initialize(self):
        logger.info("MiniMax Alert 插件初始化中...")

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            logger.info("创建懒初始化 ClientSession")
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    def get_api_url(self, region: str, group_id: str) -> tuple[str, dict]:
        params = {}
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

    def format_timestamp(self, ts: int) -> str:
        if ts <= 0:
            return "未知"
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    async def fetch_quota(self, api_key: str, region: str, group_id: str) -> dict:
        await self._ensure_session()

        url, params = self.get_api_url(region, group_id)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        logger.info(f"发起 API 请求: url={url}, params={params}")

        try:
            async with self._session.get(url, headers=headers, params=params) as response:
                logger.info(f"收到响应状态码: {response.status}")

                if response.status == 200:
                    data = await response.json()
                    logger.info(f"API 请求成功，返回数据长度: {len(str(data))}")
                    return data
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
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=error_msg_full,
                        headers=response.headers,
                    )
        except aiohttp.ClientResponseError as e:
            logger.error(f"ClientResponseError: {e.message} (状态码: {e.status})")
            raise QueryError(f"{e.message}（状态码：{e.status}）") from e
        except aiohttp.ClientConnectorError as e:
            logger.error(f"网络连接失败: {str(e)}")
            raise QueryError("网络连接失败，请检查网络或 MiniMax 服务状态") from e
        except TimeoutError as e:
            logger.error(f"请求超时: {str(e)}")
            raise QueryError("请求超时，请检查网络连接后重试") from e

    REQUIRED_FIELDS = [
        "current_interval_total_count",
        "current_interval_usage_count",
        "start_time",
        "end_time",
        "current_weekly_total_count",
        "current_weekly_usage_count",
        "weekly_start_time",
        "weekly_end_time",
    ]

    def parse_data(self, data: dict) -> str:
        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code")

        if status_code is not None and status_code != 0:
            error_msg = base_resp.get("status_msg", "未知错误")
            error_map = {
                "invalid_token": "API Key 无效，请检查配置",
                "token_expired": "API Key 已过期，请重新获取",
                "quota_exceeded": "额度已用尽，请等待重置",
                "rate_limited": "请求过于频繁，请稍后重试",
                "group_not_found": "Group ID 不存在，请检查配置",
                "permission_denied": "无权限访问，请确认账户状态",
            }
            for key, msg in error_map.items():
                if key in error_msg.lower():
                    logger.error(f"API 返回业务错误: {msg} ({error_msg})")
                    raise QueryError(f"API 返回错误：{msg}（{error_msg}）")
            logger.error(f"API 返回未知错误: {error_msg} (状态码: {status_code})")
            raise QueryError(f"API 返回错误：{error_msg}（状态码：{status_code}）")

        model_list = data.get("model_remains", [])
        if not model_list:
            logger.warning("model_remains 列表为空")
            raise QueryError("未获取到任何额度数据，接口返回格式可能已变更")

        logger.info(f"解析额度数据（{len(model_list)} 个模型，共用用量）")

        model = model_list[0]
        missing_fields = [f for f in self.REQUIRED_FIELDS if model.get(f) is None]
        if missing_fields:
            logger.warning(f"缺少必填字段: {missing_fields}")
            raise QueryError(f"数据格式异常，缺少必填字段: {', '.join(missing_fields)}")

        intv_total = model.get("current_interval_total_count", 0)
        intv_used = model.get("current_interval_usage_count", 0)
        intv_remain = intv_total - intv_used
        intv_percent = (intv_remain / intv_total) * 100 if intv_total > 0 else 0

        week_total = model.get("current_weekly_total_count", 0)
        week_used = model.get("current_weekly_usage_count", 0)
        week_remain = week_total - week_used
        week_percent = (week_remain / week_total) * 100 if week_total > 0 else 0

        end_time_ms = model.get('end_time', 0)
        if end_time_ms > 0:
            end_time = datetime.fromtimestamp(end_time_ms / 1000, tz=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            delta = end_time - now
            remains_time_minutes = max(0, int(delta.total_seconds() / 60))
        else:
            remains_time_minutes = 0

        result = "套餐：MiniMax Token Plan\n"
        result += f"5小时剩余/总额：{intv_remain}/{intv_total} ({intv_percent:.1f}%)\n"
        result += f"本周剩余/总额：{week_remain}/{week_total} ({week_percent:.1f}%)\n"
        result += f"\n📅 5小时滚动周期：{self.format_timestamp(model.get('start_time', 0))} ~ {self.format_timestamp(model.get('end_time', 0))}\n"
        result += f"📅 本周周期：{self.format_timestamp(model.get('weekly_start_time', 0))} ~ {self.format_timestamp(model.get('weekly_end_time', 0))}\n"
        result += f"⏰ 距离5小时重置：{remains_time_minutes} 分钟\n"
        result += f"\n✅ 查询完成！"

        return result

    @filter.command("用量")
    async def query_quota(self, event: AstrMessageEvent):
        api_key = self.config.get("api_key", "")
        region = self.config.get("region", "国内")
        group_id = self.config.get("group_id", "")

        if not api_key:
            logger.warning("用户未配置 API Key")
            yield event.plain_result("⚠️ 请先在插件设置中配置 MiniMax API Key")
            return

        try:
            logger.info(f"开始查询用量: region={region}, group_id={group_id}")
            quota_data = await self.fetch_quota(api_key, region, group_id)
            result = self.parse_data(quota_data)
            yield event.plain_result(result)
        except ValueError as e:
            logger.error(f"配置错误: {str(e)}")
            yield event.plain_result(f"⚠️ 配置错误：{str(e)}")
        except QueryError as e:
            logger.error(f"业务查询错误: {str(e)}")
            yield event.plain_result(f"❌ {str(e)}")
        except aiohttp.ClientError as e:
            logger.error(f"网络错误: {str(e)}")
            yield event.plain_result(f"❌ 网络错误：{str(e)}")

    async def terminate(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("ClientSession 已关闭")


class QueryError(Exception):
    """查询业务异常"""
    pass
