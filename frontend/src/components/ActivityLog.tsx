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
import './ActivityLog.css';

interface ActivityEvent {
  timestamp: string;
  event_type: string;
  actor: string;
  action: string;
  level: string;
  details: Record<string, any>;
}

const ACTIVITY_API_URL = 'http://localhost:8002';

const actorColors: Record<string, string> = {
  buyer_agent: '#3b82f6',      // blue
  supplier_agent: '#06b6d4',   // cyan/teal (different from NPL Engine green)
  approver: '#f59e0b',         // amber
  'NPL Engine': '#8b5cf6',     // purple
  npl_engine: '#8b5cf6',       // purple (legacy)
  adk_npl_bridge: '#ec4899',   // pink
  keycloak: '#6366f1',         // indigo
  system: '#64748b',           // slate
};

const eventTypeIcons: Record<string, { icon: string; class: string }> = {
  agent_action: { icon: '◉', class: 'icon-agent' },
  agent_reasoning: { icon: '◐', class: 'icon-reasoning' },
  agent_message: { icon: '◈', class: 'icon-message' },
  agent_thinking: { icon: '💭', class: 'icon-thinking' },
  agent_tool_call: { icon: '⚙', class: 'icon-tool' },
  tool_call: { icon: '✓', class: 'icon-tool-complete' },
  npl_api: { icon: '◆', class: 'icon-api' },
  state_transition: { icon: '→', class: 'icon-transition' },
  authentication: { icon: '●', class: 'icon-auth' },
  bridge_operation: { icon: '▪', class: 'icon-bridge' },
  llm_call: { icon: '◎', class: 'icon-llm' },
  // A2A events
  a2a_message: { icon: '↔', class: 'icon-a2a-message' },
  a2a_transfer: { icon: '⇄', class: 'icon-a2a-transfer' },
  // Notifications
  notification_received: { icon: '🔔', class: 'icon-notification' },
  notification_processed: { icon: '✓', class: 'icon-notification-done' },
  // Human approval events
  approval_required: { icon: '⚠️', class: 'icon-approval' },
};


