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
 * Keycloak configuration for NPL Approval Dashboard
 * 
 * Authenticates as the 'approver' user in the 'purchasing' realm
 */

import Keycloak from 'keycloak-js';

const rawKeycloakUrl = import.meta.env.VITE_KEYCLOAK_URL || 'http://keycloak:11000';
// Force browser to use 'keycloak:11000' so the JWT issuer matches ENGINE_ALLOWED_ISSUERS
// This requires /etc/hosts entry: 127.0.0.1 keycloak
// If localhost is configured, force it to keycloak so the issuer is consistent
const keycloakUrl = rawKeycloakUrl === 'http://localhost:11000' ? 'http://keycloak:11000' : rawKeycloakUrl;
const keycloakRealm = import.meta.env.VITE_KEYCLOAK_REALM || 'purchasing';
const keycloakClientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'purchasing';

const keycloak = new Keycloak({
  url: keycloakUrl,
  realm: keycloakRealm,
  clientId: keycloakClientId,
});

export default keycloak;

