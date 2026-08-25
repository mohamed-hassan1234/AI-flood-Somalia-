import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type ActionItem = { id: string; plan_title: string; alert_title: string; risk_domain: string; description: string; due_at: string; status: string; blockers: string[]; evidence_count: number };

export function EarlyActionsPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const items = useQuery({ queryKey: ['early-action-items'], queryFn: () => apiRequest<ActionItem[]>('/early-actions/items'), enabled: authenticated });
  return <main><p className="eyebrow">EARLY ACTION</p><h1>Accountable response</h1><p className="lead">Approved-plan actions in your scope, with deadlines, blockers, and evidence progress.</p>
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Early-action operations are restricted to authorized partners and officials.</p></div>}
    {authenticated && items.isPending && <div className="empty">Loading early actions…</div>}
    {items.isError && <div className="empty error" role="alert"><b>{items.error instanceof ApiError && [401, 403].includes(items.error.status) ? 'Access not authorized' : 'Early actions unavailable'}</b><p>{items.error.message}</p></div>}
    {items.data?.length === 0 && <div className="empty"><b>No actions in scope</b><p>No approved-plan action items are currently visible.</p></div>}
    {items.data && items.data.length > 0 && <section className="task-list" aria-label="Early action work queue">{items.data.map((item) => { const overdue = new Date(item.due_at).getTime() < Date.now() && item.status !== 'completed'; return <article key={item.id}><div className="task-heading"><span>{item.risk_domain.replaceAll('_', ' ')}</span><strong>{item.status.replaceAll('_', ' ')}</strong></div><h2>{item.description}</h2><p>{item.plan_title} · {item.alert_title}</p><dl><div><dt>Due</dt><dd className={overdue ? 'error' : ''}>{new Date(item.due_at).toLocaleString()}{overdue ? ' · OVERDUE' : ''}</dd></div><div><dt>Evidence</dt><dd>{item.evidence_count} object{item.evidence_count === 1 ? '' : 's'}</dd></div><div><dt>Blockers</dt><dd>{item.blockers.length ? item.blockers.join('; ') : 'None reported'}</dd></div></dl></article>; })}</section>}
  </main>;
}
