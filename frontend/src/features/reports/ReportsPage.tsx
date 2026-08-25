import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type Report = {
  id: string; title: string; reporting_period: string; admin_unit_id: string;
  admin_unit_name?: string; boundary_version: string; classification?: string; status?: string;
  sections: Array<{ heading: string; body: string }>; findings: string[];
  recommendations: string[]; published_at: string;
};

export function ReportsPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const reports = useQuery({ queryKey: ['reports', authenticated], queryFn: () => apiRequest<Report[]>(authenticated ? '/reports' : '/public/reports') });
  return <main><p className="eyebrow">REPORTS</p><h1>{authenticated ? 'Governed report library' : 'Public reports'}</h1><p className="lead">Published reporting with explicit period, geography, boundary version, findings, and recommendations. Access follows report classification.</p>
    {reports.isPending && <div className="empty">Loading published reports…</div>}
    {reports.isError && <div className="empty error" role="alert"><b>{reports.error instanceof ApiError && [401, 403].includes(reports.error.status) ? 'Access not authorized' : 'Reports unavailable'}</b><p>{reports.error.message}</p></div>}
    {reports.data?.length === 0 && <div className="empty"><b>No published reports available</b><p>No reports are currently visible at this access level.</p></div>}
    {reports.data && reports.data.length > 0 && <section className="task-list" aria-label="Published reports">{reports.data.map((report) => <article key={report.id}><div className="task-heading"><span>{report.reporting_period}</span><strong>{report.classification ?? 'public'}</strong></div><h2>{report.title}</h2><p>{report.admin_unit_name ?? 'Scoped administrative unit'} · boundary {report.boundary_version}</p>{report.sections.map((section) => <section key={section.heading}><h3>{section.heading}</h3><p>{section.body}</p></section>)}<dl><div><dt>Findings</dt><dd>{report.findings.length ? report.findings.join('; ') : 'None recorded'}</dd></div><div><dt>Recommendations</dt><dd>{report.recommendations.length ? report.recommendations.join('; ') : 'None recorded'}</dd></div><div><dt>Published</dt><dd>{new Date(report.published_at).toLocaleString()}</dd></div></dl></article>)}</section>}
  </main>;
}
