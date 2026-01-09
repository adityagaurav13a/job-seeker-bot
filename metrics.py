from prometheus_client import Counter, Histogram, start_http_server

# Total messages received
MESSAGES_TOTAL = Counter(
    "telegram_messages_total",
    "Total Telegram messages received"
)

# Total errors
ERRORS_TOTAL = Counter(
    "telegram_errors_total",
    "Total Telegram errors"
)

# Message processing latency
MESSAGE_LATENCY = Histogram(
    "telegram_message_latency_seconds",
    "Message processing latency"
)

def start_metrics_server(port: int = 8000):
    start_http_server(port)
