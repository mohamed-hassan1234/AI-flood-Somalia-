/**
 * Application-wide providers, composed in dependency order:
 * query client → router → i18n → auth (which reads from the query client).
 */

import { useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import { I18nProvider } from '../../i18n';
import { AuthProvider } from './AuthProvider';
import { shouldRetry } from '../../api/queries';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        // Operational data changes on a scheduled cadence, not continuously.
        // Refetching on every window focus would add load without adding
        // information, so it is disabled in favour of explicit staleTime.
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
      mutations: { retry: false },
    },
  });
}

export function AppProviders({ children }: { children: ReactNode }) {
  // Created once per application instance rather than per render.
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <I18nProvider>
          <AuthProvider>{children}</AuthProvider>
        </I18nProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