export function ActivityLog() {
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Fetch recent activity (show all events, no filtering)
  const { data: events } = useQuery<ActivityEvent[]>({
    queryKey: ['activity', 'recent'],
    queryFn: async () => {
      const response = await fetch(`${ACTIVITY_API_URL}/api/activity/logs?limit=200`);
      if (!response.ok) throw new Error('Failed to fetch activity');
      return response.json();
    },
    refetchInterval: autoRefresh ? 2000 : false,
  });

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { 
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3
    });
  };

  const getActorColor = (actor: string) => {
    return actorColors[actor] || '#94a3b8';
  };

  const getLevelClass = (level: string) => {
    switch (level) {
      case 'error': return 'log-level-error';
      case 'warning': return 'log-level-warning';
      default: return 'log-level-info';
    }
  };

  // For certain event types, show the target system instead of the actor
  const getDisplayActor = (event: ActivityEvent): { label: string; isTarget: boolean } => {
    switch (event.event_type) {
      case 'npl_api':
        return { label: 'NPL Engine', isTarget: true };
      case 'llm_call':
        return { label: 'LLM', isTarget: true };
      case 'authentication':
        return { label: 'Keycloak', isTarget: true };
      case 'bridge_operation':
        return { label: 'NPL Bridge', isTarget: true };
      case 'a2a_message':
        // For A2A messages, show "A2A" as the communication type
        return { label: 'A2A', isTarget: true };
      case 'approval_required':
        // For approval events, show "Human Approver" as the target
        return { label: 'Human Approver', isTarget: true };
      default:
        return { label: event.actor, isTarget: false };
    }
  };

  const getTargetColor = (label: string) => {
    switch (label) {
      case 'NPL Engine': return '#10b981';  // Green
      case 'LLM': return '#8b5cf6';          // Purple
      case 'Keycloak': return '#f59e0b';     // Amber
      case 'Human Approver': return '#ef4444'; // Red (urgent)
      case 'NPL Bridge': return '#06b6d4';   // Cyan
      case 'A2A': return '#f43f5e';          // Rose (agent-to-agent)
      default: return '#64748b';             // Slate
    }
  };

  return (
    <div className="activity-log-container">
      {/* Header */}
      <div className="activity-log-header">
        <div className="header-left">
          <h2>Activity Feed</h2>
          <span className="event-count">{events?.length || 0} events</span>
        </div>
        <div className="activity-log-controls">
          <label className="auto-refresh-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto</span>
          </label>
        </div>
      </div>

      {/* Compact Event Table */}
      <div className="activity-table">
        {!events || events.length === 0 ? (
          <div className="no-events">No activity events yet. Run the demo script to see logs.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="col-time">Time</th>
                <th className="col-type">Type</th>
                <th className="col-actor">Actor</th>
                <th className="col-action">Action / Result</th>
              </tr>
            </thead>
            <tbody>
              {events?.map((event, index) => {
                const iconInfo = eventTypeIcons[event.event_type] || { icon: '•', class: 'icon-default' };
                return (
                  <tr key={index} className={`event-row ${getLevelClass(event.level)}`}>
                    <td className="col-time">{formatTimestamp(event.timestamp)}</td>
                    <td className="col-type">
                      <span className={`type-badge ${iconInfo.class}`}>
                        {iconInfo.icon}
                      </span>
                    </td>
                    <td className="col-actor">
                      {(() => {
                        const displayActor = getDisplayActor(event);
                        return (
                          <span 
                            className={`actor-badge ${displayActor.isTarget ? 'target-badge' : ''}`}
                            style={{ 
                              backgroundColor: displayActor.isTarget 
                                ? getTargetColor(displayActor.label) 
                                : getActorColor(event.actor) 
                            }}
                            title={displayActor.isTarget ? `Called by: ${event.actor}` : undefined}
                          >
                            {displayActor.label}
                          </span>
                        );
                      })()}
                    </td>
                  <td className="col-action">
                    {event.event_type === 'agent_reasoning' && event.details?.reasoning ? (
                      <span className="reasoning-text">{event.details.reasoning}</span>
                    ) : event.event_type === 'agent_message' && event.details?.message ? (
                      <span className="message-text">
                        <strong>To {event.details.to}:</strong> {event.details.message}
                      </span>
                    ) : event.event_type === 'a2a_message' && event.details?.message_preview ? (
                      <details className="a2a-message-details">
                        <summary className="a2a-message-summary">
                          <strong>
                            {event.details.from_agent} → {event.details.to_agent}:
                          </strong> 
                          <span className="a2a-preview">{event.details.message_preview}</span>
                        </summary>
                        <div className="a2a-full-message">
                          {event.details.full_message || event.details.message_preview}
                        </div>
                      </details>
                    ) : event.event_type === 'agent_thinking' && event.details?.thinking_preview ? (
                      <details className="agent-thinking-details">
                        <summary className="agent-thinking-summary">
                          <span className="thinking-label">thinking</span>
                          <span className="thinking-preview">{event.details.thinking_preview}</span>
                        </summary>
                        <div className="thinking-full">
                          {event.details.full_thinking || event.details.thinking_preview}
                        </div>
                      </details>
                    ) : event.event_type === 'npl_api' && event.details?.endpoint ? (
                      <details className="npl-api-details">
                        <summary className="npl-api-summary">
                          <span className="api-caller-badge">{event.details.caller || 'unknown'}</span>
                          {event.details.status_code && (
                            <span className={`api-status-badge ${
                              event.details.status_code >= 200 && event.details.status_code < 300 
                                ? 'status-success' 
                                : event.details.status_code >= 400 
                                  ? 'status-error' 
                                  : 'status-other'
                            }`}>
                              {event.details.status_code >= 200 && event.details.status_code < 300 ? '✓' : '✗'} {event.details.status_code}
                            </span>
                          )}
                          <strong>{event.details.method || 'API'}</strong> {event.details.endpoint}
                          {event.details.response_time_ms && (
                            <span className="tool-latency">{Math.round(event.details.response_time_ms)}ms</span>
                          )}
                        </summary>
                        <div className="npl-api-body">
                          {event.details.request_body && (
                            <div className="api-section">
                              <strong>Request Body:</strong>
                              <pre>{JSON.stringify(event.details.request_body, null, 2)}</pre>
                            </div>
                          )}
                          {event.details.response_body && (
                            <div className="api-section">
                              <strong>Response Body:</strong>
                              <pre>{JSON.stringify(event.details.response_body, null, 2)}</pre>
                            </div>
                          )}
                          <div className="api-meta">
                            {event.details.response_time_ms && (
                              <span><strong>Time:</strong> {event.details.response_time_ms}ms</span>
                            )}
                          </div>
                        </div>
                      </details>
                    ) : event.event_type === 'tool_call' && event.details?.tool_name && event.details?.latency_ms !== undefined ? (
                      <details className="tool-result-details">
                        <summary className="tool-result-summary">
                          <span className={`tool-status ${event.details.success !== false ? 'success' : 'error'}`}>
                            {event.details.success !== false ? '✓' : '✗'}
                          </span>
                          <strong>{event.details.tool_name}</strong>
                          <span className="tool-latency">{event.details.latency_ms?.toFixed(0)}ms</span>
                          {event.details.protocol_id && (
                            <span className="tool-protocol-id">{event.details.protocol_id}</span>
                          )}
                          {event.details.state && (
                            <span className="tool-state">{event.details.state}</span>
                          )}
                          {event.details.count && (
                            <span className="tool-count">{event.details.count}</span>
                          )}
                          {event.details.error && (
                            <span className="tool-error">{event.details.error}</span>
                          )}
                        </summary>
                        <div className="tool-result-body">
                          {event.details.args && (
                            <div className="tool-args">
                              <strong>Args:</strong> <code>{event.details.args}</code>
                            </div>
                          )}
                          <pre>{event.details.result_preview || '(no result data)'}</pre>
                        </div>
                      </details>
                    ) : (
                      event.action
                    )}
                  </td>
                  {/* Removed the expand column - tool_result events now have inline expansion */}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

