/*
 * Copyright 2025 Noumena Digital AG
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
  // Enhanced metrics
  llm_calls?: {
    total: number;
    by_agent: Record<string, number>;
    avg_latency_ms: number;
    total_latency_ms: number;
  };
  a2a_transfers?: {
    total: number;
    by_agent: Record<string, number>;
    avg_latency_ms: number;
  };
  npl_calls?: {
    total: number;
    by_action: Record<string, number>;
    avg_latency_ms: number;
  };
  // New metrics
  tool_calls?: {
    total: number;
    by_agent: Record<string, number>;
  };
  notifications?: {
    total_received: number;
    total_processed: number;
    by_agent: Record<string, number>;
    by_type: Record<string, number>;
    avg_processing_time_ms: number;
    success_rate: number;
  };
  a2a_messages?: {
    total_sent: number;
    total_received: number;
    total_errors: number;
    by_route: Record<string, number>;
    avg_roundtrip_ms: number;
    success_rate: number;
  };
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

      {/* Key Metrics Overview */}
      <div className="metrics-overview">
        <div className="metric-card llm">
          <div className="metric-icon">◎</div>
          <div className="metric-content">
            <div className="metric-label">LLM API Calls</div>
            <div className="metric-value">{metrics?.llm_calls?.total || 0}</div>
            {metrics?.llm_calls?.avg_latency_ms && (
              <div className="metric-sublabel">
                Avg: {formatDuration(metrics.llm_calls.avg_latency_ms)}
              </div>
            )}
          </div>
        </div>
        <div className="metric-card tool-calls">
          <div className="metric-icon">🔧</div>
          <div className="metric-content">
            <div className="metric-label">Agent Tool Calls</div>
            <div className="metric-value">{metrics?.tool_calls?.total || 0}</div>
          </div>
        </div>
        <div className="metric-card a2a">
          <div className="metric-icon">⇄</div>
          <div className="metric-content">
            <div className="metric-label">A2A Messages</div>
            <div className="metric-value">{metrics?.a2a_messages?.total_sent || 0}</div>
            {metrics?.a2a_messages?.avg_roundtrip_ms && (
              <div className="metric-sublabel">
                Avg: {formatDuration(metrics.a2a_messages.avg_roundtrip_ms)}
              </div>
            )}
          </div>
        </div>
        <div className="metric-card notifications">
          <div className="metric-icon">🔔</div>
          <div className="metric-content">
            <div className="metric-label">Notifications</div>
            <div className="metric-value">{metrics?.notifications?.total_received || 0}</div>
            {metrics?.notifications?.success_rate !== undefined && (
              <div className="metric-sublabel">
                Success: {formatNumber(metrics.notifications.success_rate * 100, 1)}%
              </div>
            )}
          </div>
        </div>
        <div className="metric-card npl">
          <div className="metric-icon">◆</div>
          <div className="metric-content">
            <div className="metric-label">NPL API Calls</div>
            <div className="metric-value">{metrics?.npl_calls?.total || getTotalCalls()}</div>
            {metrics?.npl_calls?.avg_latency_ms && (
              <div className="metric-sublabel">
                Avg: {formatDuration(metrics.npl_calls.avg_latency_ms)}
              </div>
            )}
          </div>
        </div>
        <div className="metric-card error">
          <div className="metric-icon">⚠️</div>
          <div className="metric-content">
            <div className="metric-label">Errors</div>
            <div className="metric-value">{getTotalErrors()}</div>
          </div>
        </div>
      </div>

      {/* LLM Calls by Agent */}
      {metrics?.llm_calls?.by_agent && Object.keys(metrics.llm_calls.by_agent).length > 0 && (
        <div className="metrics-section">
          <details open className="section-details">
            <summary className="section-summary">
              <h3>◎ LLM Calls by Agent</h3>
            </summary>
            <div className="breakdown-grid">
              {Object.entries(metrics.llm_calls.by_agent).map(([agent, count]) => (
                <div key={agent} className="breakdown-item">
                  <span className="breakdown-label">{agent}</span>
                  <span className="breakdown-value">{count}</span>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}

      {/* Agent Tool Calls */}
      {metrics?.tool_calls && metrics.tool_calls.total > 0 && (
        <div className="metrics-section">
          <details open className="section-details">
            <summary className="section-summary">
              <h3>🔧 Agent Tool Calls</h3>
              <span className="section-subtitle">
                {metrics.tool_calls.total} calls
              </span>
            </summary>
            {metrics.tool_calls.by_agent && Object.keys(metrics.tool_calls.by_agent).length > 0 && (
              <>
                <h4 className="subsection-title">By Agent</h4>
                <div className="breakdown-grid">
                  {Object.entries(metrics.tool_calls.by_agent).map(([agent, count]) => (
                    <div key={agent} className="breakdown-item">
                      <span className="breakdown-label">{agent}</span>
                      <span className="breakdown-value">{count}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </details>
        </div>
      )}

      {/* Notifications */}
      {metrics?.notifications && metrics.notifications.total_received > 0 && (
        <div className="metrics-section">
          <details open className="section-details">
            <summary className="section-summary">
              <h3>🔔 NPL Notifications</h3>
              <span className="section-subtitle">
                {metrics.notifications.total_received} received · 
                {metrics.notifications.total_processed} processed · 
                {metrics.notifications.avg_processing_time_ms && ` Avg ${formatDuration(metrics.notifications.avg_processing_time_ms)} · `}
                Success {formatNumber((metrics.notifications.success_rate || 0) * 100, 1)}%
              </span>
            </summary>
            {metrics.notifications.by_agent && Object.keys(metrics.notifications.by_agent).length > 0 && (
              <>
                <h4 className="subsection-title">By Agent</h4>
                <div className="breakdown-grid">
                  {Object.entries(metrics.notifications.by_agent).map(([agent, count]) => (
                    <div key={agent} className="breakdown-item">
                      <span className="breakdown-label">{agent}</span>
                      <span className="breakdown-value">{count}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            {metrics.notifications.by_type && Object.keys(metrics.notifications.by_type).length > 0 && (
              <>
                <h4 className="subsection-title">By Type</h4>
                <div className="breakdown-grid">
                  {Object.entries(metrics.notifications.by_type).map(([type, count]) => (
                    <div key={type} className="breakdown-item">
                      <span className="breakdown-label">{type}</span>
                      <span className="breakdown-value">{count}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </details>
        </div>
      )}

      {/* A2A Messages */}
      {metrics?.a2a_messages && (metrics.a2a_messages.total_sent > 0 || metrics?.a2a_transfers?.by_agent) && (
        <div className="metrics-section">
          <details open className="section-details">
            <summary className="section-summary">
              <h3>⇄ A2A Messages</h3>
              {metrics.a2a_messages.total_sent > 0 && (
                <span className="section-subtitle">
                  {metrics.a2a_messages.total_sent} sent · 
                  {metrics.a2a_messages.total_received} received · 
                  {metrics.a2a_messages.total_errors > 0 && ` ${metrics.a2a_messages.total_errors} errors · `}
                  {metrics.a2a_messages.avg_roundtrip_ms && ` Avg ${formatDuration(metrics.a2a_messages.avg_roundtrip_ms)} · `}
                  Success {formatNumber((metrics.a2a_messages.success_rate || 0) * 100, 1)}%
                </span>
              )}
            </summary>
            {metrics.a2a_messages.by_route && Object.keys(metrics.a2a_messages.by_route).length > 0 && (
              <>
                <h4 className="subsection-title">By Route</h4>
                <div className="breakdown-grid">
                  {Object.entries(metrics.a2a_messages.by_route).map(([route, count]) => (
                    <div key={route} className="breakdown-item">
                      <span className="breakdown-label">{route}</span>
                      <span className="breakdown-value">{count}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            {/* Fallback to old a2a_transfers if new metrics not available */}
            {(!metrics.a2a_messages.by_route || Object.keys(metrics.a2a_messages.by_route).length === 0) 
             && metrics?.a2a_transfers?.by_agent && Object.keys(metrics.a2a_transfers.by_agent).length > 0 && (
              <>
                <h4 className="subsection-title">By Agent</h4>
                <div className="breakdown-grid">
                  {Object.entries(metrics.a2a_transfers.by_agent).map(([agent, count]) => (
                    <div key={agent} className="breakdown-item">
                      <span className="breakdown-label">{agent}</span>
                      <span className="breakdown-value">{count}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </details>
        </div>
      )}

      {/* NPL Actions */}
      {metrics?.npl_calls?.by_action && Object.keys(metrics.npl_calls.by_action).length > 0 && (
        <div className="metrics-section">
          <details open className="section-details">
            <summary className="section-summary">
              <h3>◆ NPL Actions</h3>
            </summary>
            <div className="breakdown-grid">
              {Object.entries(metrics.npl_calls.by_action).map(([action, count]) => (
                <div key={action} className="breakdown-item">
                  <span className="breakdown-label">{action}</span>
                  <span className="breakdown-value">{count}</span>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}

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

