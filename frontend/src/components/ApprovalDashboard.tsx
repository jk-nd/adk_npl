/**
 * NPL Approval Dashboard
 * 
 * Displays PurchaseOrders in ApprovalRequired state and allows approval.
 * Uses type-safe generated NPL clients.
 */

import { useState, useEffect } from 'react';
import { useKeycloak } from '@react-keycloak/web';
import { useTheme } from '../contexts/ThemeContext';
import client, { setAuthToken } from '../clients/commerce/client';
import type { components } from '../clients/commerce/types';
import './ApprovalDashboard.css';

type PurchaseOrder = components['schemas']['PurchaseOrder'];

export default function ApprovalDashboard() {
  const { keycloak, initialized } = useKeycloak();
  const { theme, toggleTheme } = useTheme();
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialized && keycloak.authenticated && keycloak.token) {
      setAuthToken(keycloak.token);
      loadOrders();
    } else if (initialized && !keycloak.authenticated) {
      setAuthToken(null);
      setError('Not authenticated. Please log in.');
      setLoading(false);
    }
  }, [keycloak.token, keycloak.authenticated, initialized]);

  const loadOrders = async () => {
    try {
      setLoading(true);
      
      const { data, error } = await client.GET('/npl/commerce/PurchaseOrder/', {
        params: {
          query: {
            state: ['ApprovalRequired'],
            page: 1,
            pageSize: 50,
          },
        },
      });

      if (error) {
        setError((error as any)?.message ? String((error as any).message) : `Failed to load orders`);
        return;
      }

      setOrders(data?.items || []);
    } catch (err) {
      setError(`Error: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (orderId: string) => {
    try {
      const { error } = await client.POST('/npl/commerce/PurchaseOrder/{id}/approve', {
        params: {
          path: { id: orderId },
        },
        headers: {
          'X-Party': 'approver',
        },
      });

      if (error) {
        alert(`Failed to approve: ${JSON.stringify(error)}`);
        return;
      }

      // Reload orders after approval
      await loadOrders();
    } catch (err) {
      alert(`Error: ${err}`);
    }
  };

  if (loading) {
    return (
      <div className="agent-shell">
        <div className="agent-container">
          <header className="agent-header">
            <div className="agent-brand">
              <div className="agent-logo">NPL</div>
              <div>
                <div className="agent-title">Approval Dashboard</div>
                <div className="agent-subtitle">Human-in-the-loop governance for agent actions</div>
              </div>
            </div>
            <div className="agent-headerRight">
              <div className="agent-pill agent-pill--info">Loading…</div>
              <button 
                className="agent-btn agent-btn--ghost agent-btn--icon" 
                onClick={toggleTheme}
                title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              >
                {theme === 'dark' ? (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="8" cy="8" r="3"/>
                    <path d="M8 1v2M8 13v2M3 8H1M15 8h-2M2.343 2.343l1.414 1.414M12.243 12.243l1.414 1.414M2.343 13.657l1.414-1.414M12.243 3.757l1.414-1.414"/>
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M8 1a7 7 0 1 0 0 14M8 4V1M8 15v-3M4 8H1M15 8h-3M2.343 2.343l2.121 2.121M11.536 11.536l2.121 2.121M2.343 13.657l2.121-2.121M11.536 4.464l2.121-2.121"/>
                  </svg>
                )}
              </button>
            </div>
          </header>

          <div className="agent-panel">
            <div className="agent-panelHeader">
              <div className="agent-panelTitle">Pending approvals</div>
            </div>
            <div className="agent-skeletonList">
              <div className="agent-skeletonCard" />
              <div className="agent-skeletonCard" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!keycloak.authenticated) {
    return (
      <div className="agent-shell">
        <div className="agent-container">
          <header className="agent-header">
            <div className="agent-brand">
              <div className="agent-logo">NPL</div>
              <div>
                <div className="agent-title">Approval Dashboard</div>
                <div className="agent-subtitle">Human-in-the-loop governance for agent actions</div>
              </div>
            </div>
            <div className="agent-headerRight">
              <button 
                className="agent-btn agent-btn--primary" 
                onClick={() => keycloak.login()}
              >
                Login
              </button>
              <button 
                className="agent-btn agent-btn--ghost agent-btn--icon" 
                onClick={toggleTheme}
                title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              >
                {theme === 'dark' ? (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="8" cy="8" r="3"/>
                    <path d="M8 1v2M8 13v2M3 8H1M15 8h-2M2.343 2.343l1.414 1.414M12.243 12.243l1.414 1.414M2.343 13.657l1.414-1.414M12.243 3.757l1.414-1.414"/>
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M8 1a7 7 0 1 0 0 14M8 4V1M8 15v-3M4 8H1M15 8h-3M2.343 2.343l2.121 2.121M11.536 11.536l2.121 2.121M2.343 13.657l2.121-2.121M11.536 4.464l2.121-2.121"/>
                  </svg>
                )}
              </button>
            </div>
          </header>
          <div className="agent-callout agent-callout--info">
            <div className="agent-calloutTitle">Authentication Required</div>
            <div className="agent-calloutBody">
              Please log in to access the approval dashboard. You'll need approver credentials to review and approve purchase orders.
            </div>
            <button className="agent-btn agent-btn--primary" onClick={() => keycloak.login()}>
              Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="agent-shell">
        <div className="agent-container">
          <header className="agent-header">
            <div className="agent-brand">
              <div className="agent-logo">NPL</div>
              <div>
                <div className="agent-title">Approval Dashboard</div>
                <div className="agent-subtitle">Human-in-the-loop governance for agent actions</div>
              </div>
            </div>
            <div className="agent-headerRight">
              <div className="agent-pill agent-pill--danger">Error</div>
              <button 
                className="agent-btn agent-btn--ghost agent-btn--icon" 
                onClick={toggleTheme}
                title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              >
                {theme === 'dark' ? (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="8" cy="8" r="3"/>
                    <path d="M8 1v2M8 13v2M3 8H1M15 8h-2M2.343 2.343l1.414 1.414M12.243 12.243l1.414 1.414M2.343 13.657l1.414-1.414M12.243 3.757l1.414-1.414"/>
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M8 1a7 7 0 1 0 0 14M8 4V1M8 15v-3M4 8H1M15 8h-3M2.343 2.343l2.121 2.121M11.536 11.536l2.121 2.121M2.343 13.657l2.121-2.121M11.536 4.464l2.121-2.121"/>
                  </svg>
                )}
              </button>
            </div>
          </header>
          <div className="agent-callout agent-callout--danger">
            <div className="agent-calloutTitle">Failed to load</div>
            <div className="agent-calloutBody">{error}</div>
            <button className="agent-btn agent-btn--secondary" onClick={loadOrders}>Retry</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-shell">
      <div className="agent-container">
        <header className="agent-header">
          <div className="agent-brand">
            <div className="agent-logo">NPL</div>
            <div>
              <div className="agent-title">Approval Dashboard</div>
              <div className="agent-subtitle">Human-in-the-loop governance for agent actions</div>
            </div>
          </div>

          <div className="agent-headerRight">
            {keycloak.authenticated ? (
              <>
                <div className="agent-meta">
                  <span className="agent-metaLabel">User</span>
                  <span className="agent-mono">{keycloak.tokenParsed?.preferred_username || 'N/A'}</span>
                </div>
                <div className="agent-pill agent-pill--success">Authenticated</div>
                <button 
                  className="agent-btn agent-btn--ghost agent-btn--icon" 
                  onClick={() => keycloak.logout()}
                  title="Logout"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M6 14H3a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h3M10 12l4-4-4-4M14 8H6"/>
                  </svg>
                </button>
              </>
            ) : (
              <button 
                className="agent-btn agent-btn--primary" 
                onClick={() => keycloak.login()}
              >
                Login
              </button>
            )}
            <button 
              className="agent-btn agent-btn--ghost agent-btn--icon" 
              onClick={toggleTheme}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {theme === 'dark' ? (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="8" cy="8" r="3"/>
                  <path d="M8 1v2M8 13v2M3 8H1M15 8h-2M2.343 2.343l1.414 1.414M12.243 12.243l1.414 1.414M2.343 13.657l1.414-1.414M12.243 3.757l1.414-1.414"/>
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M8 1a7 7 0 1 0 0 14M8 4V1M8 15v-3M4 8H1M15 8h-3M2.343 2.343l2.121 2.121M11.536 11.536l2.121 2.121M2.343 13.657l2.121-2.121M11.536 4.464l2.121-2.121"/>
                </svg>
              )}
            </button>
          </div>
        </header>

        <div className="agent-panel">
          <div className="agent-panelHeader">
            <div className="agent-panelTitle">Pending approvals</div>
            <div className="agent-pill agent-pill--warning">{orders.length}</div>
          </div>

          {orders.length === 0 ? (
            <div className="agent-empty">
              <div className="agent-emptyTitle">All clear</div>
              <div className="agent-emptyBody">No purchase orders currently require approval.</div>
              <button className="agent-btn agent-btn--secondary" onClick={loadOrders}>Refresh</button>
            </div>
          ) : (
            <div className="agent-grid">
              {orders.map((order) => (
                <div key={order['@id']} className="agent-card">
                  <div className="agent-cardHeader">
                    <div>
                      <div className="agent-cardTitle">PO {order.orderNumber || order['@id']}</div>
                      <div className="agent-cardSub">
                        <span className="agent-badge agent-badge--warning">{order['@state'] || 'ApprovalRequired'}</span>
                        {order.quoteSubmittedAt ? (
                          <span className="agent-muted">Quoted {new Date(order.quoteSubmittedAt).toLocaleString()}</span>
                        ) : (
                          <span className="agent-muted">Awaiting approval</span>
                        )}
                      </div>
                    </div>

                    <div className="agent-amount">
                      <div className="agent-amountLabel">Total</div>
                      <div className="agent-amountValue">${order.total?.toLocaleString() ?? '—'}</div>
                    </div>
                  </div>

                  <div className="agent-kv">
                    <div className="agent-k">Quantity</div>
                    <div className="agent-v">{order.quantity ?? '—'} units</div>
                    <div className="agent-k">Unit price</div>
                    <div className="agent-v">${order.unitPrice ?? '—'}</div>
                  </div>

                  <div className="agent-cardFooter">
                    <button className="agent-btn agent-btn--ghost" onClick={loadOrders}>Refresh</button>
                    <button className="agent-btn agent-btn--primary" onClick={() => handleApprove(order['@id']!)}>
                      Approve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="agent-callout agent-callout--info">
          <div className="agent-calloutTitle">Why this is safe</div>
          <div className="agent-calloutBody">
            Agents can propose actions, but NPL enforces state + authorization. High-value orders pause here until a human approves.
          </div>
        </div>
      </div>
    </div>
  );
}

