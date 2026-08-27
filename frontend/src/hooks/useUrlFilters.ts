/**
 * Keeps filter state in the URL query string.
 *
 * Operational work is collaborative: an analyst needs to send a colleague the
 * exact view they are looking at, and browser back must undo a filter change
 * rather than leaving the page. Holding filters in the URL gives both, plus
 * reproducibility when a decision is later audited.
 */

import { useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';

export type FilterShape = Record<string, string>;

/**
 * Returns the current filter values merged over the supplied defaults, and a
 * setter that patches individual keys.
 *
 * Values equal to their default are removed from the URL, so a default view
 * has a clean address rather than a string of empty parameters.
 */
export function useUrlFilters<T extends FilterShape>(
  defaults: T,
): [T, (patch: Partial<T>) => void, () => void] {
  const [searchParams, setSearchParams] = useSearchParams();

  // Callers pass an object literal, which is a new identity on every render.
  // Pinning the first one keeps the memo and callbacks below stable instead of
  // invalidating on each render.
  const defaultsRef = useRef(defaults);
  const stableDefaults = defaultsRef.current;

  const values = useMemo(() => {
    const result = { ...stableDefaults };
    for (const key of Object.keys(stableDefaults) as Array<keyof T>) {
      const raw = searchParams.get(String(key));
      if (raw !== null) result[key] = raw as T[keyof T];
    }
    return result;
  }, [searchParams, stableDefaults]);

  const setFilters = useCallback(
    (patch: Partial<T>) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          for (const [key, value] of Object.entries(patch)) {
            if (
              value === undefined ||
              value === null ||
              value === '' ||
              value === stableDefaults[key]
            ) {
              next.delete(key);
            } else {
              next.set(key, String(value));
            }
          }
          return next;
        },
        // Filter changes replace rather than push, so the back button steps
        // out of the page instead of unwinding every dropdown interaction.
        { replace: true },
      );
    },
    [setSearchParams, stableDefaults],
  );

  const reset = useCallback(() => {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        for (const key of Object.keys(stableDefaults)) next.delete(key);
        return next;
      },
      { replace: true },
    );
  }, [setSearchParams, stableDefaults]);

  return [values, setFilters, reset];
}
