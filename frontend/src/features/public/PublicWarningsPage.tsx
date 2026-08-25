import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../services/api';

type PublicWarning = {
  id: string;
  title: string;
  summary: string;
  risk_domain: string;
  risk_level: string;
  target_period: string;
  admin_unit_id: string;
  admin_unit_name: string;
  boundary_version: string;
  published_at: string;
};

export function PublicWarningsPage() {
  const warnings = useQuery({
    queryKey: ['public-warnings'],
    queryFn: () => apiRequest<PublicWarning[]>('/public/warnings'),
  });

  return (
    <main>
      <p className="eyebrow">PUBLIC EARLY WARNING</p>
      <h1>Published warnings</h1>
      <p className="lead">Official public warnings approved through the national early-warning workflow.</p>
      {warnings.isPending && <div className="empty">Loading published warnings…</div>}
      {warnings.isError && <div className="empty error" role="alert">Published warnings are temporarily unavailable. Please try again later.</div>}
      {warnings.data?.length === 0 && <div className="empty"><b>No active public warnings</b><p>Only approved and published public warnings appear here.</p></div>}
      {warnings.data && warnings.data.length > 0 && (
        <section className="warning-list" aria-label="Published warnings">
          {warnings.data.map((warning) => (
            <article key={warning.id}>
              <div className="warning-meta"><span>{warning.risk_domain.replaceAll('_', ' ')}</span><strong>{warning.risk_level}</strong></div>
              <h2>{warning.title}</h2><p>{warning.summary}</p>
              <dl>
                <div><dt>Area</dt><dd>{warning.admin_unit_name}</dd></div>
                <div><dt>Period</dt><dd>{warning.target_period}</dd></div>
                <div><dt>Published</dt><dd>{new Date(warning.published_at).toLocaleString()}</dd></div>
              </dl>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
