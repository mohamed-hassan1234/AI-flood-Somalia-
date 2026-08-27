/**
 * Registers `ApiError` as the default error type for every TanStack Query
 * hook in this application.
 *
 * Without this the error is inferred as `unknown`, which forces a cast at
 * every call site that wants to branch on `error.kind`. Since `src/api/client`
 * normalises *every* failure — network, timeout, HTTP status — into an
 * `ApiError` before it can reach a query, the registration is accurate rather
 * than merely convenient.
 */

import type { ApiError } from '../api/client';

declare module '@tanstack/react-query' {
  interface Register {
    defaultError: ApiError;
  }
}
