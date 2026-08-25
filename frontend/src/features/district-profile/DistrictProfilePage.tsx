import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ApiError, apiRequest } from '../../services/api';

type AdminUnit = {
  id: string;
  stable_code: string;
  name: string;
  level: 'region' | 'district';
  parent_id: string | null;
  boundary_version: string;
  boundary_source: string;
  valid_from: string;
  valid_to: string | null;
  aliases: string[];
};

type Observation = {
  id: string;
  source_id: string;
  source_name: string;
  source_classification: 'internal' | 'partner' | 'public';
  admin_unit_id: string;
  indicator_code: string;
  indicator_definition_id?: string | null;
  indicator_version?: string | null;
  season_name?: string | null;
  season_version?: string | null;
  season_authority?: string | null;
  value: number | null;
  value_kind: string;
  unit: string;
  reference_time: string;
  retrieved_at: string;
  stage: string;
  quality_flags: string[];
  boundary_version: string;
};

type Aggregate = {
  admin_unit_id: string; indicator_code: string; reference_time: string; latest_retrieved_at: string;
  value: number | null; unit: string; method: string; contributing_admin_units: number;
  total_descendant_units: number; missing_records: number; source_ids: string[];
  source_names: string[]; boundary_version: string;
  season_name: string | null; season_version: string | null; season_authority: string | null;
};

export function DistrictProfilePage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const [level, setLevel] = useState<'district' | 'region'>('district');
  const [districtId, setDistrictId] = useState('');
  const [indicator, setIndicator] = useState('');
  const districts = useQuery({
    queryKey: ['profile-units', level],
    queryFn: () => apiRequest<AdminUnit[]>(`/geography/admin-units?level=${level}`),
    enabled: authenticated,
  });
  const activeDistrictId = districtId || districts.data?.[0]?.id || '';
  const observations = useQuery({
    queryKey: ['profile-observations', level, activeDistrictId],
    queryFn: async () => {
      if (level === 'district') return apiRequest<Observation[]>(`/observations?admin_unit_id=${activeDistrictId}&limit=500`);
      const rows = await apiRequest<Aggregate[]>(`/observations/aggregate?admin_unit_id=${activeDistrictId}`);
      return rows.map((row, index): Observation => ({ id: `${row.admin_unit_id}-${index}`, source_id: row.source_ids[0] ?? '', source_name: row.source_names.join(', '), source_classification: 'internal', admin_unit_id: row.admin_unit_id, indicator_code: row.indicator_code, value: row.value, value_kind: 'aggregate', unit: row.unit, reference_time: row.reference_time, retrieved_at: row.latest_retrieved_at, stage: 'normalized', quality_flags: [`${row.method}`, `coverage:${row.contributing_admin_units}/${row.total_descendant_units}`, `missing_records:${row.missing_records}`], boundary_version: row.boundary_version, season_name: row.season_name, season_version: row.season_version, season_authority: row.season_authority }));
    },
    enabled: authenticated && Boolean(activeDistrictId),
  });
  const indicators = useMemo(
    () => [...new Set(observations.data?.map((row) => row.indicator_code) ?? [])].sort(),
    [observations.data],
  );
  const activeIndicator = indicator && indicators.includes(indicator) ? indicator : indicators[0];
  const series = observations.data?.filter((row) => row.indicator_code === activeIndicator) ?? [];
  const activeDistrict = districts.data?.find((unit) => unit.id === activeDistrictId);
  const latest = series.at(-1);
  const stale = latest ? Date.now() - new Date(latest.retrieved_at).getTime() > 48 * 60 * 60 * 1000 : true;
  const error = districts.error ?? observations.error;

  return (
    <main>
      <p className="eyebrow">DISTRICT PROFILE</p>
      <h1>Regional and district evidence</h1>
      <p className="lead">Scoped observation history with explicit source, aggregation method, coverage, missingness, unit, period, freshness, quality, and boundary version.</p>
      {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>District evidence is restricted by membership geography and classification.</p></div>}
      {authenticated && districts.isPending && <div className="empty">Loading accessible districts…</div>}
      {error && (
        <div className="empty error" role="alert">
          <b>{error instanceof ApiError && [401, 403].includes(error.status) ? 'Access not authorized' : 'District evidence unavailable'}</b>
          <p>{error.message}</p>
        </div>
      )}
      {districts.data?.length === 0 && <div className="empty"><b>No accessible districts</b><p>No approved district geography is available in this membership scope.</p></div>}
      {districts.data && districts.data.length > 0 && (
        <div className="profile-controls">
          <label>Level<select value={level} onChange={(event) => { setLevel(event.target.value as 'district' | 'region'); setDistrictId(''); setIndicator(''); }}><option value="district">District</option><option value="region">Region</option></select></label>
          <label>{level === 'district' ? 'District' : 'Region'}<select value={activeDistrictId} onChange={(event) => { setDistrictId(event.target.value); setIndicator(''); }}>{districts.data.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</select></label>
          {indicators.length > 0 && <label>Indicator<select value={activeIndicator} onChange={(event) => setIndicator(event.target.value)}>{indicators.map((code) => <option key={code}>{code}</option>)}</select></label>}
        </div>
      )}
      {observations.isPending && activeDistrictId && <div className="empty">Loading district observations…</div>}
      {observations.data?.length === 0 && <div className="empty"><b>No observations available</b><p>Missing evidence remains missing; no zero values are inferred.</p></div>}
      {latest && activeDistrict && (
        <section className="profile-series" aria-label={`${activeDistrict.name} ${activeIndicator} time series`}>
          <div className="chart-meta">
            <span>{latest.source_name}</span><span>{latest.unit}</span><span>{series[0].reference_time.slice(0, 10)} – {latest.reference_time.slice(0, 10)}</span><span>{latest.season_name ? `${latest.season_name} · ${latest.season_version} · ${latest.season_authority}` : 'No approved season'}</span><strong className={stale ? 'stale-text' : ''}>{stale ? 'STALE' : 'CURRENT'}</strong>
          </div>
          <div className="chart-frame" role="img" aria-label={`${activeIndicator} values in ${latest.unit} over time`}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} accessibilityLayer>
                <CartesianGrid stroke="#26463c" />
                <XAxis dataKey="reference_time" tickFormatter={(value: string) => value.slice(0, 10)} stroke="#829c93" />
                <YAxis stroke="#829c93" />
                <Tooltip labelFormatter={(value) => new Date(String(value)).toLocaleString()} />
                <Line dataKey="value" stroke="#e8b84a" strokeWidth={2} connectNulls={false} name={`${activeIndicator} (${latest.unit})`} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <table><caption>Accessible observation values</caption><thead><tr><th>Period</th><th>Season</th><th>Value</th><th>Source</th><th>Definition</th><th>Quality</th><th>Boundary</th></tr></thead><tbody>{series.map((row) => <tr key={row.id}><td>{new Date(row.reference_time).toLocaleString()}</td><td>{row.season_name ? `${row.season_name} (${row.season_version})` : 'Unclassified'}</td><td>{row.value ?? 'Missing'} {row.unit}</td><td>{row.source_name}</td><td>{row.indicator_version ?? 'Unregistered'}</td><td>{row.quality_flags.join(', ') || 'No flags'}</td><td>{row.boundary_version}</td></tr>)}</tbody></table>
        </section>
      )}
    </main>
  );
}
