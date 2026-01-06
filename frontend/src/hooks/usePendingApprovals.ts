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
 * Hook to check for pending approvals
 * 
 * Polls the NPL Engine for orders in ApprovalRequired state
 */

import { useEffect, useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';
import client, { setAuthToken } from '../clients/commerce/client';

export function usePendingApprovals(pollInterval: number = 3000) {
  const { keycloak, initialized } = useKeycloak();
  const [hasPending, setHasPending] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    let intervalId: number | null = null;

    const checkPendingApprovals = async () => {
      if (!initialized || !keycloak.authenticated || !keycloak.token) {
        setHasPending(false);
        setPendingCount(0);
        return;
      }

      try {
        setAuthToken(keycloak.token);
        
        const { data, error } = await client.GET('/npl/commerce/PurchaseOrder/', {
          params: {
            query: {
              state: ['ApprovalRequired'],
              page: 1,
              pageSize: 50,
            },
          },
        });

        if (!error && data?.items) {
          const count = data.items.length;
          setHasPending(count > 0);
          setPendingCount(count);
        } else {
          setHasPending(false);
          setPendingCount(0);
        }
      } catch (err) {
        // Silently handle errors (user might not be logged in)
        setHasPending(false);
        setPendingCount(0);
      }
    };

    // Check immediately
    checkPendingApprovals();

    // Then poll at interval
    intervalId = setInterval(checkPendingApprovals, pollInterval);

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [keycloak.token, keycloak.authenticated, initialized, pollInterval]);

  return { hasPending, pendingCount };
}

