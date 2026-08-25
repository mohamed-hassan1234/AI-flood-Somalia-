import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type Option = { id: string; name: string; row_count?: number };
type Scenario = { id: string; name: string; snapshot_name: string; admin_unit_name: string; domain: string; modifications: Record<string, number>; result: { baseline_score: number; simulated_score: number; may_publish_warning: boolean }; label: string; created_at: string };

export function ScenarioLabPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const client = useQueryClient();
  const [name, setName] = useState(''); const [snapshot, setSnapshot] = useState(''); const [unit, setUnit] = useState('');
  const [domain, setDomain] = useState('drought'); const [baseline, setBaseline] = useState('0.4'); const [shock, setShock] = useState('0.1');
  const scenarios = useQuery({ queryKey: ['scenarios'], queryFn: () => apiRequest<Scenario[]>('/scenarios'), enabled: authenticated });
  const snapshots = useQuery({ queryKey: ['scenario-snapshots'], queryFn: () => apiRequest<Option[]>('/ml/snapshot-options'), enabled: authenticated });
  const units = useQuery({ queryKey: ['scenario-units'], queryFn: () => apiRequest<Option[]>('/geography/admin-units?level=district'), enabled: authenticated });
  const run = useMutation({ mutationFn: () => apiRequest('/scenarios', { method: 'POST', body: JSON.stringify({ name, baseline_snapshot_id: snapshot, admin_unit_id: unit, domain, baseline_score: Number(baseline), modifications: { compound_shock: Number(shock) } }) }), onSuccess: () => { setName(''); client.invalidateQueries({ queryKey: ['scenarios'] }); } });
  const submit = (event: FormEvent) => { event.preventDefault(); run.mutate(); };
  return <main><p className="eyebrow">SCENARIO LAB</p><h1>Explore, never publish</h1><p className="lead">Run bounded what-if shocks against a governed baseline. Simulations cannot publish warnings or replace operational forecasts.</p>
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Scenario inputs and results are restricted internal analysis.</p></div>}
    {authenticated && <form className="profile-controls" onSubmit={submit}><label>Name<input required minLength={3} value={name} onChange={(event) => setName(event.target.value)} /></label><label>Baseline snapshot<select required value={snapshot} onChange={(event) => setSnapshot(event.target.value)}><option value="">Select</option>{snapshots.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>District<select required value={unit} onChange={(event) => setUnit(event.target.value)}><option value="">Select</option>{units.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Domain<select value={domain} onChange={(event) => setDomain(event.target.value)}><option value="drought">Drought</option><option value="river_flood">River flood</option><option value="flash_flood">Flash flood</option><option value="food_security_deterioration">Food security</option></select></label><label>Baseline score<input required type="number" min="0" max="1" step="0.01" value={baseline} onChange={(event) => setBaseline(event.target.value)} /></label><label>Compound shock<input required type="number" min="-1" max="1" step="0.01" value={shock} onChange={(event) => setShock(event.target.value)} /></label><button disabled={run.isPending || !snapshot || !unit}>{run.isPending ? 'Running…' : 'Run simulation'}</button></form>}
    {(scenarios.isError || snapshots.isError || units.isError) && <div className="empty error" role="alert"><b>Scenario Lab unavailable</b><p>{[scenarios.error, snapshots.error, units.error].find(Boolean) instanceof ApiError ? 'Access is not authorized or scenario evidence could not be loaded.' : 'Scenario evidence could not be loaded.'}</p></div>}
    {run.isError && <div className="error" role="alert">Simulation failed: {run.error.message}</div>}
    {scenarios.data?.length === 0 && <div className="empty"><b>No simulations in scope</b><p>Run a bounded scenario to create an explicitly non-operational result.</p></div>}
    {scenarios.data && scenarios.data.length > 0 && <section className="task-list" aria-label="Scenario history">{scenarios.data.map((scenario) => <article key={scenario.id}><div className="task-heading"><span>{scenario.domain.replaceAll('_', ' ')}</span><strong className="severity-warning">{scenario.label}</strong></div><h2>{scenario.name}</h2><p>{scenario.admin_unit_name} · {scenario.snapshot_name}</p><dl><div><dt>Baseline</dt><dd>{scenario.result.baseline_score}</dd></div><div><dt>Simulated</dt><dd>{scenario.result.simulated_score}</dd></div><div><dt>Warning publication</dt><dd>{scenario.result.may_publish_warning ? 'Unexpectedly enabled' : 'Prohibited'}</dd></div></dl></article>)}</section>}
  </main>;
}
