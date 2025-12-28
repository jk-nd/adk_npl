"""
Monitoring and observability utilities for ADK-NPL integration.

Provides structured logging, metrics collection, and health checks.
"""

import json
import time
import logging
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)


class StructuredLogger:
    """
    Structured logger that outputs JSON-formatted logs.
    
    Useful for log aggregation systems (ELK, CloudWatch, etc.).
    """
    
    def __init__(self, name: str, use_json: bool = False):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name
            use_json: If True, output JSON logs (default: False)
        """
        self.logger = logging.getLogger(name)
        self.use_json = use_json
    
    def _format_message(self, level: str, message: str, **kwargs) -> str:
        """Format log message as JSON or plain text."""
        if self.use_json:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "message": message,
                "logger": self.logger.name,
                **kwargs
            }
            return json.dumps(log_entry)
        else:
            # Plain text format with extra fields
            extra_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            if extra_str:
                return f"{message} | {extra_str}"
            return message
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        formatted = self._format_message("INFO", message, **kwargs)
        self.logger.info(formatted)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        formatted = self._format_message("WARNING", message, **kwargs)
        self.logger.warning(formatted)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        formatted = self._format_message("ERROR", message, **kwargs)
        self.logger.error(formatted)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        formatted = self._format_message("DEBUG", message, **kwargs)
        self.logger.debug(formatted)


class MetricsCollector:
    """
    Simple metrics collector for tracking API calls, errors, and latency.
    
    Thread-safe for use in multi-threaded environments.
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self._lock = Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._errors: List[Dict[str, Any]] = []
        self._max_errors = 100  # Keep last 100 errors
    
    def increment(self, metric_name: str, value: int = 1, **tags):
        """
        Increment a counter metric.
        
        Args:
            metric_name: Name of the metric (e.g., "npl.api.calls")
            value: Value to increment by (default: 1)
            **tags: Optional tags for the metric
        """
        with self._lock:
            key = self._format_key(metric_name, tags)
            self._counters[key] += value
    
    def record_latency(self, metric_name: str, latency_seconds: float, **tags):
        """
        Record a latency measurement.
        
        Args:
            metric_name: Name of the metric (e.g., "npl.api.latency")
            latency_seconds: Latency in seconds
            **tags: Optional tags for the metric
        """
        with self._lock:
            key = self._format_key(metric_name, tags)
            self._histograms[key].append(latency_seconds)
            # Keep only last 1000 measurements per metric
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
    
    def record_error(self, error_type: str, error_message: str, **context):
        """
        Record an error with context.
        
        Args:
            error_type: Type of error (e.g., "AuthenticationError")
            error_message: Error message
            **context: Additional context (url, status_code, etc.)
        """
        with self._lock:
            error_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": error_type,
                "message": error_message,
                **context
            }
            self._errors.append(error_entry)
            # Keep only last N errors
            if len(self._errors) > self._max_errors:
                self._errors = self._errors[-self._max_errors:]
    
    def _format_key(self, metric_name: str, tags: Dict[str, Any]) -> str:
        """Format metric key with tags."""
        if tags:
            tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
            return f"{metric_name}[{tag_str}]"
        return metric_name
    
    def get_counters(self) -> Dict[str, int]:
        """Get all counter metrics."""
        with self._lock:
            return dict(self._counters)
    
    def get_latency_stats(self, metric_name: str, **tags) -> Optional[Dict[str, float]]:
        """
        Get latency statistics for a metric.
        
        Args:
            metric_name: Name of the metric
            **tags: Tags to filter by
            
        Returns:
            Dict with min, max, avg, p50, p95, p99, or None if no data
        """
        with self._lock:
            key = self._format_key(metric_name, tags)
            values = self._histograms.get(key, [])
            
            if not values:
                return None
            
            sorted_values = sorted(values)
            n = len(sorted_values)
            
            return {
                "count": n,
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / n,
                "p50": sorted_values[int(n * 0.5)],
                "p95": sorted_values[int(n * 0.95)],
                "p99": sorted_values[int(n * 0.99)]
            }
    
    def get_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent errors.
        
        Args:
            limit: Maximum number of errors to return
            
        Returns:
            List of error entries (most recent first)
        """
        with self._lock:
            return list(reversed(self._errors[-limit:]))
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of all metrics.
        
        Returns:
            Dict with counters, latency stats, and recent errors
        """
        return {
            "counters": self.get_counters(),
            "recent_errors": self.get_errors(limit=10),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def reset(self):
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._errors.clear()


# Global metrics collector instance
_global_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return _global_metrics


class HealthCheck:
    """
    Health check utilities for NPL Engine connectivity.
    """
    
    def __init__(self, npl_client):
        """
        Initialize health check.
        
        Args:
            npl_client: NPLClient instance
        """
        self.npl_client = npl_client
    
    def check_engine_health(self) -> Dict[str, Any]:
        """
        Check NPL Engine health.
        
        Returns:
            Dict with health status and details
        """
        try:
            health_url = f"{self.npl_client.base_url}/actuator/health"
            
            start_time = time.time()
            response = requests.get(health_url, timeout=5.0)
            latency = time.time() - start_time
            
            if response.ok:
                return {
                    "status": "healthy",
                    "latency_seconds": latency,
                    "details": response.json() if response.content else {}
                }
            else:
                return {
                    "status": "unhealthy",
                    "latency_seconds": latency,
                    "status_code": response.status_code,
                    "error": response.text[:200]
                }
        except Exception as e:
            return {
                "status": "unreachable",
                "error": str(e)
            }
    
    def check_authentication(self) -> Dict[str, Any]:
        """
        Check authentication status.
        
        Returns:
            Dict with auth status
        """
        if not self.npl_client.auth_token:
            return {
                "status": "not_authenticated",
                "authenticated": False
            }
        
        # Try a simple API call to verify token is valid
        try:
            # Use a lightweight endpoint (package discovery or health)
            health = self.check_engine_health()
            if health["status"] == "healthy":
                return {
                    "status": "authenticated",
                    "authenticated": True
                }
            else:
                return {
                    "status": "authentication_failed",
                    "authenticated": False,
                    "error": health.get("error")
                }
        except Exception as e:
            return {
                "status": "authentication_error",
                "authenticated": False,
                "error": str(e)
            }
    
    def get_full_health(self) -> Dict[str, Any]:
        """
        Get complete health status.
        
        Returns:
            Dict with engine health, auth status, and metrics summary
        """
        return {
            "engine": self.check_engine_health(),
            "authentication": self.check_authentication(),
            "metrics": get_metrics().get_summary(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

