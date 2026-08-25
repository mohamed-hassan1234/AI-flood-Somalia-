import { lazy, Suspense } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';
import { AlertCenterPage } from '../features/alerts/AlertCenterPage';
import { AdministrationPage } from '../features/administration/AdministrationPage';
import { LoginPage } from '../features/auth/LoginPage';
import { NationalDashboard } from '../features/dashboard/NationalDashboard';
import { DataHealthPage } from '../features/data-health/DataHealthPage';
import { EarlyActionsPage } from '../features/early-actions/EarlyActionsPage';
import { ExposurePage } from '../features/exposure/ExposurePage';
import { FieldVerificationPage } from '../features/field-verification/FieldVerificationPage';
import { MapExplorer } from '../features/map-explorer/MapExplorer';
import { MlOperationsPage } from '../features/ml-operations/MlOperationsPage';
import { NotificationsPage } from '../features/notifications/NotificationsPage';
import { PartnerPortalPage } from '../features/partner/PartnerPortalPage';
import { PublicWarningsPage } from '../features/public/PublicWarningsPage';
import { ReportsPage } from '../features/reports/ReportsPage';
import { ScenarioLabPage } from '../features/scenarios/ScenarioLabPage';
import { I18nProvider, useI18n } from '../i18n';

const DistrictProfilePage = lazy(async () => {
  const module = await import('../features/district-profile/DistrictProfilePage');
  return { default: module.DistrictProfilePage };
});

const areas = [
  ['/', 'executiveDashboard'], ['/map-explorer', 'mapExplorer'],
  ['/district-profile', 'districtProfile'], ['/alerts', 'alerts'],
  ['/field-verification', 'fieldVerification'], ['/exposure', 'exposure'],
  ['/early-actions', 'earlyActions'], ['/notifications', 'notifications'],
  ['/data-health', 'dataHealth'], ['/ml-operations', 'mlOperations'],
  ['/scenario-lab', 'scenarioLab'], ['/reports', 'reports'],
  ['/partner-portal', 'partnerPortal'], ['/administration', 'administration'],
  ['/public-warnings', 'publicWarnings'],
] as const;

function AppShell() {
  const { language, setLanguage, t } = useI18n();
  return <div className="shell">
    <aside>
      <div className="brand">SOMALIA <strong>AI</strong></div>
      <p>{t('earlyWarningAction')}</p>
      <label className="language-control">{t('language')}
        <select aria-label={t('language')} value={language} onChange={(event) => setLanguage(event.target.value as 'en' | 'so')}>
          <option value="en">English</option><option value="so">Soomaali</option>
        </select>
      </label>
      <nav>{areas.map(([path, key]) => <NavLink key={path} to={path}>{t(key)}</NavLink>)}</nav>
      <NavLink className="signin" to="/login">{t('signIn')}</NavLink>
      <footer>{t('dataStatus')} <b>{t('governedApi')}</b></footer>
    </aside>
    <Routes>
      <Route path="/" element={<NationalDashboard />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/map-explorer" element={<MapExplorer />} />
      <Route path="/district-profile" element={<Suspense fallback={<main><div className="empty">Loading district profile…</div></main>}><DistrictProfilePage /></Suspense>} />
      <Route path="/alerts" element={<AlertCenterPage />} />
      <Route path="/field-verification" element={<FieldVerificationPage />} />
      <Route path="/exposure" element={<ExposurePage />} />
      <Route path="/early-actions" element={<EarlyActionsPage />} />
      <Route path="/notifications" element={<NotificationsPage />} />
      <Route path="/data-health" element={<DataHealthPage />} />
      <Route path="/ml-operations" element={<MlOperationsPage />} />
      <Route path="/scenario-lab" element={<ScenarioLabPage />} />
      <Route path="/reports" element={<ReportsPage />} />
      <Route path="/partner-portal" element={<PartnerPortalPage />} />
      <Route path="/administration" element={<AdministrationPage />} />
      <Route path="/public-warnings" element={<PublicWarningsPage />} />
      <Route path="*" element={<main><p className="eyebrow">{t('notFound')}</p><h1>{t('pageUnavailable')}</h1><div className="empty">{t('requestMissing')}</div></main>} />
    </Routes>
  </div>;
}

export function App() {
  return <I18nProvider><AppShell /></I18nProvider>;
}
