# Monitoring & Observability

This document explains the monitoring capabilities in the ADK-NPL demo.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend Dashboard                            │
│   [Activity Log] [Metrics Dashboard] [Approvals]                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                          HTTP API Calls
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                      Activity API (8002)                             │
│                  FastAPI + In-Memory Metrics                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                        Reads Activity Logs
                                 │
                    ┌────────────▼────────────┐
                    │   logs/activity_*.json  │
                    │   (Written by Agents)   │
                    └─────────────────────────┘
```

## Activity Logging

### Log Events

The `ActivityLogger` (`adk_npl/activity_logger.py`) writes structured JSON logs:

```python
from adk_npl.activity_logger import activity_logger

# NPL API call
activity_logger.log_npl_api_call(
    method="POST",
    endpoint="/npl/commerce/Product",
    status_code=201,
    response_time=0.234,
    request_body={...},
    response_body={...},
    caller="buyer_agent"
)

# A2A message
activity_logger.log_a2a_message(
    from_agent="buyer_agent",
    to_agent="supplier_agent",
    message="I need to purchase 10 widgets",
    direction="send"
)

# LLM call
activity_logger.log_llm_call(
    model="gemini-2.0-flash",
    prompt_tokens=500,
    completion_tokens=150,
    latency_ms=1200
)
```

### Log Format

Logs are written in NDJSON format to `logs/activity_*.json`:

```json
{
  "timestamp": "2025-01-03T12:34:56.789Z",
  "event_type": "npl_api",
  "actor": "buyer_agent",
  "action": "POST /npl/commerce/Product",
  "level": "info",
  "details": {
    "method": "POST",
    "endpoint": "/npl/commerce/Product",
    "status_code": 201,
    "response_time_ms": 234,
    "caller": "buyer_agent"
  }
}
```

## Metrics Collection

### Built-in Metrics (`adk_npl/monitoring.py`)

```python
from adk_npl.monitoring import get_metrics

metrics = get_metrics()

# View summary
summary = metrics.get_summary()
print(f"Counters: {summary['counters']}")
print(f"Errors: {summary['recent_errors']}")

# Latency statistics
stats = metrics.get_latency_stats("npl.api.latency")
print(f"P50: {stats['p50']:.3f}s")
print(f"P95: {stats['p95']:.3f}s")
print(f"P99: {stats['p99']:.3f}s")
```

### Tracked Metrics

| Metric | Description |
|--------|-------------|
| `npl.api.calls` | Count of NPL Engine API calls |
| `npl.api.latency` | NPL API response times |
| `npl.api.errors` | NPL API error count |
| `a2a.messages` | A2A message count (send/receive) |
| `llm.calls` | Gemini API call count |
| `llm.latency` | Gemini API response times |

## Activity API Endpoints

### GET /activity/feed

Returns recent activity events:

```bash
curl http://localhost:8002/activity/feed
```

Response:
```json
{
  "events": [
    {
      "timestamp": "2025-01-03T12:34:56.789Z",
      "event_type": "npl_api",
      "actor": "buyer_agent",
      "action": "POST /npl/commerce/Product",
      "details": {...}
    }
  ]
}
```

### GET /metrics

Returns collected metrics:

```bash
curl http://localhost:8002/metrics
```

Response:
```json
{
  "counters": {
    "npl_api_calls": 45,
    "a2a_messages": 12,
    "llm_calls": 28
  },
  "latencies": {
    "npl_api": {"p50": 0.15, "p95": 0.45, "p99": 0.89},
    "llm": {"p50": 1.2, "p95": 2.1, "p99": 3.5}
  }
}
```

### GET /health

Health check endpoint:

```bash
curl http://localhost:8002/health
```

## Frontend Dashboard

### Activity Log Tab

- Real-time feed of all activity
- Color-coded by event type:
  - 🔵 NPL Engine calls
  - 🟢 A2A messages
  - 🟡 LLM calls
  - 🔴 Errors
- Expandable details for each event
- Filter toggles by event type

### Metrics Dashboard Tab

- **Counters**: Total calls by type
- **Latencies**: P50/P95/P99 percentiles
- **Errors**: Recent error list (collapsible)

### Theme Toggle

Dark/light mode toggle in the header.

## Starting the Monitoring Stack

### 1. Start Activity API

```bash
cd activity_api && ./run.sh
```

### 2. Access Dashboard

Open http://localhost:5173 and click "Activity" or "Metrics" tabs.

## Health Checks

### Using the HealthCheck Class

```python
from adk_npl.monitoring import HealthCheck
from adk_npl import NPLClient

client = NPLClient(base_url="http://localhost:12000", auth_token="...")
health = HealthCheck(client)

# Check NPL Engine
engine_status = health.check_engine_health()
print(f"Engine: {engine_status['status']}")

# Full health report
full_health = health.get_full_health()
```

## Troubleshooting

### No Activity Events

1. Check `logs/` directory for `activity_*.json` files
2. Ensure Activity API is running on port 8002
3. Check Chat API logs for activity logger initialization

### Missing Metrics

1. Verify agents are running and making API calls
2. Check Activity API logs for errors
3. Refresh the dashboard

### Stale Data

The Activity API reads from log files periodically. New events appear within 1-2 seconds.
