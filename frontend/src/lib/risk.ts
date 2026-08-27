/**
 * Risk semantics — the single source of truth for how severity, domain scope,
 * data quality and workflow state are named and coloured across the product.
 *
 * Two rules this module exists to enforce:
 *
 * 1. A severity colour means exactly one thing everywhere it appears (map,
 *    table, badge, chart, card). Severity colour is never decorative.
 * 2. Severity is never communicated by colour alone — every descriptor here
 *    carries a text label and a glyph so the meaning survives greyscale,
 *    colour-vision deficiency and screen readers.
 */

import type {
  AlertStatus,
  Classification,
  HealthStatus,
  RiskDomain,
  RiskLevel,
} from '../types/api';

/* ------------------------------------------------------------- severity -- */

/**
 * Presentational severity. Extends the backend `RiskLevel` with `unknown`,
 * used when the model withheld a prediction because input quality was
 * insufficient. `unknown` is a real operational state, not an error.
 */
export type Severity = RiskLevel | 'unknown';

export interface SeverityDescriptor {
  key: Severity;
  /** Uppercase operational label, e.g. `WARNING`. */
  label: string;
  /** Non-colour redundant encoding, per WCAG 1.4.1. */
  glyph: string;
  /** Tailwind classes for a badge/pill surface. */
  chip: string;
  /** Tailwind text colour for standalone use. */
  text: string;
  /** Solid fill used by map layers and chart marks. */
  solid: string;
  /** Left accent border for rows and cards. */
  accent: string;
  /** Ordering weight, ascending by operational urgency. */
  rank: number;
  /** Plain-language meaning shown in legends and tooltips. */
  meaning: string;
}

const SEVERITY: Record<Severity, SeverityDescriptor> = {
  normal: {
    key: 'normal',
    label: 'NORMAL',
    glyph: '●',
    chip: 'bg-[--color-risk-normal-bg] text-[--color-risk-normal-fg] ring-1 ring-inset ring-[--color-risk-normal-line]',
    text: 'text-[--color-risk-normal-fg]',
    solid: 'var(--color-risk-normal-solid)',
    accent: 'border-l-[--color-risk-normal-solid]',
    rank: 0,
    meaning: 'No elevated risk signal for this period.',
  },
  watch: {
    key: 'watch',
    label: 'WATCH',
    glyph: '◆',
    chip: 'bg-[--color-risk-watch-bg] text-[--color-risk-watch-fg] ring-1 ring-inset ring-[--color-risk-watch-line]',
    text: 'text-[--color-risk-watch-fg]',
    solid: 'var(--color-risk-watch-solid)',
    accent: 'border-l-[--color-risk-watch-solid]',
    rank: 1,
    meaning: 'Conditions are trending unfavourably. Increase monitoring.',
  },
  warning: {
    key: 'warning',
    label: 'WARNING',
    glyph: '▲',
    chip: 'bg-[--color-risk-warning-bg] text-[--color-risk-warning-fg] ring-1 ring-inset ring-[--color-risk-warning-line]',
    text: 'text-[--color-risk-warning-fg]',
    solid: 'var(--color-risk-warning-solid)',
    accent: 'border-l-[--color-risk-warning-solid]',
    rank: 2,
    meaning: 'Threshold exceeded. Preparedness action is indicated.',
  },
  critical: {
    key: 'critical',
    label: 'CRITICAL',
    glyph: '▲',
    chip: 'bg-[--color-risk-critical-bg] text-[--color-risk-critical-fg] ring-1 ring-inset ring-[--color-risk-critical-line]',
    text: 'text-[--color-risk-critical-fg]',
    solid: 'var(--color-risk-critical-solid)',
    accent: 'border-l-[--color-risk-critical-solid]',
    rank: 3,
    meaning: 'Highest modelled severity. Immediate review required.',
  },
  unknown: {
    key: 'unknown',
    label: 'UNKNOWN',
    glyph: '—',
    chip: 'bg-[--color-risk-unknown-bg] text-[--color-risk-unknown-fg] ring-1 ring-inset ring-[--color-risk-unknown-line]',
    text: 'text-[--color-risk-unknown-fg]',
    solid: 'var(--color-risk-unknown-solid)',
    accent: 'border-l-[--color-risk-unknown-solid]',
    rank: -1,
    meaning: 'No prediction was issued — model input quality was insufficient.',
  },
};

