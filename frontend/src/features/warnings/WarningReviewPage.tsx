/**
 * Warning review workspace.
 *
 * The most consequential screen in the product: where a human decides whether
 * a model output becomes an authorised government warning.
 *
 * Three rules govern the decision panel:
 *
 * 1. Only transitions the backend actually defines are offered. The workflow
 *    in `backend/app/modules/alerts/service.py` is
 *    draft → in_review → {verification_required, approved} → … → published →
 *    resolved. There is no reject or hold transition, so no reject or hold
 *    button is drawn — a control that always fails is worse than none.
 * 2. Only transitions this principal holds the capability for are offered,
 *    and when none are, the panel explains the boundary rather than showing a
 *    row of disabled buttons.
 * 3. Approve, publish and resolve require explicit confirmation naming the
 *    consequence. Publishing is never one click.
 */

import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Info,
  Lock,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';

import { useAuth } from '../../app/providers/AuthProvider';
import {
  useActionItems,
  useAlert,
  useAlertTransition,
  useAlerts,
  useExposureAssessments,
  useRiskSignals,
} from '../../api/queries';
import { Button, Card, DataGrid, DataPoint, Panel, Skeleton, cx } from '../../components/ui/primitives';
import { ConfirmDialog, MetaBar, MetaItem, PageHeader } from '../../components/ui/layout';
import { AccessDenied, EmptyState, ErrorState, Note } from '../../components/ui/states';
import {
  ClassificationBadge,
  ConfidenceIndicator,
  GovernanceBadge,
  MetaChip,
  RiskBadge,
  StatusBadge,
} from '../../components/intelligence/badges';
import { IntelligenceDetail } from '../../components/intelligence/IntelligenceDetail';
import {
  GOVERNANCE_CHAIN,
  availableTransitions,
  domain as domainDescriptor,
  severity,
  workflow,
  type TransitionAction,
} from '../../lib/risk';
import { NOT_REPORTED, formatCompact, formatCount, formatProbability, humanise } from '../../lib/format';
import { formatDateTime } from '../../lib/time';
import type { ActionStatus, AlertListItem, AlertStatus, RiskSignal } from '../../types/api';
import type { IntelligenceRow } from '../../hooks/useDomainIntelligence';

/* ---------------------------------------------------------- progress rail -- */

/**
 * Renders the governance chain so the difference between a model output and an
 * authorised warning is visible at a glance, not inferred from a status word.
 */
