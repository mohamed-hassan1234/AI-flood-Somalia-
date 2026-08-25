import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type Assessment = { id: string; alert_title: string; classification: string; risk_domain: string; risk_level: string; population: number | null; settlements: number | null; cropland_hectares: number | null; infrastructure: Record<string, unknown>; confidence: number | null; lineage_available: boolean };

export function ExposurePage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const assessments = useQuery({ queryKey: ['exposure-assessments'], queryFn: () => apiRequest<Assessment[]>('/exposure/assessments'), enabled: authenticated });
  return <main><p className="eyebrow">EXPOSURE</p><h1>People and assets potentially affected</h1><p className="lead">Scoped exposure estimates linked to published warnings. Missing measurements remain unknown and confidence is shown explicitly.</p>
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Exposure evidence follows warning classification and membership geography.</p></div>}
    {authenticated && assessments.isPending && <div className="empty">Loading exposure assessments…</div>}
    {assessments.isError && <div className="empty error" role="alert"><b>{assessments.error instanceof ApiError && [401, 403].includes(assessments.error.status) ? 'Access not authorized' : 'Exposure assessments unavailable'}</b><p>{assessments.error.message}</p></div>}
    {assessments.data?.length === 0 && <div className="empty"><b>No assessments in scope</b><p>No governed exposure estimates are currently visible.</p></div>}
    {assessments.data && assessments.data.length > 0 && <section className="task-list" aria-label="Exposure assessments">{assessments.data.map((assessment) => <article key={assessment.id}><div className="task-heading"><span>{assessment.risk_domain.replaceAll('_', ' ')}</span><strong className={`severity-${assessment.risk_level}`}>{assessment.risk_level}</strong></div><h2>{assessment.alert_title}</h2><p>{assessment.classification} · {assessment.lineage_available ? 'Source lineage recorded' : 'Lineage unavailable'}</p><dl><div><dt>Population</dt><dd>{assessment.population === null ? 'Unknown' : assessment.population.toLocaleString()}</dd></div><div><dt>Settlements</dt><dd>{assessment.settlements === null ? 'Unknown' : assessment.settlements.toLocaleString()}</dd></div><div><dt>Cropland</dt><dd>{assessment.cropland_hectares === null ? 'Unknown' : `${assessment.cropland_hectares.toLocaleString()} ha`}</dd></div><div><dt>Confidence</dt><dd>{assessment.confidence === null ? 'Unknown' : `${Math.round(assessment.confidence * 100)}%`}</dd></div><div><dt>Infrastructure categories</dt><dd>{Object.keys(assessment.infrastructure).length || 'None measured'}</dd></div></dl></article>)}</section>}
  </main>;
}
