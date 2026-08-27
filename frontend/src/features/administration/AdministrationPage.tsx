/**
 * Administration — users, roles and organisations.
 *
 * Read-only in this release. The backend exposes create endpoints for users,
 * organisations and memberships, but creating an account is a credential
 * operation with consequences this interface is not yet designed to carry
 * safely (password issuance, geographic scope assignment, classification
 * ceiling). Rather than ship a half-safe form, this page presents the current
 * access model accurately and states where account changes are performed.
 */

import { useMemo, useState } from 'react';
import { Building2, ShieldCheck, Users } from 'lucide-react';

import { useOrganizations, useRoles, useUsers } from '../../api/queries';
import { Card, Skeleton } from '../../components/ui/primitives';
import {
  MetaBar,
  MetaItem,
  PageHeader,
  SectionHeader,
  TabPanel,
  Table,
  TableScroll,
  Tabs,
  Td,
  Th,
  type TabDefinition,
} from '../../components/ui/layout';
import { EmptyState, Note, QueryBoundary } from '../../components/ui/states';
import { MetaChip } from '../../components/intelligence/badges';
import { formatCount, humanise } from '../../lib/format';

type AdminTab = 'users' | 'roles' | 'organizations';

export function AdministrationPage() {
  const [tab, setTab] = useState<AdminTab>('users');

  const users = useUsers(true);
  const roles = useRoles(true);
  const organizations = useOrganizations(true);

  const tabs: Array<TabDefinition<AdminTab>> = [
    { id: 'users', label: 'Users', count: users.data?.length },
    { id: 'roles', label: 'Roles', count: roles.data?.length },
    { id: 'organizations', label: 'Organisations', count: organizations.data?.length },
  ];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Administration"
        title="Users, Roles & Organisations"
        description="The access model this deployment enforces. Every capability listed here is checked by the backend on each request."
        meta={
          <MetaBar>
            <MetaItem label="Users" value={formatCount(users.data?.length ?? 0)} />
            <MetaItem label="Roles" value={formatCount(roles.data?.length ?? 0)} />
            <MetaItem label="Organisations" value={formatCount(organizations.data?.length ?? 0)} />
          </MetaBar>
        }
      />

      <Note tone="neutral" icon={<ShieldCheck className="size-3.5" aria-hidden="true" />}>
        <span className="font-semibold text-[--color-ink]">Read-only view. </span>
        Account creation and membership assignment involve credential issuance, geographic scope and
        classification ceiling. They are performed through the platform administration API and its
        operational runbook, not from this screen.
      </Note>

      <Tabs tabs={tabs} value={tab} onChange={setTab} label="Administration section" />

      <TabPanel id="users" active={tab === 'users'}>
        <Card flush>
          <div className="border-b border-[--color-line] px-4 py-3">
            <SectionHeader className="mb-0" title="User accounts" />
          </div>
          <div className="p-3">
            <QueryBoundary
              query={users}
              skeleton={<Skeleton className="h-48 w-full" />}
              isEmpty={(data) => data.length === 0}
              empty={
                <EmptyState
                  icon={<Users className="size-4.5" aria-hidden="true" />}
                  title="No user accounts visible"
                  description="No account is visible to your administrative scope."
                />
              }
            >
              {(data) => (
                <TableScroll>
                  <Table>
                    <thead>
                      <tr>
                        <Th>Display name</Th>
                        <Th>Email</Th>
                        <Th>Status</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.map((user) => (
                        <tr key={user.id}>
                          <Td className="font-medium">{user.display_name}</Td>
                          <Td className="text-[--color-ink-secondary]">{user.email}</Td>
                          <Td>
                            <MetaChip
                              className={
                                user.active
                                  ? 'bg-[--color-ok-bg] text-[--color-ok-fg]'
                                  : 'bg-[--color-muted-bg] text-[--color-muted-fg]'
                              }
                            >
                              {user.active ? 'Active' : 'Inactive'}
                            </MetaChip>
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </TableScroll>
              )}
            </QueryBoundary>
          </div>
        </Card>
      </TabPanel>

      <TabPanel id="roles" active={tab === 'roles'}>
        <QueryBoundary
          query={roles}
          skeleton={<Skeleton className="h-64 w-full" />}
          isEmpty={(data) => data.length === 0}
          empty={<EmptyState title="No roles defined" />}
        >
          {(data) => (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {data.map((role) => (
                <Card key={role.id}>
                  <SectionHeader
                    title={role.name}
                    description={`${formatCount(role.capabilities.length)} capabilities`}
                  />
                  <div className="flex flex-wrap gap-1.5">
                    {[...role.capabilities].sort().map((capability) => (
                      <MetaChip key={capability} className="font-mono text-[11px]">
                        {capability}
                      </MetaChip>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </QueryBoundary>
      </TabPanel>

      <TabPanel id="organizations" active={tab === 'organizations'}>
        <Card flush>
          <div className="border-b border-[--color-line] px-4 py-3">
            <SectionHeader className="mb-0" title="Organisations" />
          </div>
          <div className="p-3">
            <QueryBoundary
              query={organizations}
              skeleton={<Skeleton className="h-40 w-full" />}
              isEmpty={(data) => data.length === 0}
              empty={
                <EmptyState
                  icon={<Building2 className="size-4.5" aria-hidden="true" />}
                  title="No organisations registered"
                />
              }
            >
              {(data) => (
                <TableScroll>
                  <Table>
                    <thead>
                      <tr>
                        <Th>Organisation</Th>
                        <Th>Type</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.map((organization) => (
                        <tr key={organization.id}>
                          <Td className="font-medium">{organization.name}</Td>
                          <Td className="text-[--color-ink-secondary]">
                            {humanise(organization.organization_type)}
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </TableScroll>
              )}
            </QueryBoundary>
          </div>
        </Card>
      </TabPanel>
    </div>
  );
}

/** Capability count summary used by the profile page. */
export function useCapabilitySummary(capabilities: string[]): Array<[string, number]> {
  return useMemo(() => {
    const counts = new Map<string, number>();
    for (const capability of capabilities) {
      const [namespace] = capability.split('.');
      counts.set(namespace, (counts.get(namespace) ?? 0) + 1);
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [capabilities]);
}
