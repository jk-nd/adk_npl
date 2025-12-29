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
import './App.css';

type Tab = 'approvals' | 'activity' | 'metrics';

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

function TabNavigation() {
  const [activeTab, setActiveTab] = useState<Tab>('approvals');
  const { hasPending, pendingCount } = usePendingApprovals(3000);

  return (
    <div className="app-container">
      <nav className="app-tabs">
        <div className="tab-buttons">
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
        <ThemeToggle />
      </nav>
      <div className="tab-content">
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
