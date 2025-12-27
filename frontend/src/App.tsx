/**
 * Main App with Keycloak Authentication
 * 
 * Wraps the application in Keycloak provider for authentication.
 */

import { ReactKeycloakProvider } from '@react-keycloak/web';
import keycloak from './keycloak';
import { ThemeProvider } from './contexts/ThemeContext';
import ApprovalDashboard from './components/ApprovalDashboard';
import './App.css';

function App() {
  return (
    <ThemeProvider>
      <ReactKeycloakProvider
        authClient={keycloak}
        initOptions={{
          onLoad: 'check-sso', // Changed from 'login-required' to allow login button
          checkLoginIframe: false,
        }}
        LoadingComponent={<div style={{ padding: '20px' }}>Authenticating...</div>}
      >
        <ApprovalDashboard />
      </ReactKeycloakProvider>
    </ThemeProvider>
  );
}

export default App;