function GovernanceRail({ status }: { status: AlertStatus }) {
  const current = workflow(status);
  const labels: Record<string, string> = {
    draft: 'AI generated',
    in_review: 'Analyst review',
    verified: 'Verification',
    approved: 'Authorised approval',
    published: 'Published',
  };

  return (
    <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-2" aria-label="Governance progress">
      {GOVERNANCE_CHAIN.map((step, index) => {
        const descriptor = workflow(step);
        const reached = current.step >= descriptor.step;
        const isCurrent = current.step === descriptor.step;
        return (
          <li key={step} className="flex items-center gap-1.5">
            <span
              className={cx(
                'inline-flex items-center gap-1.5 rounded-[--radius-xs] px-2 py-1 text-[11px] font-medium',
                isCurrent
                  ? 'bg-[--color-brand-600] text-white'
                  : reached
                    ? 'bg-[--color-brand-50] text-[--color-brand-700]'
                    : 'bg-[--color-surface-sunken] text-[--color-ink-faint]',
              )}
              aria-current={isCurrent ? 'step' : undefined}
            >
              {reached && !isCurrent && (
                <CheckCircle2 className="size-3" aria-hidden="true" />
              )}
              {labels[step]}
            </span>
            {index < GOVERNANCE_CHAIN.length - 1 && (
              <span className="text-[--color-ink-faint]" aria-hidden="true">
                ›
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------ decisions -- */

function DecisionPanel({
  alertId,
  status,
  riskLevel,
}: {
  alertId: string;
  status: AlertStatus;
  riskLevel: string;
}) {
  const { capabilities } = useAuth();
  const transition = useAlertTransition();
  const [pendingAction, setPendingAction] = useState<TransitionAction | null>(null);
  const [feedback, setFeedback] = useState<{ tone: 'ok' | 'error'; message: string } | null>(null);

  const permitted = useMemo(
    () => availableTransitions(status, capabilities),
    [status, capabilities],
  );

  const state = workflow(status);
  const terminal = status === 'resolved';

  function run(action: TransitionAction) {
    setFeedback(null);
    transition.mutate(
      { alertId, target: action.target },
      {
        onSuccess: () => {
          setPendingAction(null);
          setFeedback({
            tone: 'ok',
            message: `Warning moved to ${workflow(action.target).label}. This decision is recorded against your account.`,
          });
        },
        onError: (apiError) => {
          setPendingAction(null);
          setFeedback({
            tone: 'error',
            message:
              apiError.kind === 'conflict'
                ? 'This warning changed state while you were reviewing it. Reload before deciding again.'
                : apiError.message,
          });
        },
      },
    );
  }

  return (
    <Panel
      eyebrow="Section 6"
      title="Decision"
      className={cx(
        permitted.length > 0 && severity(riskLevel).rank >= 3 && 'ring-2 ring-[--color-risk-critical-line]',
      )}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={status} />
          <GovernanceBadge status={status} />
        </div>

        <p className="text-[13px] leading-5 text-[--color-ink-secondary]">
          {state.description}
        </p>

        {feedback && (
          <Note
            tone={feedback.tone === 'ok' ? 'info' : 'caution'}
            icon={
              feedback.tone === 'ok' ? (
                <CheckCircle2 className="size-3.5" aria-hidden="true" />
              ) : (
                <TriangleAlert className="size-3.5" aria-hidden="true" />
              )
            }
          >
            {feedback.message}
          </Note>
        )}

        {terminal ? (
          <Note tone="neutral" icon={<Info className="size-3.5" aria-hidden="true" />}>
            This warning is resolved. The workflow defines no further transitions from this state.
          </Note>
        ) : permitted.length === 0 ? (
          <Note tone="neutral" icon={<Lock className="size-3.5" aria-hidden="true" />}>
            <span className="font-semibold text-[--color-ink]">
              You cannot act on this warning at its current stage.
            </span>{' '}
            Your role does not carry the capability required to advance a warning from{' '}
            {state.label.toLowerCase()}. You can review the full evidence above.
          </Note>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              {permitted.map((action) => (
                <Button
                  key={action.target}
                  variant={action.consequential ? 'primary' : 'secondary'}
                  onClick={() =>
                    action.consequential ? setPendingAction(action) : run(action)
                  }
                  loading={transition.isPending && transition.variables?.target === action.target}
                  disabled={transition.isPending}
                >
                  {action.consequential && <ShieldCheck className="size-4" aria-hidden="true" />}
                  {action.label}
                </Button>
              ))}
            </div>
            <p className="text-[11px] leading-4 text-[--color-ink-muted]">
              The platform records the decision, the deciding account and the time. The backend
              re-checks your authorisation independently of this screen.
            </p>
          </div>
        )}

        {/* Honest statement about what this workflow does not include. */}
        <details className="group">
          <summary className="inline-flex min-h-6 cursor-pointer list-none items-center text-[12px] font-medium text-[--color-ink-muted] transition-colors hover:text-[--color-ink]">
            Why is there no reject or hold action?
          </summary>
          <p className="mt-2 text-[12px] leading-5 text-[--color-ink-secondary]">
            The governed workflow implemented by this platform advances a warning through review,
            optional field verification, authorised approval and publication. It does not currently
            define a reject or hold transition. To pause a decision pending evidence, use{' '}
            <span className="font-medium">Request Field Verification</span>, which holds the warning
            until field evidence is accepted.
          </p>
        </details>
      </div>

      {pendingAction && (
        <ConfirmDialog
          open
          onClose={() => setPendingAction(null)}
          onConfirm={() => run(pendingAction)}
          title={`${pendingAction.label} this warning?`}
          consequence={pendingAction.consequence}
          confirmLabel={pendingAction.label}
          destructive={pendingAction.target === 'published'}
          pending={transition.isPending}
        >
          <div className="flex flex-col gap-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <RiskBadge level={riskLevel} size="sm" />
              <MetaChip>Moving to {workflow(pendingAction.target).label}</MetaChip>
            </div>
            <p className="text-[13px] leading-5 text-[--color-ink-secondary]">
              This action is attributed to your account and appears in the platform’s audit record.
            </p>
          </div>
        </ConfirmDialog>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ page -- */

export function WarningReviewPage() {
  const { alertId = '' } = useParams();
  const { can } = useAuth();

  const alert = useAlert(alertId);
  // The detail endpoint returns the alert core only; the list carries the
  // geographic and risk context, so both are read and joined here.
  const alerts = useAlerts(true);
  const signals = useRiskSignals({ limit: 1000 }, can('predictions.read'));
  const exposures = useExposureAssessments(can('exposure.read'));

  const listItem: AlertListItem | undefined = useMemo(
    () => (alerts.data ?? []).find((item) => item.id === alertId),
    [alerts.data, alertId],
  );

  const signal: RiskSignal | undefined = useMemo(
    () => (signals.data ?? []).find((item) => item.id === alert.data?.signal_id),
    [signals.data, alert.data?.signal_id],
  );

  const exposure = useMemo(
    () => (exposures.data ?? []).find((item) => item.alert_id === alertId),
    [exposures.data, alertId],
  );

  if (alert.isPending) return <ReviewSkeleton />;

  if (alert.isError) {
    const error = alert.error;
    if (error.kind === 'forbidden') {
      return (
        <div className="flex flex-col gap-5">
          <BackLink />
          <AccessDenied capability="alerts.read" what="this warning" />
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-5">
        <BackLink />
        <ErrorState error={alert.error} onRetry={() => void alert.refetch()} />
      </div>
    );
  }

  const record = alert.data;
  if (!record) return <ReviewSkeleton />;

  const riskLevel = listItem?.risk_level ?? 'unknown';
  const riskDomain = listItem?.risk_domain;
  const state = workflow(record.status);

  // The shared intelligence detail needs a joined row; build one when the
  // underlying signal is readable by this principal.
  const intelligenceRow: IntelligenceRow | null = signal
    ? {
        signal,
        unit: undefined,
        unitName: listItem?.title ?? record.title,
        parentName: undefined,
        level: severity(signal.level).key,
        probability: signal.score,
        degraded: false,
        suppressionReason:
          typeof signal.provenance?.suppression_reason === 'string'
            ? signal.provenance.suppression_reason
            : null,
      }
    : null;

  return (
    <div className="flex flex-col gap-5">
      <BackLink />

      <PageHeader
        eyebrow={riskDomain ? domainDescriptor(riskDomain).label : 'Warning'}
        title={record.title}
        description={record.summary}
        meta={
          <MetaBar>
            <MetaItem label="Workflow state" value={<StatusBadge status={record.status} size="sm" />} />
            <MetaItem label="Severity" value={<RiskBadge level={riskLevel} size="sm" />} />
            <MetaItem
              label="Classification"
              value={<ClassificationBadge classification={record.classification} />}
            />
            {listItem && <MetaItem label="Target period" value={listItem.target_period || '—'} />}
            {listItem && (
              <MetaItem label="Generated" value={formatDateTime(listItem.created_at)} />
            )}
          </MetaBar>
        }
      />

      {/* Governance chain — the distinction the product must never blur. */}
      <Card>
        <div className="flex flex-col gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[--color-ink-faint]">
            Governance
          </p>
          <GovernanceRail status={record.status} />
          {!state.humanApproved && (
            <Note tone="neutral" icon={<Info className="size-3.5" aria-hidden="true" />}>
              This is model-generated intelligence under review. It has{' '}
              <span className="font-semibold">not</span> been approved as an official warning.
            </Note>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)]">
        <div className="flex flex-col gap-4">
          {/* Section 1 — summary */}
          <Panel eyebrow="Section 1" title="Warning summary">
            <DataGrid columns={3}>
              <DataPoint
                label="Risk type"
                value={riskDomain ? domainDescriptor(riskDomain).label : NOT_REPORTED}
              />
              <DataPoint label="Severity" value={<RiskBadge level={riskLevel} size="sm" />} />
              <DataPoint
                label="Modelled probability"
                value={signal ? formatProbability(signal.score) : NOT_REPORTED}
              />
              <DataPoint
                label="Target period"
                value={listItem?.target_period || NOT_REPORTED}
              />
              <DataPoint
                label="Generated"
                value={listItem ? formatDateTime(listItem.created_at) : NOT_REPORTED}
              />
              <DataPoint
                label="Published"
                value={
                  listItem?.published_at ? formatDateTime(listItem.published_at) : 'Not published'
                }
              />
            </DataGrid>
            {riskDomain && (
              <Note
                tone="neutral"
                className="mt-4"
                icon={<Info className="size-3.5" aria-hidden="true" />}
              >
                {domainDescriptor(riskDomain).scopeStatement}
              </Note>
            )}
          </Panel>

          {/* Sections 2–5 come from the shared intelligence detail, which
              already answers where/what/why/how-good in a fixed order. */}
          <Panel eyebrow="Sections 2–5" title="Evidence, data quality and model">
            {intelligenceRow ? (
              <IntelligenceDetail
                row={intelligenceRow}
                exposure={<ExposureBlock exposure={exposure} />}
                recommendedActions={<RecommendedActions alertTitle={record.title} />}
              />
            ) : signals.isPending ? (
              <div className="flex flex-col gap-3">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-24 w-full" />
              </div>
            ) : !can('predictions.read') ? (
              <AccessDenied
                capability="predictions.read"
                what="the underlying model evidence for this warning"
              />
            ) : (
              <EmptyState
                title="Underlying signal not available"
                description="The risk signal referenced by this warning was not returned for your scope. The warning's own record is shown above; the model evidence cannot be displayed."
              />
            )}
          </Panel>
        </div>

        <div className="flex flex-col gap-4">
          {can('alerts.review') ||
          can('alerts.approve') ||
          can('alerts.publish') ||
          can('alerts.resolve') ||
          can('field_tasks.create') ||
          can('field_reports.verify') ? (
            <DecisionPanel alertId={alertId} status={record.status} riskLevel={riskLevel} />
          ) : (
            <Panel eyebrow="Section 6" title="Decision">
              <Note tone="neutral" icon={<Lock className="size-3.5" aria-hidden="true" />}>
                Your role is read-only for warnings. You can review the full evidence but cannot
                change this warning’s state.
              </Note>
            </Panel>
          )}

          <Panel eyebrow="Reference" title="Record identifiers">
            <DataGrid columns={2}>
              <DataPoint
                label="Warning ID"
                value={<code className="font-mono text-[12px]">{record.id.slice(0, 12)}</code>}
              />
              <DataPoint
                label="Signal ID"
                value={<code className="font-mono text-[12px]">{record.signal_id.slice(0, 12)}</code>}
              />
            </DataGrid>
          </Panel>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- fragments -- */

function BackLink() {
  return (
    <Link
      to="/app/warnings"
      className="-mx-1 inline-flex min-h-6 w-fit items-center gap-1.5 rounded-[--radius-xs] px-1 text-[13px] font-medium text-[--color-ink-muted] transition-colors hover:text-[--color-ink]"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
      Back to Warning Center
    </Link>
  );
}

function ExposureBlock({
  exposure,
}: {
  exposure: ReturnType<typeof useExposureAssessments>['data'] extends Array<infer T> | undefined
    ? T | undefined
    : never;
}) {
  if (!exposure) {
    return (
      <p className="text-[13px] leading-5 text-[--color-ink-muted]">
        No exposure assessment has been attached to this warning. No population figure is shown,
        because none has been calculated and attributed to a source.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <DataGrid columns={3}>
        <DataPoint
          label="Population"
          value={formatCompact(exposure.population)}
          hint="People in the assessed area"
        />
        <DataPoint label="Settlements" value={formatCount(exposure.settlements)} />
        <DataPoint
          label="Cropland"
          value={
            exposure.cropland_hectares === null
              ? NOT_REPORTED
              : `${formatCompact(exposure.cropland_hectares)} ha`
          }
        />
      </DataGrid>
      <div className="flex flex-wrap items-center gap-2">
        <ConfidenceIndicator value={exposure.confidence} label="Assessment confidence" />
        {!exposure.lineage_available && (
          <MetaChip title="No source lineage was recorded for this assessment">
            Lineage unavailable
          </MetaChip>
        )}
      </div>
    </div>
  );
}

/**
 * Recommended actions attached to this warning.
 *
 * Actions are grouped by their current workflow status so that a *planned*
 * action is never read as one already carried out — the difference between
 * "we intend to pre-position supplies" and "supplies are pre-positioned" is
 * the whole point of an early-action record.
 *
 * `/early-actions/items` returns items across every plan the principal can
 * read, with no per-alert filter, so items are matched here on the alert title
 * their plan belongs to.
 */
function RecommendedActions({ alertTitle }: { alertTitle: string }) {
  const { can } = useAuth();
  const mayRead = can('early_actions.read');
  const actions = useActionItems(mayRead);

  const matching = useMemo(
    () => (actions.data ?? []).filter((item) => item.alert_title === alertTitle),
    [actions.data, alertTitle],
  );

  const grouped = useMemo(() => {
    const groups = new Map<ActionStatus, typeof matching>();
    for (const item of matching) {
      const existing = groups.get(item.status) ?? [];
      existing.push(item);
      groups.set(item.status, existing);
    }
    return [...groups.entries()].sort(
      (a, b) => ACTION_ORDER.indexOf(a[0]) - ACTION_ORDER.indexOf(b[0]),
    );
  }, [matching]);

  if (!mayRead) {
    return (
      <p className="text-[13px] leading-5 text-[--color-ink-muted]">
        Recommended actions require the early-actions read capability, which your role does not
        carry.
      </p>
    );
  }

  if (actions.isPending) {
    return <Skeleton className="h-20 w-full" />;
  }

  if (actions.isError) {
    return <ErrorState compact error={actions.error} onRetry={() => void actions.refetch()} />;
  }

  if (matching.length === 0) {
    return (
      <Note tone="neutral" icon={<ClipboardList className="size-3.5" aria-hidden="true" />}>
        No early action has been planned against this warning yet. Actions are attached through an
        approved action plan in the early-actions module.
      </Note>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Note tone="neutral" icon={<Info className="size-3.5" aria-hidden="true" />}>
        These are <span className="font-semibold">planned and in-progress actions</span>, not
        completed ones. Status is shown against each item.
      </Note>

      {grouped.map(([status, items]) => (
        <div key={status} className="flex flex-col gap-2">
          <h4 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-[--color-ink-faint]">
            {humanise(status)} · {items.length}
          </h4>
          <ul className="flex flex-col gap-2">
            {items.map((item) => (
              <li
                key={item.id}
                className="flex flex-col gap-1.5 rounded-[--radius-md] bg-[--color-surface-subtle] px-3 py-2.5 ring-1 ring-[--color-line]"
              >
                <p className="text-[13px] leading-5 text-[--color-ink]">{item.description}</p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[--color-ink-muted]">
                  <MetaChip>{humanise(item.status)}</MetaChip>
                  <span>Due {formatDateTime(item.due_at)}</span>
                  {item.blockers.length > 0 && (
                    <span className="text-[--color-risk-warning-fg]">
                      {item.blockers.length} blocker{item.blockers.length === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Display order for action status groups, from least to most advanced. */
const ACTION_ORDER: ActionStatus[] = [
  'planned',
  'assigned',
  'in_progress',
  'blocked',
  'completed',
  'cancelled',
];

function ReviewSkeleton() {
  return (
    <div className="flex flex-col gap-5" aria-busy="true">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-12 w-full" />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)]">
        <div className="flex flex-col gap-4">
          <Skeleton className="h-52" />
          <Skeleton className="h-96" />
        </div>
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}
