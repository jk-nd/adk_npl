import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import './MetricsDashboard.css';

interface MetricsSummary {
  counters: Record<string, Record<string, number>>;
  latencies: Record<string, Record<string, LatencyStats>>;
  recent_errors: Array<{
    timestamp: string;
    type: string;
    message: string;
    tags: Record<string, any>;
  }>;
  timestamp: string;
}

interface LatencyStats {
  count: number;
  sum: number;
  avg: number;
  min: number;
  max: number;
  p50: number;
  p95: number;
  p99: number;
}

const ACTIVITY_API_URL = 'http://localhost:8002';

export function MetricsDashboard() {
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Fetch metrics
  const { data: metrics, refetch } = useQuery<MetricsSummary>({
    queryKey: ['metrics', 'summary'],
    queryFn: async () => {
      const response = await fetch(`${ACTIVITY_API_URL}/api/metrics`);
      if (!response.ok) throw new Error('Failed to fetch metrics');
      return response.json();
    },
    refetchInterval: autoRefresh ? 3000 : false, // Refresh every 3 seconds
  });

  const formatNumber = (num: number, decimals: number = 2) => {
    return num.toFixed(decimals);
  };

  const formatDuration = (ms: number) => {
    if (ms < 1) return `${formatNumber(ms * 1000, 3)}µs`;
    if (ms < 1000) return `${formatNumber(ms, 2)}ms`;
    return `${formatNumber(ms / 1000, 2)}s`;
  };

  const getTotalCalls = () => {
    if (!metrics?.counters) return 0;
    return Object.values(metrics.counters)
      .flatMap(tagCounts => Object.values(tagCounts))
      .reduce((sum, count) => sum + count, 0);
  };

  const getTotalErrors = () => {
    return metrics?.recent_errors?.length || 0;
  };

  return (
    <div className="metrics-dashboard-container">
      {/* Header */}
      <div className="metrics-dashboard-header">
        <h2>Metrics Dashboard</h2>
        <div className="metrics-dashboard-controls">
          <label className="auto-refresh-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto-refresh</span>
          </label>
          <button className="refresh-btn" onClick={() => refetch()} title="Refresh">
            ↻
          </button>
        </div>
      </div>

      {/* Overview */}
      <div className="metrics-overview">
        <div className="metric-card">
          <div className="metric-icon">◉</div>
          <div className="metric-content">
            <div className="metric-label">Total API Calls</div>
            <div className="metric-value">{getTotalCalls()}</div>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon">◐</div>
          <div className="metric-content">
            <div className="metric-label">Avg Latency</div>
            <div className="metric-value">
              {(() => {
                const latencyKey = Object.keys(metrics?.latencies || {})[0];
                const latencyStats = latencyKey ? metrics?.latencies?.[latencyKey]?.[''] : null;
                return latencyStats?.avg ? formatDuration(latencyStats.avg) : 'N/A';
              })()}
            </div>
          </div>
        </div>
        <div className="metric-card error">
          <div className="metric-icon">◈</div>
          <div className="metric-content">
            <div className="metric-label">Recent Errors</div>
            <div className="metric-value">{getTotalErrors()}</div>
          </div>
        </div>
      </div>

      {/* Counters */}
      {metrics?.counters && Object.keys(metrics.counters).length > 0 && (
        <div className="metrics-section">
          <details open className="section-details">
            <summary className="section-summary">
              <h3>Counters</h3>
            </summary>
            <div className="counters-grid">
            {Object.entries(metrics.counters).map(([name, tagCounts]) => (
              <div key={name} className="counter-card">
                <div className="counter-name">{name}</div>
                <div className="counter-tags">
                  {Object.entries(tagCounts).map(([tags, count]) => (
                    <div key={tags} className="counter-tag-item">
                      <span className="counter-tags-label">
                        {tags || 'total'}
                      </span>
                      <span className="counter-value">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            </div>
          </details>
        </div>
      )}

      {/* Latencies */}
      {metrics?.latencies && Object.keys(metrics.latencies).length > 0 && (
        <div className="metrics-section">
          <details open className="section-details">
            <summary className="section-summary">
              <h3>Latencies</h3>
            </summary>
            <div className="latencies-grid">
            {Object.entries(metrics.latencies).map(([name, tagStats]) => (
              Object.entries(tagStats).map(([tags, stats]) => (
                <div key={`${name}-${tags}`} className="latency-card">
                  <div className="latency-name">{name}</div>
                  {tags && <div className="latency-tags">{tags}</div>}
                  <div className="latency-stats">
                    <div className="stat-item">
                      <span className="stat-label">Avg:</span>
                      <span className="stat-value">{formatDuration(stats.avg)}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">P50:</span>
                      <span className="stat-value">{formatDuration(stats.p50)}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">P95:</span>
                      <span className="stat-value">{formatDuration(stats.p95)}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">P99:</span>
                      <span className="stat-value">{formatDuration(stats.p99)}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Min:</span>
                      <span className="stat-value">{formatDuration(stats.min)}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Max:</span>
                      <span className="stat-value">{formatDuration(stats.max)}</span>
                    </div>
                    <div className="stat-item full-width">
                      <span className="stat-label">Count:</span>
                      <span className="stat-value">{stats.count}</span>
                    </div>
                  </div>
                </div>
              ))
            ))}
            </div>
          </details>
        </div>
      )}

      {/* Recent Errors */}
      {metrics?.recent_errors && metrics.recent_errors.length > 0 && (
        <div className="metrics-section">
          <details open className="section-details">
            <summary className="section-summary">
              <h3>Recent Errors ({metrics.recent_errors.length})</h3>
            </summary>
            <div className="errors-list">
            {metrics.recent_errors.slice(-10).reverse().map((error, index) => (
              <div key={index} className="error-item">
                <div className="error-header">
                  <span className="error-timestamp">
                    {new Date(error.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="error-type">{error.type}</span>
                </div>
                <div className="error-message">{error.message}</div>
                {Object.keys(error.tags).length > 0 && (
                  <details className="error-tags">
                    <summary>Tags</summary>
                    <pre>{JSON.stringify(error.tags, null, 2)}</pre>
                  </details>
                )}
              </div>
            ))}
            </div>
          </details>
        </div>
      )}

      {/* No Data */}
      {(!metrics || (
        Object.keys(metrics.counters || {}).length === 0 &&
        Object.keys(metrics.latencies || {}).length === 0 &&
        (metrics.recent_errors || []).length === 0
      )) && (
        <div className="no-data">
          No metrics data available. Run the demo script to generate metrics.
        </div>
      )}
    </div>
  );
}