/**
 * Normalises any severity spelling the platform may produce into the
 * presentational vocabulary.
 *
 * The Phase 03 operational contract writes `SEVERE`; the backend enum
 * (`app.core.enums.RiskLevel`) writes `critical`. They denote the same top
 * severity band, so both resolve here rather than silently degrading to
 * `unknown` — which would understate a real emergency.
 */
export function toSeverity(value: string | null | undefined): Severity {
  if (value === null || value === undefined) return 'unknown';
  const key = value.trim().toLowerCase();
  if (key === 'severe') return 'critical';
  if (key === 'insufficient' || key === '') return 'unknown';
  return key in SEVERITY ? (key as Severity) : 'unknown';
}

export function severity(value: string | null | undefined): SeverityDescriptor {
  return SEVERITY[toSeverity(value)];
}

/** Ascending operational urgency; `unknown` sorts below `normal`. */
export function severityRank(value: string | null | undefined): number {
  return severity(value).rank;
}

/** Severities at or above WATCH — the "Watch+" counting convention. */
export const WATCH_PLUS: Severity[] = ['watch', 'warning', 'critical'];
/** Severities at or above WARNING — the "Warning+" counting convention. */
export const WARNING_PLUS: Severity[] = ['warning', 'critical'];

export function isWatchPlus(value: string | null | undefined): boolean {
  return severityRank(value) >= 1;
}

export function isWarningPlus(value: string | null | undefined): boolean {
  return severityRank(value) >= 2;
}

/** Highest severity present, or `unknown` when the set is empty. */
export function highestSeverity(values: Array<string | null | undefined>): Severity {
  let best: Severity = 'unknown';
  for (const value of values) {
    if (severityRank(value) > severityRank(best)) best = toSeverity(value);
  }
  return best;
}

/** Ordered list for legends and filter controls, most urgent first. */
export const SEVERITY_ORDER: Severity[] = ['critical', 'warning', 'watch', 'normal', 'unknown'];

export function severityDescriptors(): SeverityDescriptor[] {
  return SEVERITY_ORDER.map((key) => SEVERITY[key]);
}

/* --------------------------------------------------------------- domain -- */

/**
 * Geographic scope at which each risk domain is actually modelled.
 *
 * This is a scientific constraint from
 * `docs/contracts/operational-intelligence-contract.md`, not a display
 * preference. The UI must never imply spatial precision the model does not
 * provide — no nationwide flood polygons from five gauges, no district-level
 * food-security predictions from a region-level model.
 */
export type DomainScope = 'district' | 'station' | 'region';

export interface DomainDescriptor {
  key: RiskDomain;
  /** Short label used in navigation and chips. */
  label: string;
  /** Full operational name used in page titles. */
  longLabel: string;
  scope: DomainScope;
  /** Noun for one modelled unit, e.g. "district", "river gauge". */
  unitNoun: string;
  unitNounPlural: string;
  /**
   * The honest, user-facing statement of what this domain does and does not
   * cover. Rendered near every risk display — never buried in a tooltip.
   */
  scopeStatement: string;
}

const DOMAIN: Record<RiskDomain, DomainDescriptor> = {
  drought: {
    key: 'drought',
    label: 'Drought',
    longLabel: 'Drought Intelligence',
    scope: 'district',
    unitNoun: 'district',
    unitNounPlural: 'districts',
    scopeStatement:
      'District-level drought risk signal. This is an early-warning indicator of deteriorating ' +
      'agro-climatic conditions — it is not a famine forecast and not an IPC classification.',
  },
  river_flood: {
    key: 'river_flood',
    label: 'River Flood',
    longLabel: 'River Flood Intelligence',
    scope: 'station',
    unitNoun: 'river gauge',
    unitNounPlural: 'river gauges',
    scopeStatement:
      'Riverine early warning at supported Jubba and Shabelle gauging stations only. ' +
      'Coverage is tied to the gauges themselves — this is not Somalia-wide flood coverage ' +
      'and does not cover flash or surface flooding.',
  },
  flash_flood: {
    key: 'flash_flood',
    label: 'Flash Flood',
    longLabel: 'Flash Flood Intelligence',
    scope: 'district',
    unitNoun: 'area',
    unitNounPlural: 'areas',
    scopeStatement:
      'Flash-flood signals are reported only where the platform holds validated inputs for the ' +
      'area shown. Absence of a signal is not evidence of absence of flash-flood risk.',
  },
  food_security_deterioration: {
    key: 'food_security_deterioration',
    label: 'Food Security',
    longLabel: 'Food Security Intelligence',
    scope: 'region',
    unitNoun: 'region',
    unitNounPlural: 'regions',
    scopeStatement:
      'Region-level model early-warning signal for food-security deterioration. It is not an ' +
      'official IPC classification and must not be reported as one. No validated methodology ' +
      'exists to disaggregate this signal to district level.',
  },
};

