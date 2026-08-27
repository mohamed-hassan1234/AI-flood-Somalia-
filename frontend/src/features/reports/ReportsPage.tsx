/**
 * Governed reports.
 *
 * Reports are analyst-authored narrative products attached to a warning, with
 * mandatory source lineage. Draft and published states are visually distinct
 * so an unpublished draft is never mistaken for an issued report.
 */

import { useMemo, useState } from 'react';
import { FileText } from 'lucide-react';

import { useReports } from '../../api/queries';
import { Skeleton, cx } from '../../components/ui/primitives';
import { Dialog, MetaBar, MetaItem, PageHeader, SectionHeader } from '../../components/ui/layout';
import { EmptyState, QueryBoundary } from '../../components/ui/states';
import { ClassificationBadge, MetaChip } from '../../components/intelligence/badges';
import { NOT_REPORTED, formatCount, safeLabel } from '../../lib/format';
import { formatDateTime } from '../../lib/time';
import type { GovernedReport } from '../../types/api';

export function ReportsPage() {
  const reports = useReports(true);
  const [open, setOpen] = useState<GovernedReport | null>(null);

  const published = useMemo(
    () => (reports.data ?? []).filter((report) => report.status === 'published').length,
    [reports.data],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Operations"
        title="Reports"
        description="Governed narrative reports attached to warnings, each carrying its own source lineage."
        meta={
          <MetaBar>
            <MetaItem label="Reports in scope" value={formatCount(reports.data?.length ?? 0)} />
            <MetaItem label="Published" value={formatCount(published)} />
          </MetaBar>
        }
      />

      <QueryBoundary
        query={reports}
        skeleton={
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {[0, 1, 2, 3].map((index) => (
              <Skeleton key={index} className="h-40" />
            ))}
          </div>
        }
        isEmpty={(data) => data.length === 0}
        empty={
          <EmptyState
            icon={<FileText className="size-4.5" aria-hidden="true" />}
            title="No reports available"
            description="No governed report has been created for the warnings within your scope."
          />
        }
      >
        {(data) => (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {data.map((report) => (
              <button
                key={report.id}
                type="button"
                onClick={() => setOpen(report)}
                className={cx(
                  'flex flex-col gap-2.5 rounded-[--radius-lg] bg-[--color-surface] p-4 text-left',
                  'ring-1 ring-[--color-line] transition-shadow hover:shadow-[--shadow-sm]',
                )}
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <MetaChip
                    className={
                      report.status === 'published'
                        ? 'bg-[--color-ok-bg] text-[--color-ok-fg]'
                        : 'bg-[--color-muted-bg] text-[--color-muted-fg]'
                    }
                  >
                    {report.status === 'published' ? 'Published' : 'Draft'}
                  </MetaChip>
                  <ClassificationBadge classification={report.classification} />
                  <MetaChip>{report.reporting_period}</MetaChip>
                </div>
                <p className="text-[14px] font-semibold leading-5 text-[--color-ink]">
                  {report.title}
                </p>
                <p className="text-[12px] text-[--color-ink-muted]">
                  {formatCount(report.sections.length)} sections ·{' '}
                  {formatCount(report.findings.length)} findings ·{' '}
                  {formatCount(report.source_lineage.length)} sources cited
                </p>
                <p className="mt-auto text-[11px] text-[--color-ink-muted]">
                  {report.published_at
                    ? `Published ${formatDateTime(report.published_at)}`
                    : `Created ${formatDateTime(report.created_at)}`}
                </p>
              </button>
            ))}
          </div>
        )}
      </QueryBoundary>

      <Dialog
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open?.title ?? 'Report'}
        description={open ? `${open.reporting_period} · ${open.status}` : undefined}
        size="lg"
      >
        {open && (
          <div className="flex flex-col gap-5">
            {open.sections.map((section, index) => (
              <section key={index}>
                <h3 className="text-[13px] font-semibold text-[--color-ink]">{section.heading}</h3>
                <p className="mt-1 whitespace-pre-line text-[13px] leading-6 text-[--color-ink-secondary]">
                  {section.body}
                </p>
              </section>
            ))}

            {open.findings.length > 0 && (
              <section>
                <SectionHeader title="Findings" />
                <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[13px] leading-5 text-[--color-ink-secondary]">
                  {open.findings.map((finding, index) => (
                    <li key={index}>{finding}</li>
                  ))}
                </ul>
              </section>
            )}

            {open.recommendations.length > 0 && (
              <section>
                <SectionHeader
                  title="Recommendations"
                  description="Proposed actions, not actions already taken"
                />
                <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[13px] leading-5 text-[--color-ink-secondary]">
                  {open.recommendations.map((recommendation, index) => (
                    <li key={index}>{recommendation}</li>
                  ))}
                </ul>
              </section>
            )}

            <section>
              <SectionHeader
                title="Source lineage"
                description="Every report cites the sources and reference periods it drew on"
              />
              <ul className="flex flex-col gap-1.5">
                {open.source_lineage.map((source, index) => (
                  <li
                    key={index}
                    className="rounded-[--radius-md] bg-[--color-surface-subtle] px-3 py-2 text-[12px] text-[--color-ink-secondary] ring-1 ring-[--color-line]"
                  >
                    {safeLabel(source.source_id) === NOT_REPORTED
                      ? 'Unnamed source'
                      : safeLabel(source.source_id)}
                    {source.reference_period ? ` · ${safeLabel(source.reference_period)}` : ''}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )}
      </Dialog>
    </div>
  );
}
