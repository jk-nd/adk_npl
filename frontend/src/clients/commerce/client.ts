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
 * Type-safe NPL API client generated from OpenAPI spec
 * 
 * This client provides full type safety for all NPL Engine operations
 * based on the commerce package protocols.
 */

import createClient from 'openapi-fetch';
import type { paths } from './types';

// Store the token
let authToken: string | null = null;

// Create type-safe client with auth middleware
// Use empty baseUrl to leverage Vite's proxy configuration
const client = createClient<paths>({
  baseUrl: '',
});

// Set up auth middleware that uses the stored token
client.use({
  onRequest({ request }) {
    if (authToken) {
      request.headers.set('Authorization', `Bearer ${authToken}`);
    }
    return request;
  },
});

// Configure authentication token
export const setAuthToken = (token: string | null) => {
  authToken = token;
};

export default client;