export function domain(key: RiskDomain): DomainDescriptor {
  return DOMAIN[key];
}

export function domainLabel(key: string): string {
  return key in DOMAIN
    ? DOMAIN[key as RiskDomain].label
    : String(key).replaceAll('_', ' ');
}

export const DOMAIN_ORDER: RiskDomain[] = [
  'drought',
  'river_flood',
  'flash_flood',
  'food_security_deterioration',
];

export function domainDescriptors(): DomainDescriptor[] {
  return DOMAIN_ORDER.map((key) => DOMAIN[key]);
}

/* ------------------------------------------------------- workflow state -- */

/**
 * Governance stage of an alert. The product must never let a model output
 * read as a government-approved warning, so each state declares plainly
 * whether human authorisation has happened yet.
 */
export interface WorkflowDescriptor {
  key: AlertStatus;
  label: string;
  /** Where this sits in the governance chain, for the progress rail. */
  step: number;
  /** True once an authorised human has approved the content. */
  humanApproved: boolean;
  /** True once the warning is externally visible. */
  published: boolean;
  chip: string;
  description: string;
}

const WORKFLOW: Record<AlertStatus, WorkflowDescriptor> = {
  draft: {
    key: 'draft',
    label: 'Draft',
    step: 0,
    humanApproved: false,
    published: false,
    chip: 'bg-[--color-muted-bg] text-[--color-muted-fg] ring-1 ring-inset ring-[--color-muted-line]',
    description: 'AI-generated candidate. Not yet submitted for analyst review.',
  },
  in_review: {
    key: 'in_review',
    label: 'In Review',
    step: 1,
    humanApproved: false,
    published: false,
    chip: 'bg-[--color-info-bg] text-[--color-info-fg] ring-1 ring-inset ring-[--color-info-line]',
    description: 'Under analyst review. No approval has been given.',
  },
  verification_required: {
    key: 'verification_required',
    label: 'Verification Required',
    step: 2,
    humanApproved: false,
    published: false,
    chip: 'bg-[--color-risk-watch-bg] text-[--color-risk-watch-fg] ring-1 ring-inset ring-[--color-risk-watch-line]',
    description: 'Field verification requested before a decision can be made.',
  },
  verified: {
    key: 'verified',
    label: 'Verified',
    step: 3,
    humanApproved: false,
    published: false,
    chip: 'bg-[--color-info-bg] text-[--color-info-fg] ring-1 ring-inset ring-[--color-info-line]',
    description: 'Field evidence accepted. Awaiting authorised approval.',
  },
  approved: {
    key: 'approved',
    label: 'Approved',
    step: 4,
    humanApproved: true,
    published: false,
    chip: 'bg-[--color-ok-bg] text-[--color-ok-fg] ring-1 ring-inset ring-[--color-ok-line]',
    description: 'Authorised for publication. Not yet published.',
  },
  published: {
    key: 'published',
    label: 'Published',
    step: 5,
    humanApproved: true,
    published: true,
    chip: 'bg-[--color-brand-50] text-[--color-brand-700] ring-1 ring-inset ring-[--color-brand-200]',
    description: 'Published warning, visible to its authorised audience.',
  },
  resolved: {
    key: 'resolved',
    label: 'Resolved',
    step: 6,
    humanApproved: true,
    published: true,
    chip: 'bg-[--color-muted-bg] text-[--color-muted-fg] ring-1 ring-inset ring-[--color-muted-line]',
    description: 'The event window has closed. Retained for the record.',
  },
};

export function workflow(status: AlertStatus): WorkflowDescriptor {
  return WORKFLOW[status] ?? WORKFLOW.draft;
}

/** Governance chain rendered in the review workspace progress rail. */
export const GOVERNANCE_CHAIN: AlertStatus[] = [
  'draft',
  'in_review',
  'verified',
  'approved',
  'published',
];

/**
 * Permitted state transitions, mirroring
 * `backend/app/modules/alerts/service.py::TRANSITIONS`.
 *
 * The backend is authoritative — this table exists so the UI can avoid
 * offering an action that would be rejected, not to make the decision.
 */
