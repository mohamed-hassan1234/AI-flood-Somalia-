/**
 * Test harness: renders a component inside the real provider stack with a
 * controllable fake for the HTTP boundary.
 *
 * `fetch` is stubbed rather than the API module, so the tests exercise the
 * genuine client — error normalisation, token attachment and the 401 refresh
 * path all run as they do in production.
 */

import type { ReactElement, ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render } from '@testing-library/react';
import { vi } from 'vitest';

import { AuthProvider } from '../app/providers/AuthProvider';
import { I18nProvider } from '../i18n';
import { clearTokens, storeTokens } from '../api/client';

/* ------------------------------------------------------------ fetch stub -- */

export interface RouteHandler {
  status?: number;
  /** JSON body, or a function computing one from the request. */
  body?: unknown;
  /** Simulates a transport failure rather than an HTTP error status. */
  networkError?: boolean;
}

/**
 * Maps a route key to its canned response.
 *
 * A key is either a path fragment (`/alerts`) or a method-qualified fragment
 * (`POST /alerts/{id}/transitions`). Method-qualified keys are matched first,
 * so a mutation can be stubbed separately from the read on the same path.
 */
export type RouteMap = Record<string, RouteHandler>;

export interface FetchStub {
  calls: string[];
  restore: () => void;
}

/** `fetch` accepts three input shapes; resolve each to a plain URL string. */
function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

export function stubFetch(routes: RouteMap): FetchStub {
  const calls: string[] = [];

  const implementation = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    calls.push(`${init?.method ?? 'GET'} ${url}`);

    const method = (init?.method ?? 'GET').toUpperCase();

    // Method-qualified keys win outright; otherwise the longest matching path
    // fragment wins, so `/alerts/{id}` beats `/alerts`.
    const qualified = Object.keys(routes)
      .filter((candidate) => candidate.includes(' '))
      .filter((candidate) => {
        const [candidateMethod, fragment] = candidate.split(/\s+/, 2);
        return candidateMethod.toUpperCase() === method && url.includes(fragment);
      })
      .sort((a, b) => b.length - a.length)[0];

    const key =
      qualified ??
      Object.keys(routes)
        .filter((candidate) => !candidate.includes(' '))
        .filter((candidate) => url.includes(candidate))
        .sort((a, b) => b.length - a.length)[0];

    if (!key) {
      return Promise.resolve(
        new Response(JSON.stringify({ detail: 'No stub for this route' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }

    const handler = routes[key];
    if (handler.networkError) {
      throw new TypeError('Failed to fetch');
    }

    const body =
      typeof handler.body === 'function'
        ? (handler.body as (request: { url: string; init?: RequestInit }) => unknown)({ url, init })
        : handler.body;

    return Promise.resolve(
      new Response(body === undefined ? null : JSON.stringify(body), {
        status: handler.status ?? 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });

  vi.stubGlobal('fetch', implementation);

  return {
    calls,
    restore: () => vi.unstubAllGlobals(),
  };
}

/* --------------------------------------------------------------- session -- */

export function signInForTest(): void {
  storeTokens({
    access_token: 'test-access-token',
    refresh_token: 'test-refresh-token-that-is-long-enough-for-validation',
    token_type: 'bearer',
    expires_in: 900,
  });
}

export function signOutForTest(): void {
  clearTokens();
}

/* ---------------------------------------------------------------- render -- */

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // Retries would make failure assertions slow and flaky; the retry policy
      // itself is tested directly against `shouldRetry`.
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

export interface RenderOptions {
  /** Initial history entries for the memory router. */
  route?: string;
  /** Route pattern, when the component reads path params. */
  path?: string;
  queryClient?: QueryClient;
}

export function renderWithProviders(
  ui: ReactElement,
  { route = '/', path, queryClient = createTestQueryClient() }: RenderOptions = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>
          <I18nProvider>
            <AuthProvider>
              {path ? (
                <Routes>
                  <Route path={path} element={children} />
                </Routes>
              ) : (
                children
              )}
            </AuthProvider>
          </I18nProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return { ...render(ui, { wrapper: Wrapper }), queryClient };
}
