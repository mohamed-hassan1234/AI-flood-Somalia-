/**
 * The single HTTP boundary between this application and the governed API.
 *
 * Nothing outside `src/api` should call `fetch`. Centralising it here gives
 * one place for base-URL resolution, bearer-token attachment, silent access
 * token refresh, and — most importantly — normalisation of every failure into
 * an `ApiError` whose `kind` the UI can branch on without inspecting status
 * codes at the call site.
 */

import type { TokenResponse } from '../types/api';

const DEFAULT_BASE_URL = 'http://localhost:8000/api/v1';

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? DEFAULT_BASE_URL;

/* --------------------------------------------------------- token storage -- */

/**
 * Tokens live in `sessionStorage`, matching the existing platform behaviour:
 * they are cleared when the tab closes and are not shared across tabs. This is
 * a deliberate trade-off for an internal operational console on shared
 * workstations. It does not defend against XSS — the backend remains the
 * authority on every request.
 */
const ACCESS_TOKEN_KEY = 'somalia-ai-access-token';
const REFRESH_TOKEN_KEY = 'somalia-ai-refresh-token';

function safeStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    // Storage can throw in hardened browser configurations. Treat as signed out.
    return null;
  }
}

export function getAccessToken(): string | null {
  return safeStorage()?.getItem(ACCESS_TOKEN_KEY) ?? null;
}

export function getRefreshToken(): string | null {
  return safeStorage()?.getItem(REFRESH_TOKEN_KEY) ?? null;
}

export function storeTokens(tokens: TokenResponse): void {
  const storage = safeStorage();
  if (!storage) return;
  storage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  const storage = safeStorage();
  if (!storage) return;
  storage.removeItem(ACCESS_TOKEN_KEY);
  storage.removeItem(REFRESH_TOKEN_KEY);
}

export function hasSession(): boolean {
  return getAccessToken() !== null;
}

/* ------------------------------------------------------------- api error -- */

/**
 * Normalised failure kinds. The UI branches on `kind`, never on raw status,
 * so that a new status code cannot silently fall through to a generic screen.
 */
export type ApiErrorKind =
  | 'network' // request never completed — offline, DNS, CORS, aborted
  | 'timeout' // request exceeded the client deadline
  | 'unauthorized' // 401 — no valid session
  | 'forbidden' // 403 — authenticated but not permitted
  | 'not_found' // 404
  | 'conflict' // 409 — invalid workflow transition, concurrent edit
  | 'validation' // 422 — request rejected by schema/business validation
  | 'server' // 5xx
  | 'unknown';

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  /** Raw parsed response body, when the server returned one. */
  readonly body: unknown;

  constructor(status: number, kind: ApiErrorKind, message: string, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.kind = kind;
    this.body = body;
  }

  /** True when re-issuing the same request could plausibly succeed. */
  get retryable(): boolean {
    return this.kind === 'network' || this.kind === 'timeout' || this.kind === 'server';
  }

  /** True when the failure is a permission boundary rather than a fault. */
  get isAccessBoundary(): boolean {
    return this.kind === 'unauthorized' || this.kind === 'forbidden';
  }
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 422) return 'validation';
  if (status >= 500) return 'server';
  return 'unknown';
}

/**
 * FastAPI returns `{"detail": ...}` where detail is either a string or, for
 * 422s, a list of per-field validation errors. Both shapes are reduced to one
 * operator-readable sentence.
 */
function messageFromBody(body: unknown, status: number): string {
  if (typeof body === 'string' && body.trim()) return body;

  if (body && typeof body === 'object' && 'detail' in body) {
    const { detail } = body;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const parts = detail
        .map((entry) => {
          if (entry && typeof entry === 'object') {
            const record = entry as { loc?: unknown; msg?: unknown };
            const field = Array.isArray(record.loc)
              ? record.loc.filter((part) => part !== 'body').join('.')
              : '';
            const msg = typeof record.msg === 'string' ? record.msg : 'is invalid';
            return field ? `${field}: ${msg}` : msg;
          }
          return null;
        })
        .filter((part): part is string => Boolean(part));
      if (parts.length) return parts.join('; ');
    }
  }

  return defaultMessage(status);
}

