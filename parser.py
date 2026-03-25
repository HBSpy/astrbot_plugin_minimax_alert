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


def detect_reset_type(start_time: int, end_time: int) -> str:
    """
    根据起止时间检测重置类型

    Args:
        start_time: 起始时间戳（毫秒）
        end_time: 结束时间戳（毫秒）

    Returns:
        重置类型: "daily" (按天), "5h" (5小时滚动), "weekly" (周), "unknown" (未知)
    """
    if start_time <= 0 or end_time <= 0:
        return "unknown"

    duration_ms = end_time - start_time
    duration_hours = duration_ms / (1000 * 60 * 60)

    # 5小时滚动
    if 4 <= duration_hours <= 6:
        return "5h"
    # 按天重置（约24小时）
    elif 23 <= duration_hours <= 25:
        return "daily"
    # 周重置（约168小时）
    elif 166 <= duration_hours <= 170:
        return "weekly"
    else:
        return "unknown"


def format_remaining_time(ms: int) -> str:
    """
    格式化剩余时间

    Args:
        ms: 剩余时间（毫秒）

    Returns:
        格式化的剩余时间字符串
    """
    if ms <= 0:
        return "已过期"

    total_seconds = ms / 1000
    days = int(total_seconds // 86400)
    hours = int((total_seconds % 86400) // 3600)
    minutes = int((total_seconds % 3600) // 60)

    if days > 0:
        return f"{days}天{hours}小时"
    elif hours > 0:
        return f"{hours}小时{minutes}分钟"
    else:
        return f"{minutes}分钟"


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

        model_outputs = []
        for idx, model in enumerate(model_list):
            # 过滤掉 token plan 不支持的模型（5小时和周限额都为 0）
            intv_total = model.get("current_interval_total_count", 0)
            week_total = model.get("current_weekly_total_count", 0)
            if intv_total == 0 and week_total == 0:
                logger.info(f"模型 {model.get('model_name', idx)} 无额度，跳过")
                continue

            missing_fields = [f for f in self.REQUIRED_FIELDS if model.get(f) is None]
            if missing_fields:
                logger.warning(f"模型 {idx} 缺少必填字段: {missing_fields}")
                continue

            intv_total = model.get("current_interval_total_count", 0)
            intv_used = model.get("current_interval_usage_count", 0)
            intv_remain = intv_total - intv_used
            intv_percent = (intv_remain / intv_total) * 100 if intv_total > 0 else 0

            week_total = model.get("current_weekly_total_count", 0)
            week_used = model.get("current_weekly_usage_count", 0)
            week_remain = week_total - week_used
            week_percent = (week_remain / week_total) * 100 if week_total > 0 else 0

            end_time_ms = model.get('end_time', 0)
            remains_time_minutes = 0
            if end_time_ms > 0:
                china_tz = timezone(timedelta(hours=CHINA_TIMEZONE_OFFSET))
                end_time = datetime.fromtimestamp(end_time_ms / 1000, tz=china_tz)
                now = datetime.now(tz=china_tz)
                delta = end_time - now
                remains_time_minutes = max(0, int(delta.total_seconds() / 60))

            model_name = model.get("model_name", f"Model {idx + 1}")

            # 检测重置类型
            reset_type = detect_reset_type(
                model.get('start_time', 0),
                model.get('end_time', 0)
            )
            weekly_reset_type = detect_reset_type(
                model.get('weekly_start_time', 0),
                model.get('weekly_end_time', 0)
            )

            model_outputs.append({
                "model_name": model_name,
                "intv_remain": intv_remain,
                "intv_total": intv_total,
                "intv_percent": intv_percent,
                "week_remain": week_remain,
                "week_total": week_total,
                "week_percent": week_percent,
                "start_time": model.get('start_time', 0),
                "end_time": model.get('end_time', 0),
                "weekly_start_time": model.get('weekly_start_time', 0),
                "weekly_end_time": model.get('weekly_end_time', 0),
                "remains_time_minutes": remains_time_minutes,
                "reset_type": reset_type,
                "weekly_reset_type": weekly_reset_type,
            })

        if not model_outputs:
            raise QueryError("未获取到任何有效的额度数据")

        return self.format_multi_model_output(model_outputs)

    def format_multi_model_output(self, model_outputs: list[dict]) -> str:
        """
        格式化多模型输出信息

        Args:
            model_outputs: 解析后的模型数据列表

        Returns:
            格式化的输出字符串
        """
        lines = []

        # 收集所有唯一的重置类型
        intv_reset_types = set(m.get("reset_type", "5h") for m in model_outputs)
        week_reset_types = set(m.get("weekly_reset_type", "weekly") for m in model_outputs)

        # 5小时重置类型显示名称
        intv_reset_name = {
            "5h": "5小时滚动",
            "daily": "按日重置",
            "weekly": "按周重置",
            "unknown": "周期",
        }.get(list(intv_reset_types)[0] if intv_reset_types else "5h", "周期")

        # 周重置类型显示名称
        week_reset_name = {
            "5h": "5小时滚动",
            "daily": "按日重置",
            "weekly": "本周周期",
            "unknown": "周期",
        }.get(list(week_reset_types)[0] if week_reset_types else "weekly", "本周周期")

        for model in model_outputs:
            plan_name = self._get_plan_name(model["intv_total"])

            # 根据重置类型调整显示文本
            if model.get("reset_type") == "daily":
                intv_line = f"日剩余/总额：{model['intv_remain']}/{model['intv_total']} ({model['intv_percent']:.1f}%)"
            else:
                intv_line = f"5小时剩余/总额：{model['intv_remain']}/{model['intv_total']} ({model['intv_percent']:.1f}%)"

            if model["week_total"] == 0 and model["week_remain"] == 0:
                week_line = f"{week_reset_name.split('重置')[0] if '重置' in week_reset_name else week_reset_name}剩余/总额：无周限额"
            else:
                week_line = f"{week_reset_name.split('重置')[0] if '重置' in week_reset_name else week_reset_name}剩余/总额：{model['week_remain']}/{model['week_total']} ({model['week_percent']:.1f}%)"

            model_lines = [
                f"🤖 {model['model_name']} ({plan_name})",
                intv_line,
                week_line,
            ]
            lines.extend(model_lines)

        # 添加公共的时间信息（使用第一个模型的时间）
        first_model = model_outputs[0]
        intv_reset = first_model.get("reset_type", "5h")
        week_reset = first_model.get("weekly_reset_type", "weekly")

        intv_label = {"5h": "5小时滚动周期", "daily": "日周期", "weekly": "周周期", "unknown": "周期"}.get(intv_reset, "周期")
        week_label = {"5h": "5小时滚动", "daily": "日周期", "weekly": "本周周期", "unknown": "周期"}.get(week_reset, "本周周期")

        # 格式化剩余时间
        remains_time_ms = first_model.get("remains_time_minutes", 0) * 60 * 1000
        remains_str = format_remaining_time(remains_time_ms)

        lines.extend([
            "",
            f"📅 {intv_label}：{self.format_timestamp(first_model['start_time'])} ~ {self.format_timestamp(first_model['end_time'])}",
            f"📅 {week_label}：{self.format_timestamp(first_model['weekly_start_time'])} ~ {self.format_timestamp(first_model['weekly_end_time'])}",
            f"⏰ 距离{intv_label.split('周期')[0]}重置：{remains_str}",
            "",
            "✅ 查询完成！",
        ])
        return "\n".join(lines)

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
        格式化输出信息（单模型兼容）

        Returns:
            格式化的输出字符串
        """
        plan_name = self._get_plan_name(intv_total)

        # 检测重置类型
        reset_type = detect_reset_type(start_time, end_time)
        weekly_reset_type = detect_reset_type(weekly_start_time, weekly_end_time)

        # 根据重置类型调整显示文本
        if reset_type == "daily":
            intv_line = f"日剩余/总额：{intv_remain}/{intv_total} ({intv_percent:.1f}%)"
            intv_label = "日周期"
            intv_reset_label = "日重置"
        else:
            intv_line = f"5小时剩余/总额：{intv_remain}/{intv_total} ({intv_percent:.1f}%)"
            intv_label = "5小时滚动周期"
            intv_reset_label = "5小时重置"

        if weekly_reset_type == "daily":
            week_label = "日周期"
        else:
            week_label = "本周周期"

        if week_total == 0 and week_remain == 0:
            week_line = f"{week_label}剩余/总额：无周限额"
        else:
            week_line = f"{week_label}剩余/总额：{week_remain}/{week_total} ({week_percent:.1f}%)"

        # 格式化剩余时间
        remains_time_ms = remains_time_minutes * 60 * 1000
        remains_str = format_remaining_time(remains_time_ms)

        lines = [
            f"套餐：MiniMax Token Plan {plan_name}",
            intv_line,
            week_line,
            "",
            f"📅 {intv_label}：{self.format_timestamp(start_time)} ~ {self.format_timestamp(end_time)}",
            f"📅 {week_label}：{self.format_timestamp(weekly_start_time)} ~ {self.format_timestamp(weekly_end_time)}",
            f"⏰ 距离{intv_reset_label}：{remains_str}",
            "",
            "✅ 查询完成！",
        ]
        return "\n".join(lines)
