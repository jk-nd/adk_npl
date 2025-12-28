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
};

export function ActivityLog() {
  const [filter, setFilter] = useState<'all' | string>('all');
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Fetch recent activity
  const { data: events, refetch } = useQuery<ActivityEvent[]>({
    queryKey: ['activity', 'recent', filter], // Include filter in query key to trigger refetch
    queryFn: async () => {
      const url = filter === 'all' 
        ? `${ACTIVITY_API_URL}/api/activity/logs?limit=200`
        : `${ACTIVITY_API_URL}/api/activity/by-type/${filter}?limit=200`;
      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to fetch activity');
      return response.json();
    },
    refetchInterval: autoRefresh ? 2000 : false, // Refresh every 2 seconds if enabled
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
          <select className="compact-filter" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All Events</option>
            <option value="agent_action">Agent Actions</option>
            <option value="agent_reasoning">Agent Reasoning</option>
            <option value="agent_message">Agent Messages</option>
            <option value="npl_api">API Calls</option>
            <option value="state_transition">State Transitions</option>
            <option value="authentication">Authentication</option>
            <option value="demo">Demo</option>
          </select>
          <button className="refresh-btn" onClick={() => refetch()} title="Refresh">
            ↻
          </button>
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
                <th className="col-action">Action</th>
                <th className="col-expand"></th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, index) => {
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
                      <span 
                        className="actor-badge"
                        style={{ backgroundColor: getActorColor(event.actor) }}
                      >
                        {event.actor}
                      </span>
                    </td>
                  <td className="col-action">
                    {event.event_type === 'agent_reasoning' && event.details?.reasoning ? (
                      <span className="reasoning-text">{event.details.reasoning}</span>
                    ) : event.event_type === 'agent_message' && event.details?.message ? (
                      <span className="message-text">
                        <strong>To {event.details.to}:</strong> {event.details.message}
                      </span>
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

