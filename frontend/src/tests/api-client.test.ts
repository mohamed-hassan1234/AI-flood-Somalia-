/**
 * API error normalisation and the session lifecycle.
 *
 * These run against the real client so the behaviour the UI depends on —
 * `error.kind`, retryability, the silent 401 refresh — is exercised end to end
 * rather than mocked away.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  apiRequest,
  clearTokens,
  getAccessToken,
  hasSession,
  onSessionExpired,
  storeTokens,
} from '../api/client';
import { shouldRetry } from '../api/queries';

/** `fetch` accepts a string, URL or Request; resolve each to a URL string. */
function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

beforeEach(() => {
  clearTokens();
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearTokens();
});

describe('error normalisation', () => {
  const cases: Array<[number, string]> = [
    [400, 'unknown'],
    [403, 'forbidden'],
    [404, 'not_found'],
    [409, 'conflict'],
    [422, 'validation'],
    [500, 'server'],
    [503, 'server'],
  ];

  it.each(cases)('maps HTTP %i to kind %s', async (status, kind) => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ detail: 'nope' }, status))));

    await expect(apiRequest('/anything')).rejects.toMatchObject({ kind, status });
  });

  it('reports a transport failure as a network error, not a server error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));

    const error = (await apiRequest('/anything').catch((caught: unknown) => caught)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.kind).toBe('network');
    expect(error.retryable).toBe(true);
  });

  it('surfaces a FastAPI string detail verbatim', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse({ detail: 'Missing capability: alerts.approve' }, 403)),
      ),
    );

    await expect(apiRequest('/x')).rejects.toThrow('Missing capability: alerts.approve');
  });

  it('flattens a 422 validation list into one readable sentence', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            {
              detail: [
                { loc: ['body', 'password'], msg: 'String should have at least 12 characters' },
              ],
            },
            422,
          ),
        ),
      ),
    );

    const error = (await apiRequest('/x').catch((caught: unknown) => caught)) as ApiError;
    expect(error.kind).toBe('validation');
    expect(error.message).toContain('password');
    expect(error.message).toContain('at least 12 characters');
  });

  it('falls back to a readable default when the body carries no detail', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({}, 500))));

    const error = (await apiRequest('/x').catch((caught: unknown) => caught)) as ApiError;
    expect(error.message).toMatch(/internal error/i);
    expect(error.message).not.toContain('undefined');
  });

  it('classifies access boundaries separately from faults', () => {
    const forbidden = new ApiError(403, 'forbidden', 'no');
    const server = new ApiError(500, 'server', 'boom');

    expect(forbidden.isAccessBoundary).toBe(true);
    expect(forbidden.retryable).toBe(false);
    expect(server.isAccessBoundary).toBe(false);
    expect(server.retryable).toBe(true);
  });
});

describe('retry policy', () => {
  it('never retries an access boundary or a validation failure', () => {
    expect(shouldRetry(0, new ApiError(403, 'forbidden', 'no'))).toBe(false);
    expect(shouldRetry(0, new ApiError(401, 'unauthorized', 'no'))).toBe(false);
    expect(shouldRetry(0, new ApiError(422, 'validation', 'no'))).toBe(false);
    expect(shouldRetry(0, new ApiError(404, 'not_found', 'no'))).toBe(false);
  });

  it('retries transient failures a bounded number of times', () => {
    const transient = new ApiError(0, 'network', 'offline');
    expect(shouldRetry(0, transient)).toBe(true);
    expect(shouldRetry(1, transient)).toBe(true);
    expect(shouldRetry(2, transient)).toBe(false);
  });
});

describe('session lifecycle', () => {
  it('attaches the bearer token to authenticated requests', async () => {
    storeTokens({
      access_token: 'token-abc',
      refresh_token: 'refresh-abc-long-enough-value-for-the-backend',
      token_type: 'bearer',
      expires_in: 900,
    });

    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      Promise.resolve(jsonResponse({ ok: true })),
    );
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/auth/me');

    const init = fetchMock.mock.calls[0][1];
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer token-abc');
  });

  it('omits the bearer token on an anonymous request', async () => {
    storeTokens({
      access_token: 'token-abc',
      refresh_token: 'refresh-abc-long-enough-value-for-the-backend',
      token_type: 'bearer',
      expires_in: 900,
    });

    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      Promise.resolve(jsonResponse({ ok: true })),
    );
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/auth/login', { method: 'POST', body: {}, anonymous: true });

    const init = fetchMock.mock.calls[0][1];
    expect((init?.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('refreshes once on 401 and replays the original request', async () => {
    storeTokens({
      access_token: 'stale-token',
      refresh_token: 'refresh-abc-long-enough-value-for-the-backend',
      token_type: 'bearer',
      expires_in: 900,
    });

    let attempt = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.includes('/auth/refresh')) {
        return Promise.resolve(
          jsonResponse({
            access_token: 'fresh-token',
            refresh_token: 'refresh-def-long-enough-value-for-the-backend',
            token_type: 'bearer',
            expires_in: 900,
          }),
        );
      }
      attempt += 1;
      return Promise.resolve(
        attempt === 1 ? jsonResponse({ detail: 'expired' }, 401) : jsonResponse({ ok: true }),
      );
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiRequest<{ ok: boolean }>('/risks')).resolves.toEqual({ ok: true });
    expect(getAccessToken()).toBe('fresh-token');
  });

  it('clears the session and notifies listeners when refresh fails', async () => {
    storeTokens({
      access_token: 'stale-token',
      refresh_token: 'refresh-abc-long-enough-value-for-the-backend',
      token_type: 'bearer',
      expires_in: 900,
    });

    const listener = vi.fn();
    const unsubscribe = onSessionExpired(listener);

    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ detail: 'expired' }, 401))),
    );

    await expect(apiRequest('/risks')).rejects.toMatchObject({ kind: 'unauthorized' });

    expect(listener).toHaveBeenCalledOnce();
    expect(hasSession()).toBe(false);
    unsubscribe();
  });
});

describe('query serialisation', () => {
  it('drops undefined, null and empty query parameters', async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      Promise.resolve(jsonResponse([])),
    );
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/risks', {
      query: { domain: 'drought', admin_unit_id: undefined, limit: 100, unused: '' },
    });

    const url = requestUrl(fetchMock.mock.calls[0][0]);
    expect(url).toContain('domain=drought');
    expect(url).toContain('limit=100');
    expect(url).not.toContain('admin_unit_id');
    expect(url).not.toContain('unused');
  });
});
