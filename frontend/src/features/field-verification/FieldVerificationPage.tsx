import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type VerificationTask = {
  id: string; alert_id: string; alert_title: string;
  classification: 'internal' | 'partner' | 'public'; admin_unit_id: string;
  risk_domain: string; assigned_to: string | null; due_at: string;
  priority: 'low' | 'normal' | 'high' | 'critical';
  status: 'open' | 'submitted' | 'verified' | 'rejected' | 'more_evidence_required';
};

export function FieldVerificationPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const tasks = useQuery({ queryKey: ['verification-tasks'], queryFn: () => apiRequest<VerificationTask[]>('/field-verification/tasks'), enabled: authenticated });
  return <main><p className="eyebrow">FIELD VERIFICATION</p><h1>Ground truth</h1><p className="lead">Assigned and reviewable tasks only. Structured forms and submitted evidence are excluded from this work-queue projection.</p>
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Verification tasks are restricted by assignment, geography, and classification.</p></div>}
    {authenticated && tasks.isPending && <div className="empty">Loading verification work queue…</div>}
    {tasks.isError && <div className="empty error" role="alert"><b>{tasks.error instanceof ApiError && [401, 403].includes(tasks.error.status) ? 'Access not authorized' : 'Verification queue unavailable'}</b><p>{tasks.error.message}</p></div>}
    {tasks.data?.length === 0 && <div className="empty"><b>No verification tasks in scope</b><p>No assigned or reviewable requests are currently visible.</p></div>}
    {tasks.data && tasks.data.length > 0 && <section className="task-list" aria-label="Verification work queue">{tasks.data.map((task) => {
      const overdue = new Date(task.due_at).getTime() < Date.now() && !['verified', 'rejected'].includes(task.status);
      return <article key={task.id}><div className="task-heading"><span>{task.risk_domain.replaceAll('_', ' ')}</span><strong className={`priority-${task.priority}`}>{task.priority}</strong></div><h2>{task.alert_title}</h2><div className="workflow-state"><span>Status</span><b>{task.status.replaceAll('_', ' ')}</b><span>{task.classification}</span></div><dl><div><dt>Due</dt><dd className={overdue ? 'error' : ''}>{new Date(task.due_at).toLocaleString()}{overdue ? ' · OVERDUE' : ''}</dd></div><div><dt>Assignment</dt><dd>{task.assigned_to ? 'Assigned reporter' : 'Unassigned'}</dd></div></dl></article>;
    })}</section>}
  </main>;
}
