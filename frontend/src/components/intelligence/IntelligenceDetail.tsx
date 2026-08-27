/**
 * The reusable intelligence detail view.
 *
 * Every risk record in the product is explained through the same ordered
 * questions, so an analyst reads the same structure whether they arrived from
 * the map, a domain table or a warning review:
 *
 *   WHERE · WHAT · HOW SERIOUS · HOW LIKELY · WHEN · WHO IS EXPOSED ·
 *   WHY · HOW GOOD IS THE EVIDENCE · WHAT SHOULD HAPPEN NEXT ·
 *   WHICH MODEL · WHEN GENERATED
 *
 * The "why" section translates model attributions into operational language.
 * Raw feature internals stay available, but behind a disclosure — they help a
 * data scientist and confuse a district officer.
 */

import { useState } from 'react';
import { ChevronDown, FlaskConical, Info, TriangleAlert } from 'lucide-react';

import {
  DataPoint,
  DataGrid,
  cx,
} from '../ui/primitives';
import { Note } from '../ui/states';
import {
  ConfidenceIndicator,
  DataQualityBadge,
  MetaChip,
  RiskBadge,
  StaleBadge,
} from './badges';
import { domain as domainDescriptor } from '../../lib/risk';
import {
  NOT_REPORTED,
  formatProbability,
  formatSignedPercent,
  humanise,
  renderUnknown,
} from '../../lib/format';
import { formatDateTime } from '../../lib/time';
import type { IntelligenceRow } from '../../hooks/useDomainIntelligence';
import type { RiskDriver } from '../../types/api';

/* ---------------------------------------------------------------- drivers -- */

/**
 * Reason codes are the pipeline's own operational vocabulary. Where a code is
 * recognised it is rendered as a sentence an operator can act on; anything
 * unrecognised falls back to a readable version of the code rather than being
 * hidden, so a new code never silently disappears from the evidence.
 */
const REASON_SENTENCES: Record<string, string> = {
  RIVER_LEVEL_NEAR_THRESHOLD: 'River level is approaching the operational threshold',
  RIVER_LEVEL_ABOVE_THRESHOLD: 'River level is above the operational threshold',
  RIVER_LEVEL_RISING: 'River level has been rising over recent observations',
  RAINFALL_ABOVE_NORMAL: 'Recent rainfall is above normal for this period',
  RAINFALL_BELOW_NORMAL: 'Recent rainfall is below normal for this period',
  ANTECEDENT_WET: 'Antecedent ground conditions are wet',
  SOIL_MOISTURE_HIGH: 'Soil moisture is elevated',
  SOIL_MOISTURE_LOW: 'Soil moisture is depleted',
  VEGETATION_STRESS: 'Vegetation condition indicates stress',
  NDVI_BELOW_NORMAL: 'Vegetation index is below its seasonal normal',
  TEMPERATURE_ABOVE_NORMAL: 'Temperature is above normal for this period',
  MARKET_PRICE_RISING: 'Staple food prices are rising',
};

function driverSentence(driver: RiskDriver): string {
  const code = typeof driver.reason_code === 'string' ? driver.reason_code : null;
  if (code && REASON_SENTENCES[code]) return REASON_SENTENCES[code];
  if (code) return humanise(code);
  if (typeof driver.feature === 'string') return humanise(driver.feature);
  if (typeof driver.indicator === 'string') return humanise(driver.indicator);
  return 'Contributing model factor';
}

