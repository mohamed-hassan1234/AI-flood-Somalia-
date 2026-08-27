/**
 * Joins risk signals to administrative geography and reduces them to the view
 * model every domain page renders.
 *
 * `/risks` returns the full signal history newest-first, keyed by
 * `admin_unit_id`. Operational pages want the *current* signal per unit, so
 * this collapses to the newest signal per unit and attaches the unit's name
 * and parent. Older signals stay available for the history view.
 */

import { useMemo } from 'react';

import { useAdminUnits, useRiskSignals } from '../api/queries';
import { ApiError } from '../api/client';
import { highestSeverity, toSeverity, type Severity } from '../lib/risk';
import type { AdminUnit, RiskDomain, RiskSignal } from '../types/api';

export interface IntelligenceRow {
  signal: RiskSignal;
  /** Resolved administrative unit, when the principal can read geography. */
  unit: AdminUnit | undefined;
  unitName: string;
  /** Parent unit name — the region a district belongs to. */
  parentName: string | undefined;
  level: Severity;
  probability: number | null;
  /** True when provenance reports the record as stale or suppressed. */
  degraded: boolean;
  suppressionReason: string | null;
}

export interface DomainIntelligence {
  rows: IntelligenceRow[];
  /** Newest signal per unit, ordered by severity then probability. */
  ranked: IntelligenceRow[];
  countsByLevel: Record<Severity, number>;
  watchPlus: number;
  warningPlus: number;
  criticalCount: number;
  unitsEvaluated: number;
  highest: Severity;
  /** Most recent signal generation time across the domain. */
  latestAt: string | null;
  isPending: boolean;
  isError: boolean;
  error: ApiError | null;
  refetch: () => void;
  /** True when geography could not be read; names fall back to identifiers. */
  geographyUnavailable: boolean;
}

const EMPTY_COUNTS: Record<Severity, number> = {
  critical: 0,
  warning: 0,
  watch: 0,
  normal: 0,
  unknown: 0,
};

/** Reads a provenance flag whatever casing or spelling the pipeline used. */
function readProvenanceString(
  signal: RiskSignal,
  ...keys: string[]
): string | null {
  for (const key of keys) {
    const value = signal.provenance?.[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return null;
}

export function useDomainIntelligence(
  domain: RiskDomain,
  enabled = true,
  limit = 500,
): DomainIntelligence {
  const signals = useRiskSignals({ domain, limit }, enabled);
  const units = useAdminUnits(undefined, enabled);

  return useMemo(() => {
    const unitIndex = new Map<string, AdminUnit>();
    for (const unit of units.data ?? []) unitIndex.set(unit.id, unit);

    const rows: IntelligenceRow[] = (signals.data ?? []).map((signal) => {
      const unit = unitIndex.get(signal.admin_unit_id);
      const parent = unit?.parent_id ? unitIndex.get(unit.parent_id) : undefined;

      const quality = readProvenanceString(signal, 'data_quality', 'overall_status');
      const freshness = readProvenanceString(signal, 'freshness', 'freshness_status');
      const suppression = readProvenanceString(signal, 'suppression_reason');

      const degraded =
        suppression !== null ||
        /stale|insufficient|partial|degraded/i.test(`${quality ?? ''} ${freshness ?? ''}`);

      return {
        signal,
        unit,
        // Fall back to a short identifier rather than inventing a place name.
        unitName: unit?.name ?? `Unit ${signal.admin_unit_id.slice(0, 8)}`,
        parentName: parent?.name,
        level: toSeverity(signal.level),
        probability: signal.score,
        degraded,
        suppressionReason: suppression,
      };
    });

    // Collapse to the newest signal per administrative unit. `/risks` is
    // already ordered by `created_at` descending, so the first occurrence wins.
    const seen = new Set<string>();
    const current: IntelligenceRow[] = [];
    for (const row of rows) {
      if (seen.has(row.signal.admin_unit_id)) continue;
      seen.add(row.signal.admin_unit_id);
      current.push(row);
    }

    const countsByLevel = { ...EMPTY_COUNTS };
    for (const row of current) countsByLevel[row.level] += 1;

    const ranked = [...current].sort((a, b) => {
      const bySeverity =
        severityWeight(b.level) - severityWeight(a.level);
      if (bySeverity !== 0) return bySeverity;
      const byProbability = (b.probability ?? -1) - (a.probability ?? -1);
      if (byProbability !== 0) return byProbability;
      return a.unitName.localeCompare(b.unitName);
    });

    const latestAt =
      current.reduce<string | null>((latest, row) => {
        if (!latest) return row.signal.created_at;
        return row.signal.created_at > latest ? row.signal.created_at : latest;
      }, null) ?? null;

    const error = signals.error ?? null;

    return {
      rows,
      ranked,
      countsByLevel,
      watchPlus: countsByLevel.watch + countsByLevel.warning + countsByLevel.critical,
      warningPlus: countsByLevel.warning + countsByLevel.critical,
      criticalCount: countsByLevel.critical,
      unitsEvaluated: current.length,
      highest: highestSeverity(current.map((row) => row.level)),
      latestAt,
      isPending: signals.isPending,
      isError: signals.isError,
      error,
      refetch: () => {
        void signals.refetch();
        void units.refetch();
      },
      // Geography is a separate capability; a principal may read predictions
      // without it. That degrades labels, not correctness.
      geographyUnavailable: units.isError,
    };
  }, [signals, units]);
}

function severityWeight(level: Severity): number {
  switch (level) {
    case 'critical':
      return 4;
    case 'warning':
      return 3;
    case 'watch':
      return 2;
    case 'normal':
      return 1;
    default:
      return 0;
  }
}
