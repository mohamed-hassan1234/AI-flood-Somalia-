import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useI18n } from '../../i18n';
import { ApiError, apiRequest } from '../../services/api';

type RiskDomain = 'drought' | 'river_flood' | 'flash_flood' | 'food_security_deterioration';
type RiskLevel = 'normal' | 'watch' | 'warning' | 'critical';

type DomainSummary = {
  domain: RiskDomain;
  level: RiskLevel | null;
  admin_units_evaluated: number;
  target_periods: string[];
  source_ids: string[];
  as_of: string | null;
  stale: boolean;
};

type NationalSummary = {
  generated_at: string;
  boundary_scope: string;
  scope_admin_unit_id: string | null;
  scope_name: string;
  scope_level: string;
  boundary_version: string | null;
  published_warning_count: number;
  domains: DomainSummary[];
};

type DashboardScope = { id: string; name: string; level: string; boundary_version: string };

export function NationalDashboard() {
  const { language, t } = useI18n();
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const [scopeId, setScopeId] = useState('');
  const scopes = useQuery({
    queryKey: ['dashboard-scopes'],
    queryFn: () => apiRequest<DashboardScope[]>('/dashboard/scopes'),
    enabled: authenticated,
  });
  const summary = useQuery({
    queryKey: ['executive-summary', scopeId],
    queryFn: () => apiRequest<NationalSummary>(`/dashboard/national-summary${scopeId ? `?admin_unit_id=${scopeId}` : ''}`),
    enabled: authenticated,
  });

  return (
    <main>
      <p className="eyebrow">{t('executiveEyebrow')}</p>
      <h1>{t('trustedEvidence')}<br /><span>{t('earlierAction')}</span></h1>
      <p className="lead">{t('executiveLead')}</p>

      {authenticated && scopes.data && (
        <label>
          {t('executiveGeography')}
          <select aria-label={t('executiveGeography')} value={scopeId} onChange={(event) => setScopeId(event.target.value)}>
            <option value="">{t('national')}</option>
            {scopes.data.map((scope) => <option key={scope.id} value={scope.id}>{scope.name} ({scope.level})</option>)}
          </select>
        </label>
      )}

      {!authenticated && (
        <div className="empty unauthorized" role="status">
          <b>{t('signInRequired')}</b>
          <p>{t('nationalRestricted')}</p>
        </div>
      )}
      {authenticated && summary.isPending && <div className="empty">{t('loadingEvidence')}</div>}
      {summary.isError && (
        <div className="empty error" role="alert">
          <b>{summary.error instanceof ApiError && [401, 403].includes(summary.error.status) ? t('accessNotAuthorized') : t('summaryUnavailable')}</b>
          <p>{summary.error.message}</p>
        </div>
      )}
      {summary.data && (
        <>
          <div className="summary-meta">
            <span>{summary.data.scope_name} · {summary.data.scope_level}</span>
            <span>{t('publishedWarnings', { count: summary.data.published_warning_count })}</span>
            <span>{summary.data.boundary_scope}</span>
            {summary.data.boundary_version && <span>{t('boundary', { version: summary.data.boundary_version })}</span>}
          </div>
          <section className="domain-grid" aria-label={t('currentRiskDomains')}>
            {summary.data.domains.map((domain, index) => (
              <article className={domain.stale ? 'stale' : ''} key={domain.domain}>
                <b>0{index + 1}</b>
                <h2>{t(domain.domain === 'food_security_deterioration' ? 'foodSecurity' : domain.domain === 'river_flood' ? 'riverFlood' : domain.domain === 'flash_flood' ? 'flashFlood' : 'drought')}</h2>
                <p className={`risk-level ${domain.level ?? 'unknown'}`}>{domain.level ?? t('unknown')}</p>
                <p>{domain.admin_units_evaluated ? t('areasEvaluated', { count: domain.admin_units_evaluated }) : t('noEvidence')}</p>
                <small>{domain.stale ? t('stale') : t('current')} · {t('sources', { count: domain.source_ids.length })}</small>
                {domain.as_of && <time dateTime={domain.as_of}>{t('asOf', { date: new Date(domain.as_of).toLocaleString(language === 'so' ? 'so-SO' : 'en') })}</time>}
              </article>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
