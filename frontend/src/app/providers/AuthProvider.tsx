/**
 * Session and capability context.
 *
 * The backend is the sole authority on authorisation — this context exists so
 * the interface can avoid *offering* an action the caller cannot perform, and
 * can explain why something is unavailable. It is never a security boundary.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';

import {
  clearTokens,
  hasSession,
  onSessionExpired,
  storeTokens,
} from '../../api/client';
import { login as loginRequest } from '../../api/endpoints';
import { usePrincipal } from '../../api/queries';
import type { Principal } from '../../types/api';

export type SessionState =
  | 'anonymous' // no token stored
  | 'loading' // token present, principal being resolved
  | 'authenticated'
  | 'expired'; // token was rejected mid-session

export interface AuthContextValue {
  state: SessionState;
  principal: Principal | null;
  /** Capability set from `/auth/me`, as a set for O(1) checks. */
  capabilities: ReadonlySet<string>;
  /**
   * True when the principal holds the given capability.
   *
   * Accepts a plain string rather than only the `Capability` union so callers
   * can pass a value read from the API, which is not statically known. The
   * union is exported for authoring convenience, not as a constraint.
   */
  can: (capability: string) => boolean;
  /** True when the principal holds at least one of the given capabilities. */
  canAny: (...capabilities: string[]) => boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  /** Cleared once the user acknowledges the expiry by signing in again. */
  acknowledgeExpiry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [tokenPresent, setTokenPresent] = useState(hasSession);
  const [expired, setExpired] = useState(false);

  const principalQuery = usePrincipal(tokenPresent);

  // The API client emits this when a refresh attempt fails, which is the only
  // reliable signal that a session ended while the user was working.
  useEffect(
    () =>
      onSessionExpired(() => {
        setTokenPresent(false);
        setExpired(true);
        queryClient.clear();
      }),
    [queryClient],
  );

  const signIn = useCallback(
    async (email: string, password: string) => {
      const tokens = await loginRequest(email, password);
      storeTokens(tokens);
      setExpired(false);
      setTokenPresent(true);
      // Drop any cached data belonging to a previous principal before the new
      // one's queries run, so a scope change cannot leak across sign-ins.
      queryClient.clear();
      await queryClient.refetchQueries({ queryKey: ['principal'] });
    },
    [queryClient],
  );

  const signOut = useCallback(() => {
    clearTokens();
    setTokenPresent(false);
    setExpired(false);
    queryClient.clear();
  }, [queryClient]);

  const acknowledgeExpiry = useCallback(() => setExpired(false), []);

  const capabilities = useMemo(
    () => new Set(principalQuery.data?.capabilities ?? []),
    [principalQuery.data],
  );

  const state: SessionState = useMemo(() => {
    if (expired) return 'expired';
    if (!tokenPresent) return 'anonymous';
    if (principalQuery.data) return 'authenticated';
    // A 401/403 on /auth/me means the stored token is not usable.
    if (principalQuery.isError) return 'anonymous';
    return 'loading';
  }, [expired, tokenPresent, principalQuery.data, principalQuery.isError]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      principal: principalQuery.data ?? null,
      capabilities,
      can: (capability) => capabilities.has(capability),
      canAny: (...requested) => requested.some((capability) => capabilities.has(capability)),
      signIn,
      signOut,
      acknowledgeExpiry,
    }),
    [state, principalQuery.data, capabilities, signIn, signOut, acknowledgeExpiry],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
