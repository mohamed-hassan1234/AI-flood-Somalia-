const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';
export type TokenResponse = { access_token: string; refresh_token: string; token_type: 'bearer'; expires_in: number };
export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem('somalia-ai-access-token');
  const response = await fetch(`${API_URL}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } });
  if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: string } | null; throw new ApiError(response.status, body?.detail ?? `Request failed (${response.status})`); }
  return response.json() as Promise<T>;
}
export async function login(email: string, password: string): Promise<void> {
  const tokens = await apiRequest<TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
  sessionStorage.setItem('somalia-ai-access-token', tokens.access_token);
  sessionStorage.setItem('somalia-ai-refresh-token', tokens.refresh_token);
}
