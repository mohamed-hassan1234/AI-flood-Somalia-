/**
 * Route table.
 *
 * Every operational page is lazily loaded so the first paint after sign-in
 * carries only the shell and the landing route. Route guards are presentation
 * only — the backend authorises every request independently.
 */

import { Suspense, lazy, type ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { useAuth } from '../providers/AuthProvider';
import { AppLayout } from '../layouts/AppLayout';
import { landingRoute } from '../layouts/navigation';
import { LoginPage } from '../../features/auth/LoginPage';
import { AccessDenied } from '../../components/ui/states';
import { Skeleton } from '../../components/ui/primitives';
import { PageHeader } from '../../components/ui/layout';

const OverviewPage = lazy(() =>
  import('../../features/overview/OverviewPage').then((m) => ({ default: m.OverviewPage })),
);
const RiskMapPage = lazy(() =>
  import('../../features/risk-map/RiskMapPage').then((m) => ({ default: m.RiskMapPage })),
);
const DroughtPage = lazy(() =>
  import('../../features/drought/DroughtPage').then((m) => ({ default: m.DroughtPage })),
);
const FloodPage = lazy(() =>
  import('../../features/flood/FloodPage').then((m) => ({ default: m.FloodPage })),
);
const FoodSecurityPage = lazy(() =>
  import('../../features/food-security/FoodSecurityPage').then((m) => ({
    default: m.FoodSecurityPage,
  })),
);
const WarningCenterPage = lazy(() =>
  import('../../features/warnings/WarningCenterPage').then((m) => ({
    default: m.WarningCenterPage,
  })),
);
const WarningReviewPage = lazy(() =>
  import('../../features/warnings/WarningReviewPage').then((m) => ({
    default: m.WarningReviewPage,
  })),
);
const HistoryPage = lazy(() =>
  import('../../features/history/HistoryPage').then((m) => ({ default: m.HistoryPage })),
);
const DataHealthPage = lazy(() =>
  import('../../features/data-health/DataHealthPage').then((m) => ({
    default: m.DataHealthPage,
  })),
);
const ModelOperationsPage = lazy(() =>
  import('../../features/data-health/ModelOperationsPage').then((m) => ({
    default: m.ModelOperationsPage,
  })),
);
const ReportsPage = lazy(() =>
  import('../../features/reports/ReportsPage').then((m) => ({ default: m.ReportsPage })),
);
const AdministrationPage = lazy(() =>
  import('../../features/administration/AdministrationPage').then((m) => ({
    default: m.AdministrationPage,
  })),
);
const ProfilePage = lazy(() =>
  import('../../features/profile/ProfilePage').then((m) => ({ default: m.ProfilePage })),
);

/* --------------------------------------------------------------- guards -- */

function FullPageLoading() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-[--color-canvas]">
      <div className="flex w-full max-w-md flex-col gap-3 px-6" aria-busy="true">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-2/3" />
      </div>
    </div>
  );
}

/** Blocks unauthenticated access and preserves the intended destination. */
function RequireSession({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();

  if (state === 'loading') return <FullPageLoading />;
  if (state !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

/**
 * Renders a route only when the principal holds a relevant capability.
 *
 * Shows an explicit access notice rather than redirecting: a silent redirect
 * from a bookmarked URL reads as a broken link, while a stated boundary tells
 * the operator exactly what to ask an administrator for.
 */
function RequireCapability({
  anyOf,
  what,
  children,
}: {
  anyOf: string[];
  what: string;
  children: ReactNode;
}) {
  const { capabilities } = useAuth();
  const permitted = anyOf.length === 0 || anyOf.some((capability) => capabilities.has(capability));

  if (!permitted) {
    return (
      <div className="flex flex-col gap-5">
        <PageHeader eyebrow="Restricted" title={what} />
        <AccessDenied capability={anyOf[0]} what={what.toLowerCase()} />
      </div>
    );
  }
  return <>{children}</>;
}

/* --------------------------------------------------------------- routes -- */

function LandingRedirect() {
  const { capabilities } = useAuth();
  return <Navigate to={landingRoute(capabilities)} replace />;
}

function NotFound() {
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Not found"
        title="Page unavailable"
        description="The requested page does not exist in this application."
      />
    </div>
  );
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/app"
        element={
          <RequireSession>
            <AppLayout />
          </RequireSession>
        }
      >
        <Route index element={<LandingRedirect />} />

        <Route
          path="overview"
          element={
            <RequireCapability
              anyOf={['predictions.read', 'alerts.read', 'geography.read']}
              what="National Overview"
            >
              <OverviewPage />
            </RequireCapability>
          }
        />
        <Route
          path="map"
          element={
            <RequireCapability anyOf={['geography.read']} what="Risk Map">
              <RiskMapPage />
            </RequireCapability>
          }
        />
        <Route
          path="drought"
          element={
            <RequireCapability anyOf={['predictions.read']} what="Drought Intelligence">
              <DroughtPage />
            </RequireCapability>
          }
        />
        <Route
          path="flood"
          element={
            <RequireCapability anyOf={['predictions.read']} what="River Flood Intelligence">
              <FloodPage />
            </RequireCapability>
          }
        />
        <Route
          path="food-security"
          element={
            <RequireCapability anyOf={['predictions.read']} what="Food Security Intelligence">
              <FoodSecurityPage />
            </RequireCapability>
          }
        />
        <Route
          path="warnings"
          element={
            <RequireCapability anyOf={['alerts.read']} what="Warning Center">
              <WarningCenterPage />
            </RequireCapability>
          }
        />
        <Route
          path="warnings/:alertId"
          element={
            <RequireCapability anyOf={['alerts.read']} what="Warning Review">
              <WarningReviewPage />
            </RequireCapability>
          }
        />
        <Route
          path="history"
          element={
            <RequireCapability
              anyOf={['predictions.read', 'alerts.read']}
              what="Historical Intelligence"
            >
              <HistoryPage />
            </RequireCapability>
          }
        />
        <Route
          path="data-health"
          element={
            <RequireCapability anyOf={['data_sources.read']} what="Data Health">
              <DataHealthPage />
            </RequireCapability>
          }
        />
        <Route
          path="models"
          element={
            <RequireCapability anyOf={['models.read']} what="Model Operations">
              <ModelOperationsPage />
            </RequireCapability>
          }
        />
        <Route
          path="reports"
          element={
            <RequireCapability anyOf={['reports.read']} what="Reports">
              <ReportsPage />
            </RequireCapability>
          }
        />
        <Route
          path="admin"
          element={
            <RequireCapability
              anyOf={['users.manage', 'organizations.manage']}
              what="Administration"
            >
              <AdministrationPage />
            </RequireCapability>
          }
        />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="*" element={<NotFound />} />
      </Route>

      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route
        path="*"
        element={
          <Suspense fallback={<FullPageLoading />}>
            <Navigate to="/app" replace />
          </Suspense>
        }
      />
    </Routes>
  );
}
