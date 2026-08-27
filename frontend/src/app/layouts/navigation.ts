/**
 * Navigation model.
 *
 * Every destination declares the capability that makes it meaningful. A user
 * whose role does not carry that capability does not see the entry — the item
 * would only lead to an "access not authorised" screen, which reads as a
 * broken product rather than a correctly enforced boundary.
 *
 * This is presentation logic only. The backend enforces access on every
 * request regardless of what this file says.
 */

import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BarChart3,
  Database,
  Droplets,
  FileText,
  History,
  LayoutDashboard,
  Map,
  Settings,
  ShieldAlert,
  Sun,
  Wheat,
} from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  /** i18n key, when a translation exists for this label. */
  i18nKey?: string;
  icon: LucideIcon;
  /**
   * Capabilities that make this destination useful. The item is shown when the
   * principal holds at least one of them. An empty list means always visible.
   */
  anyOf: string[];
  /** Short description used by the mobile navigation sheet. */
  hint?: string;
}

export interface NavSection {
  id: string;
  label: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    id: 'situation',
    label: 'Situation',
    items: [
      {
        to: '/app/overview',
        label: 'Overview',
        i18nKey: 'navOverview',
        icon: LayoutDashboard,
        anyOf: ['predictions.read', 'alerts.read', 'geography.read'],
        hint: 'National early-warning picture',
      },
      {
        to: '/app/map',
        label: 'Risk Map',
        i18nKey: 'navRiskMap',
        icon: Map,
        anyOf: ['geography.read'],
        hint: 'Geographic risk explorer',
      },
    ],
  },
  {
    id: 'domains',
    label: 'Risk Domains',
    items: [
      {
        to: '/app/drought',
        label: 'Drought',
        i18nKey: 'navDrought',
        icon: Sun,
        anyOf: ['predictions.read'],
        hint: 'District drought intelligence',
      },
      {
        to: '/app/flood',
        label: 'River Flood',
        i18nKey: 'navFlood',
        icon: Droplets,
        anyOf: ['predictions.read'],
        hint: 'Gauge-based flood intelligence',
      },
      {
        to: '/app/food-security',
        label: 'Food Security',
        i18nKey: 'navFoodSecurity',
        icon: Wheat,
        anyOf: ['predictions.read'],
        hint: 'Regional food-security signal',
      },
    ],
  },
  {
    id: 'operations',
    label: 'Operations',
    items: [
      {
        to: '/app/warnings',
        label: 'Warning Center',
        i18nKey: 'navWarnings',
        icon: ShieldAlert,
        anyOf: ['alerts.read'],
        hint: 'Review and publication workflow',
      },
      {
        to: '/app/history',
        label: 'Historical Intelligence',
        i18nKey: 'navHistory',
        icon: History,
        anyOf: ['predictions.read', 'alerts.read'],
        hint: 'Past signals and warnings',
      },
      {
        to: '/app/reports',
        label: 'Reports',
        i18nKey: 'navReports',
        icon: FileText,
        anyOf: ['reports.read'],
        hint: 'Governed reporting',
      },
    ],
  },
  {
    id: 'assurance',
    label: 'Assurance',
    items: [
      {
        to: '/app/data-health',
        label: 'Data Health',
        i18nKey: 'navDataHealth',
        icon: Database,
        anyOf: ['data_sources.read'],
        hint: 'Source freshness and ingestion',
      },
      {
        to: '/app/models',
        label: 'Model Operations',
        i18nKey: 'navModels',
        icon: BarChart3,
        anyOf: ['models.read'],
        hint: 'Registered model versions',
      },
      {
        to: '/app/admin',
        label: 'Administration',
        i18nKey: 'navAdmin',
        icon: Settings,
        anyOf: ['users.manage', 'organizations.manage'],
        hint: 'Users, roles and organisations',
      },
    ],
  },
];

/** Always available to a signed-in user. */
export const PROFILE_ITEM: NavItem = {
  to: '/app/profile',
  label: 'Profile & Access',
  i18nKey: 'navProfile',
  icon: Activity,
  anyOf: [],
};

export function isVisible(item: NavItem, capabilities: ReadonlySet<string>): boolean {
  if (item.anyOf.length === 0) return true;
  return item.anyOf.some((capability) => capabilities.has(capability));
}

/** Sections filtered to what this principal can act on, empty ones removed. */
export function visibleSections(capabilities: ReadonlySet<string>): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => isVisible(item, capabilities)),
  })).filter((section) => section.items.length > 0);
}

/** Flat list of every destination this principal may reach. */
export function visibleItems(capabilities: ReadonlySet<string>): NavItem[] {
  return visibleSections(capabilities).flatMap((section) => section.items);
}

/** The first destination a principal can actually use, for post-login landing. */
export function landingRoute(capabilities: ReadonlySet<string>): string {
  const items = visibleItems(capabilities);
  return items[0]?.to ?? PROFILE_ITEM.to;
}
