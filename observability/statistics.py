import logging
from datetime import datetime
import zoneinfo
from collections import Counter
from observability.metrics import (
    METRIC_ALERTS_TOTAL,
    METRIC_ALERTS_HANDLED_TOTAL,
    METRIC_LAST_ALERT_RECIEVED_TIME
)

logger = logging.getLogger('dvp_coc_bot')

def collect_alerts_by_resolution():
    all_metrics = METRIC_ALERTS_HANDLED_TOTAL.collect()

    # Инициализируем счетчики
    alerts_dict = {
        "received": 0,
        "flapping": 0,
        "not_critical": 0,
        "other": 0
    }

    # Суммируем значения
    for metric in all_metrics:
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                resolution = sample.labels.get("resolution")
                if resolution in alerts_dict:
                    alerts_dict[resolution] += int(sample.value)
    return alerts_dict

def send_statistics(tz: zoneinfo.ZoneInfo, app_start_ts: datetime) -> str:
    logger.debug("Recieved statistics request. Sending..."),

    header_msg_part = "**DevPlatform COC Alerts Bot** \n\n"
    uptime = datetime.now(tz) - app_start_ts
    if uptime.seconds >= 3600:
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        uptime_msg_part = f"Uptime: {uptime.days}д {hours}ч {minutes}м\n\n"
    else:
        minutes = uptime.seconds // 60
        seconds = uptime.seconds % 60
        uptime_msg_part = f"Uptime: {minutes}м {seconds}с\n"

    last_alert_ts = None
    for m in METRIC_LAST_ALERT_RECIEVED_TIME.collect():
        for s in m.samples:
            if s.name == "last_alert_timestamp_seconds":
                last_alert_ts = s.value
                break

    if last_alert_ts:
        last_alert_dt = datetime.fromtimestamp(last_alert_ts, tz=tz).astimezone(tz)
    else:
        # если метрика еще не выставлялась, считаем от старта приложения
        last_alert_dt = app_start_ts

    days_without_alerts = (datetime.now(tz) - last_alert_dt).days
    days_without_alerts_msg_part = f"Дней без алертов: {days_without_alerts}\n\n"

    alerts_total         = int(METRIC_ALERTS_TOTAL._value.get())
    alerts_by_resolution = collect_alerts_by_resolution()

    alerts_stats_msg_part = f"Все получено алертов - {alerts_total}.\n"
    if alerts_total > 0:
        alerts_stats_msg_part += f"**Из них:**\n"
        alerts_stats_msg_part += f"Принято - {alerts_by_resolution["received"]}\n"
        alerts_stats_msg_part += f"Флапы  - {alerts_by_resolution["flapping"]}\n"
        alerts_stats_msg_part += f"Не критичны - {alerts_by_resolution["not_critical"]}\n"
        alerts_stats_msg_part += f"Обработаны вручную - {alerts_by_resolution["other"]}\n"

    response = header_msg_part + uptime_msg_part + days_without_alerts_msg_part + alerts_stats_msg_part
    return response
