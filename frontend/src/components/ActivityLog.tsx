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
  buyer_agent: '#3b82f6',  // blue
  supplier_agent: '#10b981', // green
  approver: '#f59e0b', // amber
  npl_engine: '#8b5cf6', // purple
  adk_npl_bridge: '#ec4899', // pink
  keycloak: '#6366f1', // indigo
  system: '#64748b', // slate
};

const eventTypeIcons: Record<string, { icon: string; class: string }> = {
  agent_action: { icon: '◉', class: 'icon-agent' },
  agent_reasoning: { icon: '◐', class: 'icon-reasoning' },
  agent_message: { icon: '◈', class: 'icon-message' },
  npl_api: { icon: '◆', class: 'icon-api' },
  state_transition: { icon: '→', class: 'icon-transition' },
  authentication: { icon: '●', class: 'icon-auth' },
  bridge_operation: { icon: '▪', class: 'icon-bridge' },
  demo: { icon: '▸', class: 'icon-demo' },
  llm_call: { icon: '◎', class: 'icon-llm' },
  // A2A events
  a2a_message: { icon: '↔', class: 'icon-a2a-message' },
  // Agent internal events
  agent_thinking: { icon: '💭', class: 'icon-thinking' },
  // Human approval events
  approval_required: { icon: '⚠️', class: 'icon-approval' },
};

// Verbose event types that can be toggled (A2A details and agent thinking)
const A2A_VERBOSE_TYPES = ['a2a_message', 'agent_thinking'];

// All available event types organized by category (only actively used types)
const EVENT_TYPE_CATEGORIES = {
  'Agent Activity': ['agent_action', 'agent_reasoning', 'agent_message', 'agent_thinking'],
  'A2A Communication': ['a2a_message'],
  'NPL Engine': ['npl_api', 'state_transition', 'bridge_operation'],
  'System': ['llm_call', 'authentication'],
  'Human Actions': ['approval_required']
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  agent_action: 'Agent Actions',
  agent_reasoning: 'Agent Reasoning', 
  agent_message: 'Agent Messages',
  agent_thinking: 'Agent Thinking',
  a2a_message: 'A2A Messages',
  npl_api: 'NPL API Calls',
  state_transition: 'State Transitions',
  bridge_operation: 'Bridge Operations',
  llm_call: 'LLM Calls',
  authentication: 'Authentication',
  approval_required: 'Approval Required'
};

export function ActivityLog() {
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set(['all']));
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showA2ADetails, setShowA2ADetails] = useState(true);
  const [filterOpen, setFilterOpen] = useState(false);

  const isAllSelected = selectedTypes.has('all');

  const toggleType = (type: string) => {
    const newSelected = new Set(selectedTypes);
    if (type === 'all') {
      // Toggle "all" - if selected, clear everything; if not, select all
      if (isAllSelected) {
        newSelected.clear();
      } else {
        newSelected.clear();
        newSelected.add('all');
      }
    } else {
      // Toggle specific type
      newSelected.delete('all'); // Remove "all" when selecting specific types
      if (newSelected.has(type)) {
        newSelected.delete(type);
      } else {
        newSelected.add(type);
      }
      // If nothing selected, default to "all"
      if (newSelected.size === 0) {
        newSelected.add('all');
      }
    }
    setSelectedTypes(newSelected);
  };

  const getFilterLabel = () => {
    if (isAllSelected) return 'All Events';
    if (selectedTypes.size === 1) return EVENT_TYPE_LABELS[Array.from(selectedTypes)[0]] || 'Filter';
    return `${selectedTypes.size} types`;
  };

  // Fetch recent activity (always fetch all, filter client-side for multi-select)
  const { data: events, refetch } = useQuery<ActivityEvent[]>({
    queryKey: ['activity', 'recent'],
    queryFn: async () => {
      const response = await fetch(`${ACTIVITY_API_URL}/api/activity/logs?limit=200`);
      if (!response.ok) throw new Error('Failed to fetch activity');
      return response.json();
    },
    refetchInterval: autoRefresh ? 2000 : false,
  });

  // Filter events based on selected types
  const filteredEvents = events?.filter(event => {
    if (isAllSelected) return true;
    return selectedTypes.has(event.event_type);
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
          <span className="event-count">{filteredEvents?.length || 0} events</span>
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
          <label className="a2a-toggle" title="Show detailed A2A messages and agent thinking">
            <input
              type="checkbox"
              checked={showA2ADetails}
              onChange={(e) => setShowA2ADetails(e.target.checked)}
            />
            <span>Verbose</span>
          </label>
          <div className="filter-dropdown-container">
            <button 
              className="filter-dropdown-btn" 
              onClick={() => setFilterOpen(!filterOpen)}
            >
              {getFilterLabel()} ▾
            </button>
            {filterOpen && (
              <div className="filter-dropdown-menu">
                <label className="filter-option all-option">
                  <input 
                    type="checkbox" 
                    checked={isAllSelected}
                    onChange={() => toggleType('all')}
                  />
                  <span>All Events</span>
                </label>
                <div className="filter-divider" />
                {Object.entries(EVENT_TYPE_CATEGORIES).map(([category, types]) => (
                  <div key={category} className="filter-category">
                    <div className="filter-category-label">{category}</div>
                    {types.map(type => (
                      <label key={type} className="filter-option">
                        <input 
                          type="checkbox" 
                          checked={isAllSelected || selectedTypes.has(type)}
                          onChange={() => toggleType(type)}
                        />
                        <span>{EVENT_TYPE_LABELS[type]}</span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
          <button className="refresh-btn" onClick={() => refetch()} title="Refresh">
            ↻
          </button>
        </div>
      </div>

      {/* Compact Event Table */}
      <div className="activity-table" onClick={() => filterOpen && setFilterOpen(false)}>
        {!filteredEvents || filteredEvents.length === 0 ? (
          <div className="no-events">No activity events yet. Run the demo script to see logs.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th className="col-time">Time</th>
                <th className="col-type">Type</th>
                <th className="col-actor">Actor</th>
                <th className="col-action">Action</th>
                <th className="col-expand"></th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents
                .filter(event => showA2ADetails || !A2A_VERBOSE_TYPES.includes(event.event_type))
                .map((event, index) => {
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
                    ) : (
                      event.action
                    )}
                  </td>
                  <td className="col-expand">
                    {Object.keys(event.details).length > 0 && (
                      <details className="event-details-inline">
                        <summary className="details-icon">⋯</summary>
                        <div className="details-popup">
                          <pre>{JSON.stringify(event.details, null, 2)}</pre>
                        </div>
                      </details>
                    )}
                  </td>
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

