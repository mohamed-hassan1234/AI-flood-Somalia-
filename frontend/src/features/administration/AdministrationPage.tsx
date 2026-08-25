import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../services/api';

type Organization = { id: string; name: string; organization_type: string; active: boolean };
type User = { id: string; email: string; display_name: string; active: boolean };
type Role = { id: string; name: string; description: string; capabilities: string[] };
type Membership = { id: string; user_id: string; organization_id: string; role_id: string; classification_ceiling: string; active: boolean; national: boolean; admin_unit_ids: string[] };

export function AdministrationPage() {
  const authenticated = Boolean(sessionStorage.getItem('somalia-ai-access-token'));
  const inventory = useQuery({
    queryKey: ['administration-inventory'],
    queryFn: async () => {
      const [organizations, users, roles, memberships] = await Promise.all([
        apiRequest<Organization[]>('/administration/organizations'),
        apiRequest<User[]>('/administration/users'),
        apiRequest<Role[]>('/administration/roles'),
        apiRequest<Membership[]>('/administration/memberships'),
      ]);
      return { organizations, users, roles, memberships };
    },
    enabled: authenticated,
  });
  return <main>
    <p className="eyebrow">ADMINISTRATION</p><h1>Governed access inventory</h1>
    <p className="lead">National administration visibility for users, organizations, roles, memberships, classification ceilings, and geographic scope. Mutations remain separately authorized and audited by the API.</p>
    {!authenticated && <div className="empty unauthorized"><b>Sign in required</b><p>Administration requires an authorized national membership.</p></div>}
    {authenticated && inventory.isPending && <div className="empty">Loading administrative inventory…</div>}
    {inventory.isError && <div className="empty error" role="alert"><b>{inventory.error instanceof ApiError && [401, 403].includes(inventory.error.status) ? 'Access not authorized' : 'Administration unavailable'}</b><p>{inventory.error.message}</p></div>}
    {inventory.data && <>
      <div className="summary-meta"><span>{inventory.data.users.length} users</span><span>{inventory.data.organizations.length} organizations</span><span>{inventory.data.memberships.length} memberships</span><span>{inventory.data.roles.length} roles</span></div>
      {inventory.data.memberships.length === 0 && <div className="empty"><b>No memberships configured</b><p>No governed membership assignments are currently recorded.</p></div>}
      {inventory.data.memberships.length > 0 && <section className="task-list" aria-label="Membership inventory">
        {inventory.data.memberships.map((membership) => {
          const user = inventory.data.users.find((item) => item.id === membership.user_id);
          const organization = inventory.data.organizations.find((item) => item.id === membership.organization_id);
          const role = inventory.data.roles.find((item) => item.id === membership.role_id);
          return <article key={membership.id}><div className="task-heading"><span>{membership.classification_ceiling}</span><strong>{membership.active ? 'active' : 'inactive'}</strong></div>
            <h2>{user?.display_name ?? 'Unknown user'}</h2><p>{user?.email ?? membership.user_id}</p>
            <dl><div><dt>Organization</dt><dd>{organization?.name ?? membership.organization_id}</dd></div><div><dt>Role</dt><dd>{role?.name ?? membership.role_id}</dd></div><div><dt>Scope</dt><dd>{membership.national ? 'National' : `${membership.admin_unit_ids.length} administrative units`}</dd></div></dl>
          </article>;
        })}
      </section>}
    </>}
  </main>;
}
