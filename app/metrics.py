from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# HTTP request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['path', 'status']
)

# Webhook-specific metrics
webhook_requests_total = Counter(
    'webhook_requests_total',
    'Total webhook requests by result',
    ['result']
)

# Request latency
request_latency_ms = Histogram(
    'request_latency_ms',
    'Request latency in milliseconds',
    buckets=[100, 500, 1000, 5000, 10000]
)

def record_http_request(path: str, status: int):
    """Record HTTP request metrics"""
    http_requests_total.labels(path=path, status=str(status)).inc()

def record_webhook_request(result: str):
    """Record webhook processing result"""
    webhook_requests_total.labels(result=result).inc()

def record_latency(latency_ms: float):
    """Record request latency"""
    request_latency_ms.observe(latency_ms)

def get_metrics():
    """Get Prometheus metrics"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)