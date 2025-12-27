/**
 * Type-safe NPL API client generated from OpenAPI spec
 * 
 * This client provides full type safety for all NPL Engine operations
 * based on the commerce package protocols.
 */

import createClient from 'openapi-fetch';
import type { paths } from './types';

// Create type-safe client
const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_NPL_ENGINE_URL || 'http://localhost:12000',
});

// Configure authentication interceptor
export const setAuthToken = (token: string) => {
  client.use({
    onRequest({ request }) {
      request.headers.set('Authorization', `Bearer ${token}`);
      return request;
    },
  });
};

export default client;

