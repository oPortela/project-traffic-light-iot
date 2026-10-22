"""Bounded-cardinality metrics and structured logs without payloads or credentials."""
import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest, start_http_server

DOMAIN = CollectorRegistry()
MESSAGES = Counter('iot_messages_total', 'Durable message stages', ['stage'], registry=DOMAIN)
PERSISTENCE = Histogram('iot_persistence_seconds', 'Reception to persistence latency', registry=DOMAIN)
ALARMS = Gauge('iot_active_alarms', 'Active or acknowledged alarms', registry=DOMAIN)
STATE_AGE = Gauge('iot_latest_state_age_seconds', 'Age of latest reported state', registry=DOMAIN)
EDGE_DEPTH = Gauge('iot_edge_queue_messages', 'Messages pending or quarantined on edge', registry=DOMAIN)
EDGE_AGE = Gauge('iot_edge_oldest_seconds', 'Age of oldest buffered message', registry=DOMAIN)


def worker_metrics(port=9100):
    configure_logging()
    start_http_server(port, registry=DOMAIN)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(), 'nivel': record.levelname,
                           'servico': record.name, 'mensagem': record.getMessage(),
                           'correlation_id': getattr(record, 'correlation_id', None)}, ensure_ascii=True)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(logging.INFO)


def instrument(app, service):
    configure_logging()
    registry = CollectorRegistry()
    requests = Counter('iot_http_requests_total', 'HTTP requests', ['service', 'route', 'method', 'status'],
                       registry=registry)
    latency = Histogram('iot_http_duration_seconds', 'HTTP latency', ['service', 'route'], registry=registry)
    logger = logging.getLogger(service)

    @app.middleware('http')
    async def observed(request, call_next):
        started = time.monotonic()
        try:
            correlation = str(UUID(request.headers.get('X-Correlation-ID', '')))
        except ValueError:
            correlation = str(uuid4())
        response = await call_next(request)
        route = getattr(request.scope.get('route'), 'path', 'unmatched')
        if route not in ('/health', '/metrics'):
            requests.labels(service, route, request.method, str(response.status_code)).inc()
            latency.labels(service, route).observe(time.monotonic() - started)
            logger.info('request_completed status=%s route=%s', response.status_code, route,
                        extra={'correlation_id': correlation})
        response.headers['X-Correlation-ID'] = correlation
        return response

    @app.get('/metrics', include_in_schema=False)
    def metrics():
        return Response(generate_latest(registry) + generate_latest(DOMAIN), media_type=CONTENT_TYPE_LATEST)

    app.state.metrics = registry
