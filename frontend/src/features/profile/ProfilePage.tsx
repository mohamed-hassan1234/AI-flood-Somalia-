/**
 * Profile & Access.
 *
 * Shows the principal exactly what the backend granted them. Capabilities are
 * listed verbatim rather than translated into a friendly role name, because
 * when a control is missing elsewhere in the product this is the page that
 * answers why — and a paraphrase would not.
 */

import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, ShieldCheck } from 'lucide-react';

import { useAuth } from '../../app/providers/AuthProvider';
import { usePlatformMeta } from '../../api/queries';
import { Button, Card, DataGrid, DataPoint } from '../../components/ui/primitives';
import { PageHeader, SectionHeader } from '../../components/ui/layout';
import { Note } from '../../components/ui/states';
import { MetaChip } from '../../components/intelligence/badges';
import { LanguageToggle } from '../../i18n';
import { formatCount, humanise } from '../../lib/format';
import { OPERATIONAL_TIMEZONE } from '../../lib/time';

/** Groups capabilities by their dotted namespace, e.g. `alerts.*`. */
function groupCapabilities(capabilities: string[]): Array<[string, string[]]> {
  const groups = new Map<string, string[]>();
  for (const capability of [...capabilities].sort()) {
    const [namespace] = capability.split('.');
    const existing = groups.get(namespace) ?? [];
    existing.push(capability);
    groups.set(namespace, existing);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export function ProfilePage() {
  const { principal, signOut, capabilities } = useAuth();
  const navigate = useNavigate();
  const meta = usePlatformMeta(true);

  const grouped = useMemo(
    () => groupCapabilities(principal?.capabilities ?? []),
    [principal?.capabilities],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Account"
        title="Profile & Access"
        description="Your identity and the exact capabilities the platform has granted you."
        actions={
          <Button
            variant="secondary"
            onClick={() => {
              signOut();
              void navigate('/login');
            }}
          >
            <LogOut className="size-4" aria-hidden="true" />
            Sign out
          </Button>
        }
      />

      <Card>
        <SectionHeader title="Identity" />
        <DataGrid columns={3}>
          <DataPoint label="Display name" value={principal?.display_name ?? '—'} />
          <DataPoint label="Email" value={principal?.email ?? '—'} />
          <DataPoint
            label="Capabilities granted"
            value={formatCount(capabilities.size)}
          />
          <DataPoint label="Operational timezone" value={OPERATIONAL_TIMEZONE} />
          <DataPoint
            label="User identifier"
            value={
              <code className="font-mono text-[12px]">
                {principal?.user_id.slice(0, 12) ?? '—'}
              </code>
            }
          />
        </DataGrid>
      </Card>

      <Card>
        <SectionHeader
          title="Granted capabilities"
          description="The backend re-checks these on every request. This list is what determines which controls appear elsewhere in the product."
        />
        {grouped.length === 0 ? (
          <Note tone="caution">
            No capabilities are attached to your account. Ask a platform administrator to review
            your role assignment.
          </Note>
        ) : (
          <div className="flex flex-col gap-4">
            {grouped.map(([namespace, items]) => (
              <div key={namespace} className="flex flex-col gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.07em] text-[--color-ink-faint]">
                  {humanise(namespace)}
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {items.map((capability) => (
                    <MetaChip key={capability} className="font-mono text-[11px]">
                      {capability}
                    </MetaChip>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {meta.data && (
        <Card>
          <SectionHeader
            title="Platform guarantees"
            description="Invariants this deployment reports through its own metadata endpoint"
          />
          <div className="flex flex-col gap-2.5">
            <Note tone="info" icon={<ShieldCheck className="size-3.5" aria-hidden="true" />}>
              <span className="font-semibold">Automatic warning publication: </span>
              {meta.data.automatic_warning_publication ? 'enabled' : 'disabled'}.{' '}
              {meta.data.automatic_warning_publication
                ? 'Warnings may publish without a human decision on this deployment.'
                : 'No warning reaches an audience without an authorised human decision.'}
            </Note>
            <Note tone="info" icon={<ShieldCheck className="size-3.5" aria-hidden="true" />}>
              <span className="font-semibold">Official IPC output: </span>
              {meta.data.official_ipc_output ? 'enabled' : 'disabled'}.{' '}
              {meta.data.official_ipc_output
                ? 'This deployment emits official IPC classifications.'
                : 'Food-security output is a model signal and is never an official IPC classification.'}
            </Note>
          </div>
        </Card>
      )}

      <Card>
        <SectionHeader title="Preferences" description="Stored in this browser only" />
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-medium text-[--color-ink-secondary]">
            Interface language
          </span>
          <LanguageToggle />
        </div>
        <p className="mt-2 text-[12px] leading-5 text-[--color-ink-muted]">
          Navigation and common status labels are available in English and Somali. Scientific and
          methodological text remains in English, the working language of the underlying model
          contract, so that caveats and scope limitations cannot be altered in translation.
        </p>
      </Card>
    </div>
  );
}
