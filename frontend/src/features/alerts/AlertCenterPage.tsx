import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type AlertItem = {
  id: string;
  signal_id: string;
  status: 'draft' | 'in_review' | 'verification_required' | 'verified' | 'approved' | 'published' | 'resolved';
  classification: 'internal' | 'partner' | 'public';
  title: string;
  summary: string;
  admin_unit_id: string;
  risk_domain: string;
  risk_level: string;
  target_period: string;
  created_at: string;
  published_at: string | null;
};

export function AlertCenterPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const alerts = useQuery({
    queryKey: ['alerts'],
    queryFn: () => apiRequest<AlertItem[]>('/alerts'),
    enabled: authenticated,
  });

  return (
    <main>
      <p className="eyebrow">ALERT CENTER</p>
      <h1>Governed warnings</h1>
      <p className="lead">Risk severity and publication workflow remain separate. Every visible alert is filtered through capability, classification, and geography.</p>
      {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Alert workflow data is restricted to authorized users.</p></div>}
      {authenticated && alerts.isPending && <div className="empty">Loading scoped alerts…</div>}
      {alerts.isError && <div className="empty error" role="alert"><b>{alerts.error instanceof ApiError && [401, 403].includes(alerts.error.status) ? 'Access not authorized' : 'Alert center unavailable'}</b><p>{alerts.error.message}</p></div>}
      {alerts.data?.length === 0 && <div className="empty"><b>No alerts in scope</b><p>No governed alert records are visible to this membership.</p></div>}
      {alerts.data && alerts.data.length > 0 && (
        <section className="alert-list" aria-label="Scoped alerts">
          {alerts.data.map((alert) => (
            <article key={alert.id}>
              <div className="alert-heading"><span>{alert.risk_domain.replaceAll('_', ' ')}</span><strong className={`severity-${alert.risk_level}`}>{alert.risk_level}</strong></div>
              <h2>{alert.title}</h2><p>{alert.summary}</p>
              <div className="workflow-state"><span>Workflow</span><b>{alert.status.replaceAll('_', ' ')}</b><span>{alert.classification}</span></div>
              <dl><div><dt>Target period</dt><dd>{alert.target_period}</dd></div><div><dt>Created</dt><dd>{new Date(alert.created_at).toLocaleString()}</dd></div><div><dt>Published</dt><dd>{alert.published_at ? new Date(alert.published_at).toLocaleString() : 'Not published'}</dd></div></dl>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
