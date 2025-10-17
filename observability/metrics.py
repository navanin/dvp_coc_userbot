from datetime import datetime
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    start_http_server,
    disable_created_metrics
)

# Отключение метрик вида _created
# disable_created_metrics()

# Регистр метрик - общий для всего процесса
_registry = CollectorRegistry()

METRIC_APP_START_TIME = Gauge(
    "app_start_timestamp_seconds",
    "UNIX timestamp of application start",
    registry=_registry,
)
METRIC_LAST_ALERT_RECIEVED_TIME = Gauge(
    "last_alert_timestamp_seconds",
    "UNIX timestamp of last alert recieved",
    registry=_registry,
)

METRIC_ALERTS_TOTAL = Counter(
    "alerts_total",
    "Alerts recieved total",
    registry=_registry,
)

METRIC_ALERTS_HANDLED_TOTAL = Counter(
    "alerts_handled_total",
    "Alerts handled total",
    labelnames=["resolution", "responsible"],
    registry=_registry,
)

METRIC_ALERTS_ERRORS_TOTAL = Counter(
    "alerts_error_total",
    "Errors while handling alerts total",
    labelnames=["handler"],
    registry=_registry,
)

_metrics_started = False

def init_metrics_server(port: int = 9100) -> None:
    """Запуск HTTP-эндпоинта для Prometheus."""
    global _metrics_started
    if _metrics_started:
        return
    start_http_server(int(port), registry=_registry)
    _metrics_started = True


def set_app_start_timestamp(app_start_ts: datetime) -> None:
    METRIC_APP_START_TIME.set(app_start_ts.timestamp())

def set_last_alert_timestamp(last_alert_time: datetime) -> None:
    METRIC_LAST_ALERT_RECIEVED_TIME.set(last_alert_time.timestamp())

def inc_alerts_total_metric() -> None:
    METRIC_ALERTS_TOTAL.inc()

def inc_alerts_handled_metric(callback: str, responsible: str) -> None:
    METRIC_ALERTS_HANDLED_TOTAL.labels(
        resolution=callback or "unknown",
        responsible=responsible or "unknown"
    ).inc()

def inc_errors_total_metric(handler: str) -> None:
    METRIC_ALERTS_ERRORS_TOTAL.labels(handler=handler or "unknown").inc()

def get_alert_count() -> int:
    return int(METRIC_ALERTS_TOTAL._value.get())