function defaultMessage(status: number): string {
  switch (kindForStatus(status)) {
    case 'unauthorized':
      return 'Your session is no longer valid. Sign in again to continue.';
    case 'forbidden':
      return 'Your role does not grant access to this information.';
    case 'not_found':
      return 'The requested record does not exist, or is outside your assigned geography.';
    case 'conflict':
      return 'This action conflicts with the record’s current state. Reload and try again.';
    case 'validation':
      return 'The request was rejected because it did not meet the required format.';
    case 'server':
      return 'The service encountered an internal error. This has not been recorded as your fault.';
    default:
      return `Request failed (${status}).`;
  }
}

/* -------------------------------------------------------- token refresh -- */

/**
 * Concurrent 401s must not each fire their own refresh. The first failure
 * starts a refresh and every other in-flight request awaits the same promise.
 */
let refreshInFlight: Promise<boolean> | null = null;

/** Notifies the auth layer that the session ended and the user must re-auth. */
type SessionExpiredListener = () => void;
const sessionExpiredListeners = new Set<SessionExpiredListener>();

export function onSessionExpired(listener: SessionExpiredListener): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

function announceSessionExpired(): void {
  clearTokens();
  for (const listener of sessionExpiredListeners) listener();
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) return false;
    const tokens = (await response.json()) as TokenResponse;
    if (!tokens?.access_token) return false;
    storeTokens(tokens);
    return true;
  } catch {
    return false;
  }
}

function ensureRefresh(): Promise<boolean> {
  refreshInFlight ??= refreshAccessToken().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/* ------------------------------------------------------------- requests -- */

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** Serialised as JSON. Omit for bodiless requests. */
  body?: unknown;
  /** Appended as a query string; `undefined` and `null` entries are dropped. */
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  /** Client-side deadline in milliseconds. */
  timeoutMs?: number;
  /** Skip the bearer token — used only by the login call. */
  anonymous?: boolean;
}

const DEFAULT_TIMEOUT_MS = 20_000;

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${API_BASE_URL}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    params.append(key, String(value));
  }
  const search = params.toString();
  return search ? `${url}?${search}` : url;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') ?? '';
  try {
    if (contentType.includes('application/json')) return await response.json();
    const text = await response.text();
    return text || null;
  } catch {
    return null;
  }
}

async function execute(path: string, options: RequestOptions): Promise<Response> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timer = setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), timeoutMs);

  // Honour a caller-supplied signal alongside our own deadline.
  const abortFromCaller = () => controller.abort(options.signal?.reason);
  options.signal?.addEventListener('abort', abortFromCaller);

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (!options.anonymous) {
    const token = getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  try {
    return await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
}

/**
 * Issues a request and returns the decoded body, or throws an `ApiError`.
 *
 * On a 401 with a stored refresh token the request is retried exactly once
 * after a silent refresh; if that fails the session is cleared and listeners
 * are notified so the router can route to sign-in.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response;

  try {
    response = await execute(path, options);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError(0, 'timeout', 'The service did not respond in time. Try again.');
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      // A caller-initiated cancellation, e.g. an unmounted component. Rethrow
      // so TanStack Query treats it as a cancellation, not a failure.
      throw error;
    }
    throw new ApiError(
      0,
      'network',
      'Cannot reach the platform service. Check your connection and try again.',
    );
  }

  if (response.status === 401 && !options.anonymous) {
    const refreshed = await ensureRefresh();
    if (refreshed) {
      try {
        response = await execute(path, options);
      } catch {
        throw new ApiError(0, 'network', 'Cannot reach the platform service after re-authenticating.');
      }
    }
    if (response.status === 401) {
      announceSessionExpired();
      throw new ApiError(401, 'unauthorized', defaultMessage(401));
    }
  }

  if (!response.ok) {
    const body = await parseBody(response);
    throw new ApiError(
      response.status,
      kindForStatus(response.status),
      messageFromBody(body, response.status),
      body,
    );
  }

  return (await parseBody(response)) as T;
}

/** Convenience wrapper for the common read path. */
export function apiGet<T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, { query, signal });
}

/** Convenience wrapper for state-changing calls. */
export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiRequest<T>(path, { method: 'POST', body });
}
