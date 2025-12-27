/**
 * Keycloak configuration for NPL Approval Dashboard
 * 
 * Authenticates as the 'approver' user in the 'purchasing' realm
 */

import Keycloak from 'keycloak-js';

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:11000',
  realm: import.meta.env.VITE_KEYCLOAK_REALM || 'purchasing',
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'purchasing',
});

export default keycloak;

