/**
 * Ranked risk table shared by the domain pages.
 *
 * On screens below `md` the table is replaced by a card list rather than being
 * horizontally scrolled: an analyst on a phone needs to triage by severity and
 * location, and a five-column scroll makes that harder, not easier.
 */

import { ChevronRight } from 'lucide-react';

import { Table, TableScroll, Td, Th } from '../ui/layout';
import { EmptyState } from '../ui/states';
import { Skeleton, cx } from '../ui/primitives';
import { DataQualityBadge, MetaChip, RiskBadge, StaleBadge } from './badges';
import { formatProbability, humanise } from '../../lib/format';
import { formatDateTime, formatRelative } from '../../lib/time';
import { severity } from '../../lib/risk';
import type { IntelligenceRow } from '../../hooks/useDomainIntelligence';

export interface RiskTableColumn {
  id: string;
  header: string;
  align?: 'left' | 'right';
  /** Hidden below `lg` to keep mid-size screens readable. */
  secondary?: boolean;
  render: (row: IntelligenceRow) => React.ReactNode;
}

export interface RiskTableProps {
  rows: IntelligenceRow[];
  /** Column header for the geographic unit, e.g. "District" or "Station". */
  unitHeader: string;
  /** Additional domain-specific columns inserted before the quality column. */
  columns?: RiskTableColumn[];
  onSelect?: (row: IntelligenceRow) => void;
  selectedId?: string | null;
  pending?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
}

export function RiskTable({
  rows,
  unitHeader,
  columns = [],
  onSelect,
  selectedId,
  pending,
  emptyTitle = 'No intelligence in scope',
  emptyDescription = 'No eligible intelligence is available for this geography and period.',
  className,
}: RiskTableProps) {
  if (pending) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        {[0, 1, 2, 3, 4, 5].map((index) => (
          <Skeleton key={index} className="h-10" />
        ))}
      </div>
    );
  }

  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <div className={className}>
      {/* Desktop and tablet: full table. */}
      <div className="hidden md:block">
        <TableScroll>
          <Table>
            <thead>
              <tr>
                <Th>{unitHeader}</Th>
                <Th>Risk</Th>
                <Th align="right">Probability</Th>
                {columns.map((column) => (
                  <Th
                    key={column.id}
                    align={column.align}
                    className={column.secondary ? 'hidden lg:table-cell' : undefined}
                  >
                    {column.header}
                  </Th>
                ))}
                <Th className="hidden lg:table-cell">Data quality</Th>
                <Th align="right">Updated</Th>
                {onSelect && <Th className="w-8"><span className="sr-only">Open</span></Th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const selected = selectedId === row.signal.admin_unit_id;
                return (
                  <tr
                    key={row.signal.id}
                    onClick={onSelect ? () => onSelect(row) : undefined}
                    tabIndex={onSelect ? 0 : undefined}
                    onKeyDown={
                      onSelect
                        ? (event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              onSelect(row);
                            }
                          }
                        : undefined
                    }
                    aria-selected={onSelect ? selected : undefined}
                    className={cx(
                      'border-l-[3px] transition-colors',
                      severity(row.level).accent,
                      onSelect && 'cursor-pointer hover:bg-[--color-surface-subtle]',
                      selected && 'bg-[--color-brand-50]',
                    )}
                  >
                    <Td>
                      <p className="font-medium text-[--color-ink]">{row.unitName}</p>
                      {row.parentName && (
                        <p className="text-[11px] text-[--color-ink-muted]">{row.parentName}</p>
                      )}
                    </Td>
                    <Td>
                      <span className="flex flex-wrap items-center gap-1.5">
                        <RiskBadge level={row.level} size="sm" />
                        {row.suppressionReason && <StaleBadge />}
                      </span>
                    </Td>
                    <Td align="right" className="font-medium tabular-nums">
                      {formatProbability(row.probability)}
                    </Td>
                    {columns.map((column) => (
                      <Td
                        key={column.id}
                        align={column.align}
                        className={column.secondary ? 'hidden lg:table-cell' : undefined}
                      >
                        {column.render(row)}
                      </Td>
                    ))}
                    <Td className="hidden lg:table-cell">
                      <DataQualityBadge
                        size="sm"
                        status={
                          typeof row.signal.provenance?.data_quality === 'string'
                            ? row.signal.provenance.data_quality
                            : null
                        }
                      />
                    </Td>
                    <Td align="right" className="whitespace-nowrap text-[--color-ink-muted]">
                      <time
                        dateTime={row.signal.created_at}
                        title={formatDateTime(row.signal.created_at)}
                      >
                        {formatRelative(row.signal.created_at)}
                      </time>
                    </Td>
                    {onSelect && (
                      <Td align="right">
                        <ChevronRight
                          className="size-4 text-[--color-ink-faint]"
                          aria-hidden="true"
                        />
                      </Td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </TableScroll>
      </div>

      {/* Mobile: severity-led cards. */}
      <ul className="flex flex-col gap-2 md:hidden">
        {rows.map((row) => (
          <li key={row.signal.id}>
            <button
              type="button"
              onClick={onSelect ? () => onSelect(row) : undefined}
              disabled={!onSelect}
              className={cx(
                'flex w-full flex-col gap-2 rounded-[--radius-md] border-l-[3px] bg-[--color-surface] p-3 text-left',
                'ring-1 ring-[--color-line] disabled:cursor-default',
                severity(row.level).accent,
                onSelect && 'transition-shadow hover:shadow-[--shadow-sm]',
              )}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <RiskBadge level={row.level} size="sm" />
                <span className="text-[13px] font-medium tabular-nums text-[--color-ink]">
                  {formatProbability(row.probability)}
                </span>
                {row.suppressionReason && <StaleBadge />}
              </div>
              <div>
                <p className="text-[13px] font-medium text-[--color-ink]">{row.unitName}</p>
                {row.parentName && (
                  <p className="text-[11px] text-[--color-ink-muted]">{row.parentName}</p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-[--color-ink-muted]">
                <span>{row.signal.target_period}</span>
                <span title={formatDateTime(row.signal.created_at)}>
                  {formatRelative(row.signal.created_at)}
                </span>
                {typeof row.signal.provenance?.data_quality === 'string' && (
                  <MetaChip>{humanise(row.signal.provenance.data_quality)}</MetaChip>
                )}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