export const ALERT_TRANSITIONS: Record<AlertStatus, AlertStatus[]> = {
  draft: ['in_review'],
  in_review: ['verification_required', 'approved'],
  verification_required: ['verified'],
  verified: ['approved'],
  approved: ['published'],
  published: ['resolved'],
  resolved: [],
};

/**
 * Capability required to move an alert *into* each state, mirroring
 * `backend/app/modules/alerts/service.py::REQUIRED_CAPABILITY`.
 */
export const TRANSITION_CAPABILITY: Record<AlertStatus, string | null> = {
  draft: null,
  in_review: 'alerts.review',
  verification_required: 'field_tasks.create',
  verified: 'field_reports.verify',
  approved: 'alerts.approve',
  published: 'alerts.publish',
  resolved: 'alerts.resolve',
};

/**
 * Transitions that change what the outside world sees, or that formally
 * commit the institution. These require an explicit confirmation step —
 * publishing must never be a casual single click.
 */
export const CONSEQUENTIAL_TRANSITIONS: AlertStatus[] = ['approved', 'published', 'resolved'];

export interface TransitionAction {
  target: AlertStatus;
  label: string;
  capability: string;
  consequential: boolean;
  /** Sentence shown in the confirmation dialog. */
  consequence: string;
}

const TRANSITION_COPY: Record<AlertStatus, { label: string; consequence: string }> = {
  draft: { label: 'Return to Draft', consequence: '' },
  in_review: {
    label: 'Submit for Review',
    consequence: 'This moves the candidate into the analyst review queue.',
  },
  verification_required: {
    label: 'Request Field Verification',
    consequence:
      'This holds the decision and requests field verification before the warning can advance.',
  },
  verified: {
    label: 'Accept Field Evidence',
    consequence: 'This records that submitted field evidence has been accepted.',
  },
  approved: {
    label: 'Approve',
    consequence:
      'Approval is an authorised institutional decision. It records you as the approver and ' +
      'makes the warning eligible for publication.',
  },
  published: {
    label: 'Publish',
    consequence:
      'Publishing makes this warning visible to its authorised audience and may trigger ' +
      'downstream notification. This cannot be undone from this screen.',
  },
  resolved: {
    label: 'Resolve',
    consequence: 'This closes the event window and archives the warning as resolved.',
  },
};

/**
 * The transitions a given principal may actually perform from the current
 * state. Returns an empty list when the user lacks every required capability
 * — callers should then render a read-only notice rather than a disabled row
 * of buttons, which reads as a system fault rather than a permission boundary.
 */
export function availableTransitions(
  status: AlertStatus,
  capabilities: ReadonlySet<string>,
): TransitionAction[] {
  return (ALERT_TRANSITIONS[status] ?? [])
    .map((target) => {
      const capability = TRANSITION_CAPABILITY[target];
      if (!capability) return null;
      const copy = TRANSITION_COPY[target];
      return {
        target,
        label: copy.label,
        capability,
        consequential: CONSEQUENTIAL_TRANSITIONS.includes(target),
        consequence: copy.consequence,
      } satisfies TransitionAction;
    })
    .filter((action): action is TransitionAction => action !== null)
    .filter((action) => capabilities.has(action.capability));
}

/** Every transition defined from this state, regardless of capability. */
export function allTransitions(status: AlertStatus): TransitionAction[] {
  return availableTransitions(status, new Set(Object.values(TRANSITION_CAPABILITY).filter(Boolean) as string[]));
}

/* ----------------------------------------------------------- data health -- */

export interface HealthDescriptor {
  key: HealthStatus;
  label: string;
  glyph: string;
  chip: string;
  dot: string;
  /** True when this status should reduce confidence in dependent output. */
  degraded: boolean;
  meaning: string;
}

