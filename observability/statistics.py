import logging
from datetime import datetime
import zoneinfo
from collections import Counter
from observability.metrics import (
    METRIC_ALERTS_TOTAL,
    METRIC_ALERTS_HANDLED_TOTAL
)

logger = logging.getLogger('dvp_coc_bot')
def send_statistics(tz: zoneinfo.ZoneInfo, app_start_ts: datetime,) -> str:
    logger.debug("Recieved statistics request. Sending..."),

    header_msg_part = "**DevPlatform COC Alerts Bot** \n\n"
    uptime = datetime.now(tz) - app_start_ts

    if(uptime.seconds > 3600):
        uptime_msg_part = f"Uptime: {uptime.days}д {uptime.seconds // 3600}ч {uptime.seconds // 60}м\n\n"
    else:
        uptime_msg_part = f"Uptime: {uptime.seconds // 60}м {uptime.seconds % 60}с\n\n"

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

    response = header_msg_part + uptime_msg_part + alerts_stats_msg_part
    return response
