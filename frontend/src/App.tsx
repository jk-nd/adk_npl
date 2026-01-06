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

/**
 * Main App with Keycloak Authentication
 * 
 * Wraps the application in Keycloak provider for authentication.
 */

import { ReactKeycloakProvider } from '@react-keycloak/web';
import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import keycloak from './keycloak';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { usePendingApprovals } from './hooks/usePendingApprovals';
import ApprovalDashboard from './components/ApprovalDashboard';
import { ActivityLog } from './components/ActivityLog';
import { MetricsDashboard } from './components/MetricsDashboard';
import { BuyerChat } from './components/BuyerChat';
import { SupplierChat } from './components/SupplierChat';
import './App.css';

type Tab = 'approvals' | 'buyer' | 'supplier' | 'activity' | 'metrics';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 2000, // Auto-refresh every 2 seconds
      staleTime: 1000,
    },
  },
});

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      className="theme-toggle"
      onClick={toggleTheme}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      {theme === 'dark' ? '☀' : '☽'}
    </button>
  );
}

function RestartButton() {
  const [isRestarting, setIsRestarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const handleRestart = async () => {
    if (window.confirm('Complete restart? This will reload agents, refetch OpenAPI specs, and clear all history.')) {
      setIsRestarting(true);
      setError(null);
      
      try {
        const response = await fetch('http://localhost:8001/restart-session', { 
          method: 'POST',
          signal: AbortSignal.timeout(5000) // 5 second timeout
        });
        
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        
        // Server is restarting - wait and reload
        setTimeout(() => {
          window.location.reload();
        }, 8000);
      } catch (e: any) {
        // Network error is expected when server restarts
        if (e.name === 'AbortError' || e.message?.includes('fetch')) {
          // Server is restarting - this is expected
          setTimeout(() => {
            window.location.reload();
          }, 8000);
        } else {
          // Unexpected error
          setError('Restart failed. Please check the server logs.');
          setIsRestarting(false);
          setTimeout(() => setError(null), 5000);
        }
      }
    }
  };
  
  return (
    <div style={{ position: 'relative' }}>
      <button
        className="restart-button"
        onClick={handleRestart}
        disabled={isRestarting}
        title="Complete restart (reload agents & OpenAPI)"
      >
        {isRestarting ? '...' : '↻'}
      </button>
      {error && (
        <div style={{
          position: 'absolute',
          top: '100%',
          right: 0,
          marginTop: '4px',
          padding: '4px 8px',
          background: '#ef4444',
          color: 'white',
          borderRadius: '4px',
          fontSize: '12px',
          whiteSpace: 'nowrap',
          zIndex: 1000
        }}>
          {error}
        </div>
      )}
    </div>
  );
}

function ShutdownButton() {
  const [isShuttingDown, setIsShuttingDown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const handleShutdown = async () => {
    if (window.confirm('Are you sure you want to stop the demo? The server will shut down.')) {
      setIsShuttingDown(true);
      setError(null);
      
      try {
        const response = await fetch('http://localhost:8001/shutdown', { 
          method: 'POST',
          signal: AbortSignal.timeout(5000)
        });
        
        if (!response.ok) {
          throw new Error(`Server returned ${response.status}`);
        }
        
        // Server is shutting down - show message
        alert('Server is shutting down. The demo will stop.');
      } catch (e: any) {
        // Network error is expected when server shuts down
        if (e.name === 'AbortError' || e.message?.includes('fetch')) {
          // Server shut down - this is expected
          alert('Server is shutting down. The demo has stopped.');
        } else {
          // Unexpected error
          setError('Shutdown failed. Please check the server logs.');
          setIsShuttingDown(false);
          setTimeout(() => setError(null), 5000);
        }
      }
    }
  };
  
  return (
    <div style={{ position: 'relative' }}>
      <button
        className="shutdown-button"
        onClick={handleShutdown}
        disabled={isShuttingDown}
        title="Stop the demo"
      >
        {isShuttingDown ? '...' : '⏹'}
      </button>
      {error && (
        <div style={{
          position: 'absolute',
          top: '100%',
          right: 0,
          marginTop: '4px',
          padding: '4px 8px',
          background: '#ef4444',
          color: 'white',
          borderRadius: '4px',
          fontSize: '12px',
          whiteSpace: 'nowrap',
          zIndex: 1000
        }}>
          {error}
        </div>
      )}
    </div>
  );
}

function TabNavigation() {
  const [activeTab, setActiveTab] = useState<Tab>('buyer');
  const { hasPending, pendingCount } = usePendingApprovals(3000);

  return (
    <div className="app-container">
      <nav className="app-tabs">
        <div className="tab-buttons">
          <button
            className={`tab-button ${activeTab === 'buyer' ? 'active' : ''}`}
            onClick={() => setActiveTab('buyer')}
          >
            <span className="tab-icon">🛒</span>
            <span className="tab-label">Buyer</span>
          </button>
          <button
            className={`tab-button ${activeTab === 'supplier' ? 'active' : ''}`}
            onClick={() => setActiveTab('supplier')}
          >
            <span className="tab-icon">📦</span>
            <span className="tab-label">Supplier</span>
          </button>
          <button
            className={`tab-button ${activeTab === 'approvals' ? 'active' : ''}`}
            onClick={() => setActiveTab('approvals')}
          >
            <span className="tab-icon icon-check">✓</span>
            <span className="tab-label">Approvals</span>
            {hasPending && <span className="tab-badge">{pendingCount}</span>}
          </button>
          <button
            className={`tab-button ${activeTab === 'activity' ? 'active' : ''}`}
            onClick={() => setActiveTab('activity')}
          >
            <span className="tab-icon icon-pulse">●</span>
            <span className="tab-label">Activity</span>
          </button>
          <button
            className={`tab-button ${activeTab === 'metrics' ? 'active' : ''}`}
            onClick={() => setActiveTab('metrics')}
          >
            <span className="tab-icon icon-chart">▪</span>
            <span className="tab-label">Metrics</span>
          </button>
        </div>
        <div className="nav-controls">
          <RestartButton />
          <ThemeToggle />
          <ShutdownButton />
        </div>
      </nav>
      <div className="tab-content">
        {activeTab === 'buyer' && <BuyerChat />}
        {activeTab === 'supplier' && <SupplierChat />}
        {activeTab === 'approvals' && <ApprovalDashboard />}
        {activeTab === 'activity' && <ActivityLog />}
        {activeTab === 'metrics' && <MetricsDashboard />}
      </div>
    </div>
  );
}

function AppContent() {
  return (
    <ReactKeycloakProvider
      authClient={keycloak}
      initOptions={{
        onLoad: 'check-sso',
        checkLoginIframe: false,
      }}
      LoadingComponent={<div style={{ padding: '20px' }}>Authenticating...</div>}
    >
      <TabNavigation />
    </ReactKeycloakProvider>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AppContent />
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
