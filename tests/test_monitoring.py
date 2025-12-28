"""
Tests for monitoring and observability.

Tests metrics collection, structured logging, and health checks.
"""

import pytest
import time
from unittest.mock import patch, Mock

from adk_npl.monitoring import (
    MetricsCollector,
    StructuredLogger,
    HealthCheck,
    get_metrics
)
from adk_npl import NPLClient


class TestMetricsCollector:
    """Test metrics collection."""
    
    def test_increment_counter(self):
        """Test incrementing counter metrics."""
        metrics = MetricsCollector()
        metrics.increment("test.counter")
        metrics.increment("test.counter", value=2)
        
        counters = metrics.get_counters()
        assert counters["test.counter"] == 3
    
    def test_increment_with_tags(self):
        """Test incrementing counters with tags."""
        metrics = MetricsCollector()
        metrics.increment("test.counter", method="GET", status_code=200)
        metrics.increment("test.counter", method="POST", status_code=201)
        
        counters = metrics.get_counters()
        assert "test.counter[method=GET,status_code=200]" in counters
        assert "test.counter[method=POST,status_code=201]" in counters
    
    def test_record_latency(self):
        """Test recording latency measurements."""
        metrics = MetricsCollector()
        metrics.record_latency("test.latency", 0.1)
        metrics.record_latency("test.latency", 0.2)
        metrics.record_latency("test.latency", 0.3)
        
        stats = metrics.get_latency_stats("test.latency")
        assert stats is not None
        assert stats["count"] == 3
        assert stats["min"] == 0.1
        assert stats["max"] == 0.3
        assert stats["avg"] == pytest.approx(0.2, rel=0.1)
        assert "p50" in stats
        assert "p95" in stats
        assert "p99" in stats
    
    def test_record_error(self):
        """Test recording errors."""
        metrics = MetricsCollector()
        metrics.record_error("TestError", "Something went wrong", url="/test", status_code=500)
        
        errors = metrics.get_errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "TestError"
        assert errors[0]["message"] == "Something went wrong"
        assert errors[0]["url"] == "/test"
        assert errors[0]["status_code"] == 500
    
    def test_error_limit(self):
        """Test that error list is limited."""
        metrics = MetricsCollector()
        
        # Record more errors than the limit
        for i in range(150):
            metrics.record_error("TestError", f"Error {i}")
        
        errors = metrics.get_errors()
        # Should only keep last 100 errors
        assert len(errors) <= 100
    
    def test_get_summary(self):
        """Test getting metrics summary."""
        metrics = MetricsCollector()
        metrics.increment("test.counter")
        metrics.record_latency("test.latency", 0.1)
        metrics.record_error("TestError", "Test error")
        
        summary = metrics.get_summary()
        assert "counters" in summary
        assert "recent_errors" in summary
        assert "timestamp" in summary
        assert len(summary["recent_errors"]) == 1
    
    def test_reset(self):
        """Test resetting metrics."""
        metrics = MetricsCollector()
        metrics.increment("test.counter")
        metrics.record_latency("test.latency", 0.1)
        metrics.record_error("TestError", "Test error")
        
        metrics.reset()
        
        assert len(metrics.get_counters()) == 0
        assert metrics.get_latency_stats("test.latency") is None
        assert len(metrics.get_errors()) == 0


class TestStructuredLogger:
    """Test structured logging."""
    
    def test_plain_text_logging(self):
        """Test plain text logging format."""
        import logging
        logger = StructuredLogger("test", use_json=False)
        
        with patch.object(logger.logger, 'info') as mock_info:
            logger.info("Test message", key="value")
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "Test message" in call_args
            assert "key=value" in call_args
    
    def test_json_logging(self):
        """Test JSON logging format."""
        import json
        import logging
        logger = StructuredLogger("test", use_json=True)
        
        with patch.object(logger.logger, 'info') as mock_info:
            logger.info("Test message", key="value")
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            
            # Should be valid JSON
            log_entry = json.loads(call_args)
            assert log_entry["message"] == "Test message"
            assert log_entry["key"] == "value"
            assert "timestamp" in log_entry
            assert "level" in log_entry


class TestHealthCheck:
    """Test health check utilities."""
    
    def test_check_engine_health_healthy(self):
        """Test health check when engine is healthy."""
        client = NPLClient(base_url="http://localhost:12000")
        health_check = HealthCheck(client)
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"status": "UP"}
            mock_response.content = b'{"status": "UP"}'
            mock_get.return_value = mock_response
            
            health = health_check.check_engine_health()
            assert health["status"] == "healthy"
            assert "latency_seconds" in health
    
    def test_check_engine_health_unhealthy(self):
        """Test health check when engine is unhealthy."""
        client = NPLClient(base_url="http://localhost:12000")
        health_check = HealthCheck(client)
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 503
            mock_response.text = "Service Unavailable"
            mock_get.return_value = mock_response
            
            health = health_check.check_engine_health()
            assert health["status"] == "unhealthy"
            assert health["status_code"] == 503
    
    def test_check_engine_health_unreachable(self):
        """Test health check when engine is unreachable."""
        client = NPLClient(base_url="http://localhost:12000")
        health_check = HealthCheck(client)
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Connection refused")
            
            health = health_check.check_engine_health()
            assert health["status"] == "unreachable"
            assert "error" in health
    
    def test_check_authentication_authenticated(self):
        """Test authentication check when authenticated."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="test_token"
        )
        health_check = HealthCheck(client)
        
        # Mock healthy engine
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"status": "UP"}
            mock_response.content = b'{"status": "UP"}'
            mock_get.return_value = mock_response
            
            auth = health_check.check_authentication()
            assert auth["status"] == "authenticated"
            assert auth["authenticated"] is True
    
    def test_check_authentication_not_authenticated(self):
        """Test authentication check when not authenticated."""
        client = NPLClient(base_url="http://localhost:12000")
        health_check = HealthCheck(client)
        
        auth = health_check.check_authentication()
        assert auth["status"] == "not_authenticated"
        assert auth["authenticated"] is False
    
    def test_get_full_health(self):
        """Test getting complete health status."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="test_token"
        )
        health_check = HealthCheck(client)
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"status": "UP"}
            mock_response.content = b'{"status": "UP"}'
            mock_get.return_value = mock_response
            
            full_health = health_check.get_full_health()
            assert "engine" in full_health
            assert "authentication" in full_health
            assert "metrics" in full_health
            assert "timestamp" in full_health

