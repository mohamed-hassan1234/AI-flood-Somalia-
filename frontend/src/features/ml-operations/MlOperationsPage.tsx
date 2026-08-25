import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type ModelOperation = {
  id: string; name: string; version: string; state: string; snapshot_name: string;
  snapshot_row_count: number; feature_name: string; feature_version: string;
  metrics: Record<string, unknown>; model_card: Record<string, unknown>; promotion_ready: boolean;
};

function valueLabel(value: unknown) {
  return typeof value === 'number' ? value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '') : String(value);
}

export function MlOperationsPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const models = useQuery({ queryKey: ['ml-operations'], queryFn: () => apiRequest<ModelOperation[]>('/ml/operations'), enabled: authenticated });
  return <main><p className="eyebrow">ML OPERATIONS</p><h1>Model governance</h1><p className="lead">Traceable snapshots, feature versions, evaluation metrics, model-card readiness, and registry state. Predictions remain decision support.</p>
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Model registry evidence is restricted to authorized analysts.</p></div>}
    {authenticated && models.isPending && <div className="empty">Loading model registry…</div>}
    {models.isError && <div className="empty error" role="alert"><b>{models.error instanceof ApiError && [401, 403].includes(models.error.status) ? 'Access not authorized' : 'Model registry unavailable'}</b><p>{models.error.message}</p></div>}
    {models.data?.length === 0 && <div className="empty"><b>No registered models</b><p>No governed model versions are currently available.</p></div>}
    {models.data && models.data.length > 0 && <section className="task-list" aria-label="Model governance registry">{models.data.map((model) => <article key={model.id}><div className="task-heading"><span>{model.version}</span><strong className={model.promotion_ready ? 'severity-normal' : 'severity-warning'}>{model.state}</strong></div><h2>{model.name}</h2><p>{model.promotion_ready ? 'Promotion evidence complete' : 'Promotion evidence incomplete'}</p><dl><div><dt>Snapshot</dt><dd>{model.snapshot_name} · {model.snapshot_row_count.toLocaleString()} rows</dd></div><div><dt>Features</dt><dd>{model.feature_name} · {model.feature_version}</dd></div>{Object.entries(model.metrics).map(([name, value]) => <div key={name}><dt>{name.replaceAll('_', ' ')}</dt><dd>{valueLabel(value)}</dd></div>)}</dl><small>Model card: {Object.keys(model.model_card).length} documented fields</small></article>)}</section>}
  </main>;
}
