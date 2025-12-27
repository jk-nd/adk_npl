/**
 * Main App with Keycloak Authentication
 * 
 * Wraps the application in Keycloak provider for authentication.
 */

import { ReactKeycloakProvider } from '@react-keycloak/web';
import keycloak from './keycloak';
import ApprovalDashboard from './components/ApprovalDashboard';
import './App.css';

function App() {
  return (
    <ReactKeycloakProvider authClient={keycloak}>
      <ApprovalDashboard />
    </ReactKeycloakProvider>
  );
}

export default App;
