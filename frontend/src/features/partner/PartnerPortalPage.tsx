import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type Warning = { id: string; title: string; summary: string; classification: string; risk_domain: string; risk_level: string; target_period: string; published_at: string };
type Report = { id: string; title: string; reporting_period: string; boundary_version: string; classification: string; findings: string[]; recommendations: string[]; published_at: string };

export function PartnerPortalPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const products = useQuery({
    queryKey: ['partner-products'],
    queryFn: async () => {
      const [warnings, reports] = await Promise.all([
        apiRequest<Warning[]>('/alerts/partner-warnings'), apiRequest<Report[]>('/reports'),
      ]);
      return { warnings, reports };
    },
    enabled: authenticated,
  });
  return <main><p className="eyebrow">PARTNER PORTAL</p><h1>Published partner products</h1>
    <p className="lead">A least-data workspace containing only published warnings and reports within the current membership’s geography and classification ceiling.</p>
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Partner products require an authorized membership.</p></div>}
    {authenticated && products.isPending && <div className="empty">Loading scoped partner products…</div>}
    {products.isError && <div className="empty error" role="alert"><b>{products.error instanceof ApiError && [401, 403].includes(products.error.status) ? 'Access not authorized' : 'Partner portal unavailable'}</b><p>{products.error.message}</p></div>}
    {products.data && products.data.warnings.length + products.data.reports.length === 0 && <div className="empty"><b>No published products in scope</b><p>Draft and inaccessible records are never shown here.</p></div>}
    {products.data && <section className="task-list" aria-label="Published partner products">
      {products.data.warnings.map((warning) => <article key={warning.id}><div className="task-heading"><span>warning · {warning.risk_domain.replaceAll('_', ' ')}</span><strong>{warning.classification}</strong></div><h2>{warning.title}</h2><p>{warning.summary}</p><dl><div><dt>Risk</dt><dd>{warning.risk_level}</dd></div><div><dt>Period</dt><dd>{warning.target_period}</dd></div><div><dt>Published</dt><dd>{new Date(warning.published_at).toLocaleString()}</dd></div></dl></article>)}
      {products.data.reports.map((report) => <article key={report.id}><div className="task-heading"><span>report · {report.reporting_period}</span><strong>{report.classification}</strong></div><h2>{report.title}</h2><p>Boundary {report.boundary_version}</p><dl><div><dt>Findings</dt><dd>{report.findings.join('; ') || 'None recorded'}</dd></div><div><dt>Recommendations</dt><dd>{report.recommendations.join('; ') || 'None recorded'}</dd></div><div><dt>Published</dt><dd>{new Date(report.published_at).toLocaleString()}</dd></div></dl></article>)}
    </section>}
  </main>;
}
