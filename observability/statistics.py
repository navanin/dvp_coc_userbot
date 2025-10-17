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

    alerts_total        = int(METRIC_ALERTS_TOTAL._value.get())
    alerts_received     = int(sum(child.get() for (res, _), child in METRIC_ALERTS_HANDLED_TOTAL._metrics.items() if res == 'received'))
    alerts_flapping     = int(sum(child.get() for (res, _), child in METRIC_ALERTS_HANDLED_TOTAL._metrics.items() if res == 'flapping'))
    alerts_not_critical = int(sum(child.get() for (res, _), child in METRIC_ALERTS_HANDLED_TOTAL._metrics.items() if res == 'not_critical'))
    alerts_other        = int(sum(child.get() for (res, _), child in METRIC_ALERTS_HANDLED_TOTAL._metrics.items() if res == 'other'))

    alerts_stats_msg_part = f"Все получено алертов - {alerts_total}.\n"
    if alerts_total > 0:
        alerts_stats_msg_part += f"**Из них:**\n"
        alerts_stats_msg_part += f"Принято - {alerts_received}\n"
        alerts_stats_msg_part += f"Флапы  - {alerts_flapping}\n"
        alerts_stats_msg_part += f"Не критичны - {alerts_not_critical}\n"
        alerts_stats_msg_part += f"Обработаны вручную - {alerts_other}\n"

    response = header_msg_part + uptime_msg_part + days_without_alerts_msg_part + alerts_stats_msg_part
    return response
