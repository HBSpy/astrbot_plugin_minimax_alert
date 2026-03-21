from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig
import aiohttp
from datetime import datetime



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
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    def get_api_url(self, region: str, group_id: str) -> str:
        if region == "国内":
            return "https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains"
        elif region == "国际":
            if not group_id:
                raise ValueError("国际版需要填写 GroupId")
            return f"https://platform.minimax.io/v1/api/openplatform/coding_plan/remains?GroupId={group_id}"
        else:
            raise ValueError("REGION 请选择 '国内' 或 '国际'")

    def format_timestamp(self, ts: int) -> str:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")

    async def fetch_quota(self, api_key: str, region: str, group_id: str) -> dict:
        url = self.get_api_url(region, group_id)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with self._session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    title, suggestion = ERROR_MESSAGES.get(
                        response.status, ("未知错误", "请稍后重试")
                    )
                    try:
                        error_data = await response.json()
                        detail = error_data.get("base_resp", {}).get("status_msg", "")
                    except Exception:
                        detail = await response.text()

                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=f"{title}：{detail}" if detail else title,
                        headers=response.headers,
                    )
        except aiohttp.ClientResponseError as e:
            raise QueryError(f"{e.message}（状态码：{e.status}）") from e
        except aiohttp.ClientConnectorError as e:
            raise QueryError("网络连接失败，请检查网络或 MiniMax 服务状态") from e
        except TimeoutError as e:
            raise QueryError("请求超时，请检查网络连接后重试") from e

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
                    raise QueryError(f"API 返回错误：{msg}（{error_msg}）")
            raise QueryError(f"API 返回错误：{error_msg}（状态码：{status_code}）")

        model_list = data.get("model_remains", [])
        if not model_list:
            raise QueryError("未获取到任何额度数据，接口返回格式可能已变更")

        model = model_list[0]

        intv_total = model["current_interval_total_count"]
        intv_used = model["current_interval_usage_count"]
        intv_remain = intv_total - intv_used
        intv_percent = (intv_remain / intv_total) * 100 if intv_total > 0 else 0

        week_total = model["current_weekly_total_count"]
        week_used = model["current_weekly_usage_count"]
        week_remain = week_total - week_used
        week_percent = (week_remain / week_total) * 100 if week_total > 0 else 0

        remains_time_minutes = round(model['remains_time'] / 60, 1)

        result = f"套餐名称：Token Plan\n"
        result += f"5小时剩余/总额：{intv_remain}/{intv_total} ({intv_percent:.1f}%)\n"
        result += f"本周剩余/总额：{week_remain}/{week_total} ({week_percent:.1f}%)\n"
        result += f"\n📅 5小时滚动周期：{self.format_timestamp(model['start_time'])} ~ {self.format_timestamp(model['end_time'])}\n"
        result += f"📅 本周周期：{self.format_timestamp(model['weekly_start_time'])} ~ {self.format_timestamp(model['weekly_end_time'])}\n"
        result += f"⏰ 距离5小时重置：{remains_time_minutes} 分钟\n"
        result += f"\n✅ 查询完成！"

        return result

    @filter.command("用量")
    async def query_quota(self, event: AstrMessageEvent):
        api_key = self.config.get("api_key", "")
        region = self.config.get("region", "国内")
        group_id = self.config.get("group_id", "")

        if not api_key:
            yield event.plain_result("⚠️ 请先在插件设置中配置 MiniMax API Key")
            return

        try:
            quota_data = await self.fetch_quota(api_key, region, group_id)
            result = self.parse_data(quota_data)
            yield event.plain_result(result)
        except ValueError as e:
            yield event.plain_result(f"⚠️ 配置错误：{str(e)}")
        except QueryError as e:
            yield event.plain_result(f"❌ {str(e)}")
        except Exception as e:
            yield event.plain_result(f"❌ 查询失败：{str(e)}")

    async def terminate(self):
        if self._session:
            await self._session.close()
            self._session = None


class QueryError(Exception):
    """查询业务异常"""
    pass
