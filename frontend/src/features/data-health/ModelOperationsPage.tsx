/**
 * Model Operations — the registered model versions behind the intelligence.
 *
 * Exists so a reviewer can answer "which model produced this, and how was it
 * evaluated" without leaving the platform. Metrics are rendered exactly as the
 * registry reports them; nothing is recomputed or rounded into a friendlier
 * shape here.
 */

import { BarChart3 } from 'lucide-react';

import { useModelOperations } from '../../api/queries';
import { Card, Skeleton } from '../../components/ui/primitives';
import {
  MetaBar,
  MetaItem,
  PageHeader,
  SectionHeader,
  Table,
  TableScroll,
  Td,
  Th,
} from '../../components/ui/layout';
import { EmptyState, QueryBoundary } from '../../components/ui/states';
import { MetaChip } from '../../components/intelligence/badges';
import { formatCount, humanise, renderUnknown } from '../../lib/format';

export function ModelOperationsPage() {
  const models = useModelOperations(true);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Assurance"
        title="Model Operations"
        description="Registered model versions, their training snapshots and their recorded evaluation metrics."
        meta={
          <MetaBar>
            <MetaItem label="Registered models" value={formatCount(models.data?.length ?? 0)} />
            <MetaItem
              label="In production"
              value={formatCount(
                (models.data ?? []).filter((model) => model.state === 'production').length,
              )}
            />
            <MetaItem
              label="Promotion ready"
              value={formatCount(
                (models.data ?? []).filter((model) => model.promotion_ready).length,
              )}
            />
          </MetaBar>
        }
      />

      <QueryBoundary
        query={models}
        skeleton={<Skeleton className="h-64 w-full" />}
        isEmpty={(data) => data.length === 0}
        empty={
          <EmptyState
            icon={<BarChart3 className="size-4.5" aria-hidden="true" />}
            title="No models registered"
            description="No model version has been registered in the governance registry on this deployment."
          />
        }
      >
        {(data) => (
          <>
            <Card flush>
              <div className="border-b border-[--color-line] px-4 py-3">
                <SectionHeader className="mb-0" title="Registered versions" />
              </div>
              <TableScroll className="px-4 py-2 sm:px-4">
                <Table>
                  <thead>
                    <tr>
                      <Th>Model</Th>
                      <Th>Version</Th>
                      <Th>State</Th>
                      <Th className="hidden lg:table-cell">Training snapshot</Th>
                      <Th align="right" className="hidden lg:table-cell">
                        Rows
                      </Th>
                      <Th>Promotion</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((model) => (
                      <tr key={model.id}>
                        <Td className="font-medium">{model.name}</Td>
                        <Td className="font-mono text-[12px] text-[--color-ink-secondary]">
                          {model.version}
                        </Td>
                        <Td>
                          <MetaChip>{humanise(model.state)}</MetaChip>
                        </Td>
                        <Td className="hidden text-[--color-ink-secondary] lg:table-cell">
                          {model.snapshot_name}
                          <span className="block text-[11px] text-[--color-ink-muted]">
                            {model.feature_name} · {model.feature_version}
                          </span>
                        </Td>
                        <Td
                          align="right"
                          className="hidden tabular-nums text-[--color-ink-secondary] lg:table-cell"
                        >
                          {formatCount(model.snapshot_row_count)}
                        </Td>
                        <Td>
                          <MetaChip
                            className={
                              model.promotion_ready
                                ? 'bg-[--color-ok-bg] text-[--color-ok-fg]'
                                : undefined
                            }
                          >
                            {model.promotion_ready ? 'Ready' : 'Not ready'}
                          </MetaChip>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableScroll>
            </Card>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {data.map((model) => (
                <Card key={model.id}>
                  <SectionHeader
                    title={`${model.name} ${model.version}`}
                    description="Recorded evaluation metrics"
                  />
                  {Object.keys(model.metrics).length === 0 ? (
                    <p className="text-[13px] text-[--color-ink-muted]">
                      No evaluation metrics were recorded for this version.
                    </p>
                  ) : (
                    <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5">
                      {Object.entries(model.metrics).map(([key, value]) => (
                        <div key={key}>
                          <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[--color-ink-faint]">
                            {humanise(key)}
                          </dt>
                          <dd className="mt-0.5 text-[13px] font-medium tabular-nums text-[--color-ink]">
                            {renderUnknown(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </Card>
              ))}
            </div>
          </>
        )}
      </QueryBoundary>
    </div>
  );
}
