/**
 * NPL Approval Dashboard
 * 
 * Displays PurchaseOrders in ApprovalRequired state and allows approval.
 * Uses type-safe generated NPL clients.
 */

import { useState, useEffect } from 'react';
import { useKeycloak } from '@react-keycloak/web';
import client, { setAuthToken } from '../clients/commerce/client';
import type { components } from '../clients/commerce/types';

type PurchaseOrder = components['schemas']['PurchaseOrder'];

export default function ApprovalDashboard() {
  const { keycloak } = useKeycloak();
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (keycloak.token) {
      setAuthToken(keycloak.token);
      loadOrders();
    }
  }, [keycloak.token]);

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
        setError(`Failed to load orders: ${JSON.stringify(error)}`);
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
    return <div style={{ padding: '20px' }}>Loading...</div>;
  }

  if (error) {
    return <div style={{ padding: '20px', color: 'red' }}>{error}</div>;
  }

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>🔐 NPL Approval Dashboard</h1>
      <p>Human-in-the-Loop AI Agent Governance with NPL</p>
      
      <div style={{ marginTop: '30px' }}>
        <h2>📋 Pending Approvals ({orders.length})</h2>
        
        {orders.length === 0 ? (
          <div style={{ 
            padding: '40px', 
            textAlign: 'center', 
            backgroundColor: '#f5f5f5',
            borderRadius: '8px'
          }}>
            <p>No pending orders requiring approval</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {orders.map((order) => (
              <div
                key={order['@id']}
                style={{
                  border: '2px solid #ff9800',
                  borderRadius: '8px',
                  padding: '20px',
                  backgroundColor: 'white',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                  <div style={{ flex: 1 }}>
                    <h3>Order #{order.orderNumber}</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 16px', marginTop: '12px' }}>
                      <strong>Total Amount:</strong>
                      <span style={{ color: '#d32f2f', fontSize: '18px', fontWeight: 'bold' }}>
                        ${order.total?.toLocaleString()}
                      </span>
                      
                      <strong>Quantity:</strong>
                      <span>{order.quantity} units @ ${order.unitPrice}/unit</span>
                      
                      <strong>State:</strong>
                      <span style={{ 
                        backgroundColor: '#ff9800', 
                        color: 'white', 
                        padding: '4px 8px',
                        borderRadius: '4px',
                        display: 'inline-block'
                      }}>
                        {order['@state']}
                      </span>
                      
                      {order.quoteSubmittedAt && (
                        <>
                          <strong>Quote Submitted:</strong>
                          <span>{new Date(order.quoteSubmittedAt).toLocaleString()}</span>
                        </>
                      )}
                    </div>
                  </div>
                  
                  <button
                    onClick={() => handleApprove(order['@id']!)}
                    style={{
                      backgroundColor: '#4caf50',
                      color: 'white',
                      border: 'none',
                      padding: '12px 24px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '16px',
                      fontWeight: 'bold',
                    }}
                  >
                    ✓ Approve
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ 
        marginTop: '40px', 
        padding: '20px', 
        backgroundColor: '#e3f2fd',
        borderRadius: '8px',
        borderLeft: '4px solid #2196f3'
      }}>
        <h3>Proof of Concept: How AI agents can participate in real business workflows while being safely governed by NPL</h3>
        <ul style={{ lineHeight: '1.8' }}>
          <li>✅ Agents initiate actions</li>
          <li>✅ NPL enforces policy</li>
          <li>✅ Human approval required</li>
          <li>✅ Complete audit trail</li>
        </ul>
      </div>
    </div>
  );
}

