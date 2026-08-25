import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type Delivery = {
  id: string; event_key: string; event_title: string; channel: string; status: string;
  recipient_is_current_user: boolean; attempt_count: number; next_attempt_at: string | null;
  acknowledged_at: string | null; escalated_at: string | null; escalation_level: number;
  last_error_code?: string | null; last_attempted_at?: string | null; dead_lettered_at?: string | null;
};

export function NotificationsPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const client = useQueryClient();
  const deliveries = useQuery({ queryKey: ['notification-deliveries'], queryFn: () => apiRequest<Delivery[]>('/notifications/deliveries'), enabled: authenticated });
  const acknowledge = useMutation({
    mutationFn: (id: string) => apiRequest<Delivery>(`/notifications/deliveries/${id}/acknowledgement`, { method: 'POST' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['notification-deliveries'] }),
  });
  return <main><p className="eyebrow">NOTIFICATIONS</p><h1>Delivery operations</h1><p className="lead">Scoped delivery state, retries, acknowledgements, and escalation level. Recipient identifiers are deliberately excluded.</p>
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Notification operations contain restricted workflow information.</p></div>}
    {authenticated && deliveries.isPending && <div className="empty">Loading notification operations…</div>}
    {deliveries.isError && <div className="empty error" role="alert"><b>{deliveries.error instanceof ApiError && [401, 403].includes(deliveries.error.status) ? 'Access not authorized' : 'Notifications unavailable'}</b><p>{deliveries.error.message}</p></div>}
    {acknowledge.isError && <div className="error" role="alert">Acknowledgement failed: {acknowledge.error.message}</div>}
    {deliveries.data?.length === 0 && <div className="empty"><b>No deliveries in scope</b><p>No notification delivery records are currently visible.</p></div>}
    {deliveries.data && deliveries.data.length > 0 && <section className="task-list" aria-label="Notification delivery queue">{deliveries.data.map((delivery) => <article key={delivery.id}><div className="task-heading"><span>{delivery.channel}</span><strong>{delivery.dead_lettered_at ? 'dead letter' : delivery.status}</strong></div><h2>{delivery.event_title}</h2><p>{delivery.event_key}</p>{delivery.last_error_code && <p className="error">Provider status: {delivery.last_error_code}</p>}<dl><div><dt>Attempts</dt><dd>{delivery.attempt_count}</dd></div><div><dt>Escalation</dt><dd>Level {delivery.escalation_level}</dd></div><div><dt>Last attempt</dt><dd>{delivery.last_attempted_at ? new Date(delivery.last_attempted_at).toLocaleString() : 'Not attempted'}</dd></div><div><dt>Next attempt</dt><dd>{delivery.next_attempt_at ? new Date(delivery.next_attempt_at).toLocaleString() : 'Not scheduled'}</dd></div><div><dt>Acknowledged</dt><dd>{delivery.acknowledged_at ? new Date(delivery.acknowledged_at).toLocaleString() : 'No'}</dd></div></dl>{delivery.recipient_is_current_user && !delivery.acknowledged_at && <button type="button" disabled={acknowledge.isPending} onClick={() => acknowledge.mutate(delivery.id)}>Acknowledge</button>}</article>)}</section>}
  </main>;
}
