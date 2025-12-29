"""
Activity Feed API

Provides REST endpoints for accessing activity logs and metrics in real-time.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from adk_npl.activity_logger import get_activity_logger
from adk_npl.monitoring import get_metrics

app = FastAPI(
    title="Activity Feed API",
    description="Real-time activity logging and metrics for ADK-NPL integration",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative frontend port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/api/activity/logs")
async def get_activity_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Read activity events from the latest log file.
    
    Args:
        limit: Maximum number of events to return (default: 100)
    
    Returns:
        List of activity events
    """
    try:
        # Find the latest log file
        logs_dir = Path(__file__).parent.parent / "logs"
        if not logs_dir.exists():
            return []
        
        # Read the activity_latest.json symlink or find the latest file
        latest_link = logs_dir / "activity_latest.json"
        if latest_link.exists():
            log_file = latest_link
        else:
            # Find the most recent log file
            log_files = sorted(logs_dir.glob("activity_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not log_files:
                return []
            log_file = log_files[0]
        
        # Read and parse the log file
        events = []
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError:
                        continue
        
        # Return the most recent events (up to limit)
        return events[-limit:] if len(events) > limit else events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/activity/recent")
async def get_recent_activity(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get recent activity events (alias for /api/activity/logs).
    
    Args:
        limit: Maximum number of events to return (default: 100)
    
    Returns:
        List of activity events
    """
    return await get_activity_logs(limit=limit)


@app.get("/api/activity/by-type/{event_type}")
async def get_activity_by_type(
    event_type: str,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get recent activity events of a specific type from log files.
    
    Args:
        event_type: Type of events to retrieve
        limit: Maximum number of events to return (default: 100)
    
    Returns:
        List of activity events filtered by type
    """
    try:
        # Read the latest log file
        logs_dir = Path(__file__).parent.parent / "logs"
        if not logs_dir.exists():
            return []
        
        latest_link = logs_dir / "activity_latest.json"
        if not latest_link.exists():
            log_files = sorted(logs_dir.glob("activity_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not log_files:
                return []
            log_file = log_files[0]
        else:
            log_file = latest_link
        
        # Read and filter events by type
        events = []
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        event = json.loads(line)
                        if event.get('event_type') == event_type:
                            events.append(event)
                    except json.JSONDecodeError:
                        continue
        
        # Return the most recent events (up to limit)
        return events[-limit:] if len(events) > limit else events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/activity/by-actor/{actor}")
async def get_activity_by_actor(
    actor: str,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get recent activity events by a specific actor from log files.
    
    Args:
        actor: Actor name
        limit: Maximum number of events to return (default: 100)
    
    Returns:
        List of activity events filtered by actor
    """
    try:
        # Read the latest log file
        logs_dir = Path(__file__).parent.parent / "logs"
        if not logs_dir.exists():
            return []
        
        latest_link = logs_dir / "activity_latest.json"
        if not latest_link.exists():
            log_files = sorted(logs_dir.glob("activity_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not log_files:
                return []
            log_file = log_files[0]
        else:
            log_file = latest_link
        
        # Read and filter events by actor
        events = []
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        event = json.loads(line)
                        if event.get('actor') == actor:
                            events.append(event)
                    except json.JSONDecodeError:
                        continue
        
        # Return the most recent events (up to limit)
        return events[-limit:] if len(events) > limit else events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/activity/summary")
async def get_activity_summary() -> Dict[str, Any]:
    """
    Get session summary statistics from log files.
    
    Returns:
        Summary statistics for the current session
    """
    try:
        # Read the latest log file
        logs_dir = Path(__file__).parent.parent / "logs"
        if not logs_dir.exists():
            return {
                "total_events": 0,
                "by_type": {},
                "by_actor": {},
                "by_level": {"info": 0, "warning": 0, "error": 0},
                "log_file": None,
                "session_start": None
            }
        
        latest_link = logs_dir / "activity_latest.json"
        if not latest_link.exists():
            log_files = sorted(logs_dir.glob("activity_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not log_files:
                return {
                    "total_events": 0,
                    "by_type": {},
                    "by_actor": {},
                    "by_level": {"info": 0, "warning": 0, "error": 0},
                    "log_file": None,
                    "session_start": None
                }
            log_file = log_files[0]
        else:
            log_file = latest_link
        
        # Parse events and build summary
        from collections import defaultdict
        by_type = defaultdict(int)
        by_actor = defaultdict(int)
        by_level = {"info": 0, "warning": 0, "error": 0}
        session_start = None
        total_events = 0
        
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        event = json.loads(line)
                        total_events += 1
                        
                        event_type = event.get('event_type', 'unknown')
                        actor = event.get('actor', 'unknown')
                        level = event.get('level', 'info')
                        
                        by_type[event_type] += 1
                        by_actor[actor] += 1
                        by_level[level] = by_level.get(level, 0) + 1
                        
                        if session_start is None:
                            session_start = event.get('timestamp')
                    except json.JSONDecodeError:
                        continue
        
        return {
            "total_events": total_events,
            "by_type": dict(by_type),
            "by_actor": dict(by_actor),
            "by_level": by_level,
            "log_file": str(log_file.name),
            "session_start": session_start
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics")
async def get_metrics_summary() -> Dict[str, Any]:
    """
    Get metrics summary calculated from log files.
    
    Returns:
        Metrics summary with counters, latencies, LLM calls, A2A transfers, and recent errors
    """
    try:
        # Read the latest log file
        logs_dir = Path(__file__).parent.parent / "logs"
        if not logs_dir.exists():
            return {"counters": {}, "latencies": {}, "recent_errors": [], "timestamp": "",
                    "llm_calls": None, "a2a_transfers": None, "npl_calls": None}
        
        latest_link = logs_dir / "activity_latest.json"
        if not latest_link.exists():
            log_files = sorted(logs_dir.glob("activity_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not log_files:
                return {"counters": {}, "latencies": {}, "recent_errors": [], "timestamp": "",
                        "llm_calls": None, "a2a_transfers": None, "npl_calls": None}
            log_file = log_files[0]
        else:
            log_file = latest_link
        
        # Parse events and calculate metrics
        from collections import defaultdict
        counters = defaultdict(lambda: defaultdict(int))
        latencies = defaultdict(list)
        recent_errors = []
        
        # LLM metrics
        llm_calls_total = 0
        llm_calls_by_agent = defaultdict(int)
        llm_latencies = []
        
        # A2A metrics
        a2a_transfers_total = 0
        a2a_by_agent = defaultdict(int)
        a2a_latencies = []
        
        # NPL metrics
        npl_calls_total = 0
        npl_by_action = defaultdict(int)
        npl_latencies = []
        
        with open(log_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get('event_type', 'unknown')
                    actor = event.get('actor', 'unknown')
                    level = event.get('level', 'info')
                    details = event.get('details', {})
                    
                    # Count events by type and actor
                    counters[f"{event_type}_by_actor"][actor] += 1
                    counters[f"events_by_type"][event_type] += 1
                    counters[f"events_by_level"][level] += 1
                    
                    # LLM call metrics
                    if event_type == 'llm_call':
                        llm_calls_total += 1
                        agent = details.get('agent', actor)
                        llm_calls_by_agent[agent] += 1
                        latency = details.get('latency_ms', 0)
                        if latency > 0:
                            llm_latencies.append(latency)
                    
                    # A2A transfer metrics
                    if event_type == 'a2a_transfer':
                        a2a_transfers_total += 1
                        from_agent = details.get('from_agent', actor)
                        a2a_by_agent[from_agent] += 1
                        latency = details.get('latency_ms', 0)
                        if latency > 0:
                            a2a_latencies.append(latency)
                    
                    # A2A message metrics (detailed HTTP)
                    if event_type == 'a2a_message':
                        a2a_transfers_total += 1
                        from_agent = details.get('from_agent', actor)
                        a2a_by_agent[from_agent] += 1
                        latency = details.get('latency_ms', 0)
                        if latency and latency > 0:
                            a2a_latencies.append(latency)
                    
                    # NPL API call metrics
                    if event_type == 'npl_api':
                        npl_calls_total += 1
                        action = event.get('action', 'unknown')
                        npl_by_action[action] += 1
                        response_time = details.get('response_time_ms', 0)
                        if response_time > 0:
                            npl_latencies.append(response_time)
                            latencies['npl_api_latency'].append(response_time)
                    
                    # Agent action metrics (count as NPL tool calls)
                    if event_type == 'agent_action':
                        action = event.get('action', 'unknown')
                        if 'npl_' in action:
                            npl_calls_total += 1
                            npl_by_action[action] += 1
                    
                    # Track errors
                    if level in ['error', 'warning'] or details.get('outcome') == 'blocked_by_npl':
                        recent_errors.append({
                            'timestamp': event.get('timestamp', ''),
                            'type': event_type,
                            'message': event.get('action', ''),
                            'tags': {'actor': actor, 'level': level}
                        })
                
                except json.JSONDecodeError:
                    continue
        
        # Calculate latency stats
        latency_stats = {}
        for name, values in latencies.items():
            if values:
                values.sort()
                latency_stats[name] = {
                    "": {  # Default tag
                        "count": len(values),
                        "sum": sum(values),
                        "avg": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "p50": values[int(len(values) * 0.50)],
                        "p95": values[int(len(values) * 0.95)] if len(values) > 1 else values[0],
                        "p99": values[int(len(values) * 0.99)] if len(values) > 1 else values[0]
                    }
                }
        
        # Add LLM latency stats
        if llm_latencies:
            llm_latencies.sort()
            latency_stats["llm_api_latency"] = {
                "": {
                    "count": len(llm_latencies),
                    "sum": sum(llm_latencies),
                    "avg": sum(llm_latencies) / len(llm_latencies),
                    "min": min(llm_latencies),
                    "max": max(llm_latencies),
                    "p50": llm_latencies[int(len(llm_latencies) * 0.50)],
                    "p95": llm_latencies[int(len(llm_latencies) * 0.95)] if len(llm_latencies) > 1 else llm_latencies[0],
                    "p99": llm_latencies[int(len(llm_latencies) * 0.99)] if len(llm_latencies) > 1 else llm_latencies[0]
                }
            }
        
        # Add A2A latency stats
        if a2a_latencies:
            a2a_latencies.sort()
            latency_stats["a2a_transfer_latency"] = {
                "": {
                    "count": len(a2a_latencies),
                    "sum": sum(a2a_latencies),
                    "avg": sum(a2a_latencies) / len(a2a_latencies),
                    "min": min(a2a_latencies),
                    "max": max(a2a_latencies),
                    "p50": a2a_latencies[int(len(a2a_latencies) * 0.50)],
                    "p95": a2a_latencies[int(len(a2a_latencies) * 0.95)] if len(a2a_latencies) > 1 else a2a_latencies[0],
                    "p99": a2a_latencies[int(len(a2a_latencies) * 0.99)] if len(a2a_latencies) > 1 else a2a_latencies[0]
                }
            }
        
        # Build enhanced metrics
        llm_calls = None
        if llm_calls_total > 0:
            llm_calls = {
                "total": llm_calls_total,
                "by_agent": dict(llm_calls_by_agent),
                "avg_latency_ms": sum(llm_latencies) / len(llm_latencies) if llm_latencies else 0,
                "total_latency_ms": sum(llm_latencies)
            }
        
        a2a_transfers = None
        if a2a_transfers_total > 0:
            a2a_transfers = {
                "total": a2a_transfers_total,
                "by_agent": dict(a2a_by_agent),
                "avg_latency_ms": sum(a2a_latencies) / len(a2a_latencies) if a2a_latencies else 0
            }
        
        npl_calls = None
        if npl_calls_total > 0:
            npl_calls = {
                "total": npl_calls_total,
                "by_action": dict(npl_by_action),
                "avg_latency_ms": sum(npl_latencies) / len(npl_latencies) if npl_latencies else 0
            }
        
        return {
            "counters": {k: dict(v) for k, v in counters.items()},
            "latencies": latency_stats,
            "recent_errors": recent_errors[-20:],  # Last 20 errors
            "llm_calls": llm_calls,
            "a2a_transfers": a2a_transfers,
            "npl_calls": npl_calls,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/latency/{name}")
async def get_latency_stats(name: str) -> Optional[Dict[str, float]]:
    """
    Get latency statistics for a specific metric.
    
    Args:
        name: Metric name
    
    Returns:
        Latency statistics or None if not found
    """
    try:
        metrics = get_metrics()
        stats = metrics.get_latency_stats(name)
        if stats is None:
            raise HTTPException(status_code=404, detail=f"Metric '{name}' not found")
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/metrics/reset")
async def reset_metrics():
    """Reset all metrics."""
    try:
        metrics = get_metrics()
        metrics.reset()
        return {"status": "success", "message": "Metrics reset"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/activity/clear")
async def clear_activity_buffer():
    """Clear the activity log buffer."""
    try:
        logger = get_activity_logger()
        logger.clear_buffer()
        return {"status": "success", "message": "Activity buffer cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")

