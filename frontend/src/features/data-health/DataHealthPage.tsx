import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type DataSource = {
  id: string;
  name: string;
  domain: string;
  owner: string | null;
  license: string | null;
  access_method: string;
  expected_frequency_minutes: number | null;
  geographic_resolution: string | null;
  classification: 'internal' | 'partner' | 'public';
  verified: boolean;
  enabled: boolean;
};

type SourceHealth = {
  source_id: string;
  status: 'fresh' | 'delayed' | 'stale' | 'failed' | 'unknown';
  last_success: string | null;
  last_run_status: string | null;
  rows_received: number;
  rows_quarantined: number;
};

type SourceWithHealth = DataSource & { health: SourceHealth };

async function loadSourceHealth(): Promise<SourceWithHealth[]> {
  const sources = await apiRequest<DataSource[]>('/data-sources');
  return Promise.all(sources.map(async (source) => ({
    ...source,
    health: await apiRequest<SourceHealth>(`/data-sources/${source.id}/health`),
  })));
}

export function DataHealthPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const sources = useQuery({
    queryKey: ['data-source-health'],
    queryFn: loadSourceHealth,
    enabled: authenticated,
  });

  return (
    <main>
      <p className="eyebrow">DATA HEALTH</p>
      <h1>Source reliability</h1>
      <p className="lead">Freshness, ingestion outcomes, quarantine volume, verification, license, and ownership for governed evidence sources.</p>
      {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Source operations are restricted to authorized users.</p></div>}
      {authenticated && sources.isPending && <div className="empty">Loading source health…</div>}
      {sources.isError && (
        <div className="empty error" role="alert">
          <b>{sources.error instanceof ApiError && [401, 403].includes(sources.error.status) ? 'Access not authorized' : 'Source health unavailable'}</b>
          <p>{sources.error.message}</p>
        </div>
      )}
      {sources.data?.length === 0 && <div className="empty"><b>No registered sources</b><p>Register and verify an authorized source before ingestion.</p></div>}
      {sources.data && sources.data.length > 0 && (
        <section className="health-list" aria-label="Data source health">
          {sources.data.map((source) => (
            <article key={source.id} className={`health-${source.health.status}`}>
              <div className="health-heading"><span>{source.domain}</span><strong>{source.health.status}</strong></div>
              <h2>{source.name}</h2>
              <p>{source.owner ?? 'Owner not recorded'} · {source.geographic_resolution ?? 'Resolution not recorded'}</p>
              <dl>
                <div><dt>Verified</dt><dd>{source.verified ? 'Yes' : 'No'}</dd></div>
                <div><dt>Last success</dt><dd>{source.health.last_success ? new Date(source.health.last_success).toLocaleString() : 'Never'}</dd></div>
                <div><dt>Rows received</dt><dd>{source.health.rows_received}</dd></div>
                <div><dt>Quarantined</dt><dd>{source.health.rows_quarantined}</dd></div>
              </dl>
              <small>{source.license ?? 'LICENSE NOT RECORDED'} · {source.classification.toUpperCase()}</small>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
