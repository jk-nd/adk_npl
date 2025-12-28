/**
 * Keycloak configuration for NPL Approval Dashboard
 * 
 * Authenticates as the 'approver' user in the 'purchasing' realm
 */

import Keycloak from 'keycloak-js';

const rawKeycloakUrl = import.meta.env.VITE_KEYCLOAK_URL || 'http://keycloak:11000';
// Some environments override this to localhost; force the browser to use the same hostname Docker can reach for JWKS.
const keycloakUrl = rawKeycloakUrl === 'http://localhost:11000' ? 'http://keycloak:11000' : rawKeycloakUrl;
const keycloakRealm = import.meta.env.VITE_KEYCLOAK_REALM || 'purchasing';
const keycloakClientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'purchasing';

const keycloak = new Keycloak({
  url: keycloakUrl,
  realm: keycloakRealm,
  clientId: keycloakClientId,
});

export default keycloak;

