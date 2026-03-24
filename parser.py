from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from .api import QueryError
from astrbot.api import logger


CHINA_TIMEZONE_OFFSET = 8

PLAN_NAMES = {
    600: "Starter",
    1500: "Plus",
    4500: "Max",
    30000: "Ultra",
}


class DataParser:
    """数据解析器"""

    REQUIRED_FIELDS: list[str] = [
        "current_interval_total_count",
        "current_interval_usage_count",
        "start_time",
        "end_time",
        "current_weekly_total_count",
        "current_weekly_usage_count",
        "weekly_start_time",
        "weekly_end_time",
    ]

    def format_timestamp(self, ts: int) -> str:
        """
        格式化时间戳为可读字符串

        Args:
            ts: 毫秒级时间戳

        Returns:
            格式化的日期时间字符串
        """
        if ts <= 0:
            return "未知"
        return datetime.fromtimestamp(
            ts / 1000,
            tz=timezone(timedelta(hours=CHINA_TIMEZONE_OFFSET))
        ).strftime("%Y-%m-%d %H:%M:%S")
    
    def _get_plan_name(self, intv_total: int) -> str:
        """
        根据五小时总额获取套餐名称

        Args:
            intv_total: 五小时总额

        Returns:
            套餐名称
        """
        return PLAN_NAMES.get(intv_total, "Token Plan")

    def parse_quota_data(self, data: Dict[str, Any]) -> str:
        """
        解析配额数据并格式化输出

        Args:
            data: API 返回的配额数据

        Returns:
            格式化的输出字符串

        Raises:
            QueryError: 数据解析失败时抛出
        """
        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code")

        if status_code is not None and status_code != 0:
            error_msg = base_resp.get("status_msg", "未知错误")
            error_msg_lower = error_msg.lower()
            error_map = {
                "invalid_token": "API Key 无效，请检查配置",
                "token_expired": "API Key 已过期，请重新获取",
                "quota_exceeded": "额度已用尽，请等待重置",
                "rate_limited": "请求过于频繁，请稍后重试",
                "group_not_found": "Group ID 不存在，请检查配置",
                "permission_denied": "无权限访问，请确认账户状态",
            }
            for key, msg in error_map.items():
                if key in error_msg_lower:
                    logger.error(f"API 返回业务错误: {msg} ({error_msg})")
                    raise QueryError(f"API 返回错误：{msg}（{error_msg}）")
            logger.error(f"API 返回未知错误: {error_msg} (状态码: {status_code})")
            raise QueryError(f"API 返回错误：{error_msg}（状态码：{status_code}）")

        model_list = data.get("model_remains", [])
        if not model_list:
            logger.warning("model_remains 列表为空")
            raise QueryError("未获取到任何额度数据，接口返回格式可能已变更")

        logger.info(f"解析额度数据（共 {len(model_list)} 个模型）")

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
            china_tz = timezone(timedelta(hours=CHINA_TIMEZONE_OFFSET))
            end_time = datetime.fromtimestamp(end_time_ms / 1000, tz=china_tz)
            now = datetime.now(tz=china_tz)
            delta = end_time - now
            remains_time_minutes = max(0, int(delta.total_seconds() / 60))
        else:
            remains_time_minutes = 0

        return self.format_output(
            intv_remain=intv_remain,
            intv_total=intv_total,
            intv_percent=intv_percent,
            week_remain=week_remain,
            week_total=week_total,
            week_percent=week_percent,
            start_time=model.get('start_time', 0),
            end_time=model.get('end_time', 0),
            weekly_start_time=model.get('weekly_start_time', 0),
            weekly_end_time=model.get('weekly_end_time', 0),
            remains_time_minutes=remains_time_minutes,
        )

    def format_output(
        self,
        intv_remain: int,
        intv_total: int,
        intv_percent: float,
        week_remain: int,
        week_total: int,
        week_percent: float,
        start_time: int,
        end_time: int,
        weekly_start_time: int,
        weekly_end_time: int,
        remains_time_minutes: int,
    ) -> str:
        """
        格式化输出信息

        Returns:
            格式化的输出字符串
        """
        plan_name = self._get_plan_name(intv_total)
        intv_line = f"5小时剩余/总额：{intv_remain}/{intv_total} ({intv_percent:.1f}%)"
        
        if week_total == 0 and week_remain == 0:
            week_line = "本周剩余/总额：无周限额"
        else:
            week_line = f"本周剩余/总额：{week_remain}/{week_total} ({week_percent:.1f}%)"
        
        lines = [
            f"套餐：MiniMax Token Plan {plan_name}",
            intv_line,
            week_line,
            "",
            f"📅 5小时滚动周期：{self.format_timestamp(start_time)} ~ {self.format_timestamp(end_time)}",
            f"📅 本周周期：{self.format_timestamp(weekly_start_time)} ~ {self.format_timestamp(weekly_end_time)}",
            f"⏰ 距离5小时重置：{remains_time_minutes} 分钟",
            "",
            "✅ 查询完成！",
        ]
        return "\n".join(lines)