const HEALTH: Record<HealthStatus, HealthDescriptor> = {
  fresh: {
    key: 'fresh',
    label: 'FRESH',
    glyph: '●',
    chip: 'bg-[--color-ok-bg] text-[--color-ok-fg] ring-1 ring-inset ring-[--color-ok-line]',
    dot: 'bg-[--color-risk-normal-solid]',
    degraded: false,
    meaning: 'Last successful retrieval is within this source’s expected cadence.',
  },
  delayed: {
    key: 'delayed',
    label: 'DELAYED',
    glyph: '◆',
    chip: 'bg-[--color-risk-watch-bg] text-[--color-risk-watch-fg] ring-1 ring-inset ring-[--color-risk-watch-line]',
    dot: 'bg-[--color-risk-watch-solid]',
    degraded: true,
    meaning: 'Retrieval is late but within twice the expected cadence.',
  },
  stale: {
    key: 'stale',
    label: 'STALE',
    glyph: '▲',
    chip: 'bg-[--color-risk-warning-bg] text-[--color-risk-warning-fg] ring-1 ring-inset ring-[--color-risk-warning-line]',
    dot: 'bg-[--color-risk-warning-solid]',
    degraded: true,
    meaning: 'Outside the accepted freshness window. Dependent output is degraded.',
  },
  failed: {
    key: 'failed',
    label: 'FAILED',
    glyph: '■',
    chip: 'bg-[--color-danger-bg] text-[--color-danger-fg] ring-1 ring-inset ring-[--color-danger-line]',
    dot: 'bg-[--color-risk-critical-solid]',
    degraded: true,
    meaning: 'The most recent ingestion attempt failed.',
  },
  unknown: {
    key: 'unknown',
    label: 'UNKNOWN',
    glyph: '—',
    chip: 'bg-[--color-risk-unknown-bg] text-[--color-risk-unknown-fg] ring-1 ring-inset ring-[--color-risk-unknown-line]',
    dot: 'bg-[--color-risk-unknown-solid]',
    degraded: true,
    meaning: 'No successful retrieval has been recorded for this source.',
  },
};

export function health(status: string | null | undefined): HealthDescriptor {
  const key = String(status ?? 'unknown').toLowerCase();
  return HEALTH[key as HealthStatus] ?? HEALTH.unknown;
}

export const HEALTH_ORDER: HealthStatus[] = ['failed', 'stale', 'delayed', 'fresh', 'unknown'];

/* ---------------------------------------------------------- data quality -- */

export type QualityStatus = 'good' | 'partial' | 'stale' | 'insufficient' | 'unknown';

export interface QualityDescriptor {
  key: QualityStatus;
  label: string;
  glyph: string;
  chip: string;
  meaning: string;
}

const QUALITY: Record<QualityStatus, QualityDescriptor> = {
  good: {
    key: 'good',
    label: 'GOOD',
    glyph: '●',
    chip: 'bg-[--color-ok-bg] text-[--color-ok-fg] ring-1 ring-inset ring-[--color-ok-line]',
    meaning: 'All required model inputs were available and within range.',
  },
  partial: {
    key: 'partial',
    label: 'PARTIAL',
    glyph: '◆',
    chip: 'bg-[--color-risk-watch-bg] text-[--color-risk-watch-fg] ring-1 ring-inset ring-[--color-risk-watch-line]',
    meaning: 'Some model inputs were missing or degraded. Interpret with caution.',
  },
  stale: {
    key: 'stale',
    label: 'STALE',
    glyph: '▲',
    chip: 'bg-[--color-risk-warning-bg] text-[--color-risk-warning-fg] ring-1 ring-inset ring-[--color-risk-warning-line]',
    meaning: 'One or more required inputs are outside their freshness window.',
  },
  insufficient: {
    key: 'insufficient',
    label: 'INSUFFICIENT',
    glyph: '■',
    chip: 'bg-[--color-danger-bg] text-[--color-danger-fg] ring-1 ring-inset ring-[--color-danger-line]',
    meaning: 'Input quality was too low to issue a prediction. No risk level was assigned.',
  },
  unknown: {
    key: 'unknown',
    label: 'NOT REPORTED',
    glyph: '—',
    chip: 'bg-[--color-risk-unknown-bg] text-[--color-risk-unknown-fg] ring-1 ring-inset ring-[--color-risk-unknown-line]',
    meaning: 'The API did not report a data-quality status for this record.',
  },
};

export function quality(value: string | null | undefined): QualityDescriptor {
  const key = String(value ?? '').toLowerCase();
  return QUALITY[key as QualityStatus] ?? QUALITY.unknown;
}

/* -------------------------------------------------------- classification -- */

export function classificationLabel(value: string): string {
  switch (value) {
    case 'internal':
      return 'Internal';
    case 'partner':
      return 'Partner';
    case 'public':
      return 'Public';
    default:
      return String(value);
  }
}

export const CLASSIFICATION_CHIP: Record<Classification, string> = {
  internal:
    'bg-[--color-muted-bg] text-[--color-muted-fg] ring-1 ring-inset ring-[--color-muted-line]',
  partner:
    'bg-[--color-info-bg] text-[--color-info-fg] ring-1 ring-inset ring-[--color-info-line]',
  public:
    'bg-[--color-brand-50] text-[--color-brand-700] ring-1 ring-inset ring-[--color-brand-200]',
};
