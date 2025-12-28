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