function DriverList({ drivers }: { drivers: RiskDriver[] }) {
  const [technicalOpen, setTechnicalOpen] = useState(false);

  if (!drivers.length) {
    return (
      <p className="text-[13px] leading-5 text-[--color-ink-muted]">
        The API did not return driver attributions for this signal. Without them the model’s
        reasoning cannot be shown — this is reported rather than substituted.
      </p>
    );
  }

  // Strongest contribution first, so the operational headline leads.
  const ordered = [...drivers].sort(
    (a, b) =>
      Math.abs(b.probability_change_if_replaced_by_training_median ?? 0) -
      Math.abs(a.probability_change_if_replaced_by_training_median ?? 0),
  );

  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-2">
        {ordered.map((driver, index) => {
          const contribution = driver.probability_change_if_replaced_by_training_median;
          return (
            <li
              key={`${driver.feature ?? driver.reason_code ?? index}`}
              className="flex items-start gap-3 rounded-[--radius-md] bg-[--color-surface-subtle] px-3 py-2.5 ring-1 ring-[--color-line]"
            >
              <span className="mt-px flex size-5 shrink-0 items-center justify-center rounded-full bg-[--color-surface-sunken] text-[11px] font-semibold text-[--color-ink-secondary]">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium leading-5 text-[--color-ink]">
                  {driverSentence(driver)}
                </p>
                {contribution !== undefined && contribution !== null && (
                  <p className="mt-0.5 text-[12px] text-[--color-ink-muted]">
                    Contributes {formatSignedPercent(contribution)} to the modelled probability,
                    relative to typical conditions.
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      <div>
        <button
          type="button"
          onClick={() => setTechnicalOpen((value) => !value)}
          aria-expanded={technicalOpen}
          /* min-h-6 keeps the tap target at the 24px WCAG 2.5.8 minimum; the
             negative inline margin keeps it optically aligned. */
          className="-mx-1 inline-flex min-h-6 items-center gap-1.5 rounded-[--radius-xs] px-1 text-[12px] font-medium text-[--color-ink-muted] transition-colors hover:text-[--color-ink]"
        >
          <FlaskConical className="size-3.5" aria-hidden="true" />
          Technical attribution
          <ChevronDown
            className={cx('size-3.5 transition-transform', technicalOpen && 'rotate-180')}
            aria-hidden="true"
          />
        </button>

        {technicalOpen && (
          <div className="mt-2 overflow-x-auto rounded-[--radius-md] ring-1 ring-[--color-line]">
            <table className="min-w-full text-left text-[12px]">
              <thead className="bg-[--color-surface-sunken]">
                <tr>
                  <th scope="col" className="px-3 py-2 font-semibold text-[--color-ink-muted]">
                    Feature
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold text-[--color-ink-muted]">
                    Observed
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold text-[--color-ink-muted]">
                    Training median
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold text-[--color-ink-muted]">
                    Δ probability
                  </th>
                </tr>
              </thead>
              <tbody>
                {ordered.map((driver, index) => (
                  <tr key={index} className="border-t border-[--color-line]">
                    <td className="px-3 py-2 font-mono text-[11px] text-[--color-ink]">
                      {driver.feature ?? driver.indicator ?? driver.reason_code ?? NOT_REPORTED}
                    </td>
                    <td className="px-3 py-2 text-[--color-ink-secondary]">
                      {renderUnknown(driver.observed_value)}
                    </td>
                    <td className="px-3 py-2 text-[--color-ink-secondary]">
                      {renderUnknown(driver.training_median)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-[--color-ink-secondary]">
                      {formatSignedPercent(
                        driver.probability_change_if_replaced_by_training_median,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- section -- */

function Section({
  question,
  title,
  children,
  className,
}: {
  question: string;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cx('flex flex-col gap-2.5', className)}>
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.11em] text-[--color-ink-faint]">
          {question}
        </p>
        <h3 className="text-[13px] font-semibold text-[--color-ink]">{title}</h3>
      </div>
      {children}
    </section>
  );
}

/* ------------------------------------------------------------ component -- */

export interface IntelligenceDetailProps {
  row: IntelligenceRow;
  /** Rendered under "What should happen next", when actions are available. */
  recommendedActions?: React.ReactNode;
  /** Rendered under "Who or what may be exposed". */
  exposure?: React.ReactNode;
  /** Compact mode drops section chrome for use inside a drawer. */
  compact?: boolean;
  className?: string;
}

export function IntelligenceDetail({
  row,
  recommendedActions,
  exposure,
  compact,
  className,
}: IntelligenceDetailProps) {
  const { signal } = row;
  const descriptor = domainDescriptor(signal.domain);

  const modelId =
    typeof signal.provenance?.model_id === 'string' ? signal.provenance.model_id : null;
  const modelVersion =
    typeof signal.provenance?.model_version === 'string' ? signal.provenance.model_version : null;
  const pipelineVersion =
    typeof signal.provenance?.pipeline_version === 'string'
      ? signal.provenance.pipeline_version
      : null;
  const dataQuality =
    typeof signal.provenance?.data_quality === 'string' ? signal.provenance.data_quality : null;
  const freshness =
    typeof signal.provenance?.freshness === 'string' ? signal.provenance.freshness : null;

  return (
    <div className={cx('flex flex-col gap-6', compact && 'gap-5', className)}>
      {/* WHERE · WHAT · HOW SERIOUS · HOW LIKELY */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <RiskBadge level={signal.level} />
          <MetaChip>{descriptor.label}</MetaChip>
          {row.degraded && <StaleBadge asOf={signal.created_at} />}
        </div>

        <div>
          <h2 className="text-[18px] font-semibold tracking-[-0.015em] text-[--color-ink]">
            {row.unitName}
          </h2>
          <p className="mt-0.5 text-[13px] text-[--color-ink-muted]">
            {row.parentName ? `${row.parentName} · ` : ''}
            {humanise(row.unit?.level ?? descriptor.scope)}
          </p>
        </div>

        <DataGrid columns={2}>
          <DataPoint
            label="Modelled probability"
            value={
              signal.score === null ? (
                <span className="text-[--color-ink-muted]">Withheld</span>
              ) : (
                formatProbability(signal.score)
              )
            }
            hint={
              signal.score === null
                ? 'No probability was issued for this record.'
                : `Probability of the modelled ${descriptor.label.toLowerCase()} condition.`
            }
          />
          <DataPoint
            label="Model confidence"
            value={<ConfidenceIndicator value={signal.confidence} />}
          />
        </DataGrid>
      </div>

      {/* Scope honesty — always visible next to the risk, never buried. */}
      <Note tone="neutral" icon={<Info className="size-3.5" aria-hidden="true" />}>
        {descriptor.scopeStatement}
      </Note>

      {/* WHEN */}
      <Section question="When" title="Forecast period">
        <DataGrid columns={2}>
          <DataPoint label="Target period" value={signal.target_period || NOT_REPORTED} />
          <DataPoint
            label="Signal generated"
            value={formatDateTime(signal.created_at)}
            hint="Time the model produced this signal."
          />
        </DataGrid>
      </Section>

      {/* WHO / WHAT IS EXPOSED */}
      {exposure && (
        <Section question="Who or what may be exposed" title="Exposure context">
          {exposure}
        </Section>
      )}

      {/* WHY */}
      <Section question="Why" title="What is driving this risk">
        <DriverList drivers={signal.drivers ?? []} />
      </Section>

      {/* EVIDENCE QUALITY */}
      <Section question="How good is the evidence" title="Data quality and freshness">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <DataQualityBadge status={dataQuality} />
            {freshness && <MetaChip>Freshness: {humanise(freshness)}</MetaChip>}
          </div>

          {row.suppressionReason && (
            <Note tone="caution" icon={<TriangleAlert className="size-3.5" aria-hidden="true" />}>
              <span className="font-semibold">Warning suppressed.</span>{' '}
              {row.suppressionReason}
            </Note>
          )}

          {!dataQuality && !freshness && (
            <p className="text-[13px] leading-5 text-[--color-ink-muted]">
              This signal’s provenance did not include a data-quality assessment. Treat the record
              as unverified for quality rather than assuming it is good.
            </p>
          )}
        </div>
      </Section>

      {/* WHAT SHOULD HAPPEN NEXT */}
      {recommendedActions && (
        <Section question="What should happen next" title="Recommended actions">
          {recommendedActions}
        </Section>
      )}

      {/* WHICH MODEL */}
      <Section question="Which model" title="Model and lineage">
        <DataGrid columns={2}>
          <DataPoint label="Model" value={modelId ?? NOT_REPORTED} />
          <DataPoint label="Model version" value={modelVersion ?? NOT_REPORTED} />
          <DataPoint label="Pipeline version" value={pipelineVersion ?? NOT_REPORTED} />
          <DataPoint
            label="Signal identifier"
            value={<code className="font-mono text-[12px]">{signal.id.slice(0, 12)}</code>}
          />
        </DataGrid>
      </Section>
    </div>
  );
}

/* ------------------------------------------------------- scope statement -- */

/** Standalone scope notice for pages that show a domain without a full record. */
export function ScopeNotice({
  domain: key,
  className,
}: {
  domain: Parameters<typeof domainDescriptor>[0];
  className?: string;
}) {
  const descriptor = domainDescriptor(key);
  return (
    <Note
      tone="neutral"
      icon={<Info className="size-3.5" aria-hidden="true" />}
      className={className}
    >
      <span className="font-semibold text-[--color-ink]">Scope: </span>
      {descriptor.scopeStatement}
    </Note>
  );
}
