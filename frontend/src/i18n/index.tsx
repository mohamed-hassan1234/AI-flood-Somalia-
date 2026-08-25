import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type Language = 'en' | 'so';

const en = {
  earlyWarningAction: 'Early Warning & Action', executiveDashboard: 'Executive Dashboard',
  mapExplorer: 'Map Explorer', districtProfile: 'District Profile', alerts: 'Alerts',
  fieldVerification: 'Field Verification', exposure: 'Exposure', earlyActions: 'Early Actions',
  notifications: 'Notifications', dataHealth: 'Data Health', mlOperations: 'ML Operations',
  scenarioLab: 'Scenario Lab', reports: 'Reports', publicWarnings: 'Public Warnings',
  partnerPortal: 'Partner Portal', administration: 'Administration',
  signIn: 'Sign in', dataStatus: 'Data status', governedApi: 'Governed API', language: 'Language',
  executiveEyebrow: 'NATIONAL SITUATION ROOM', trustedEvidence: 'Trusted evidence.',
  earlierAction: 'Earlier action.', executiveLead: 'Human-governed intelligence for drought, river flood, flash flood, and food-security deterioration across Somalia.',
  executiveGeography: 'Executive geography', national: 'National', signInRequired: 'Sign in required',
  nationalRestricted: 'The national analytical summary is restricted to authorized national users.',
  loadingEvidence: 'Loading governed national evidence…', accessNotAuthorized: 'Access not authorized',
  summaryUnavailable: 'National summary unavailable', publishedWarnings: '{count} published warnings',
  boundary: 'Boundary {version}', currentRiskDomains: 'Current risk domains', drought: 'Drought',
  riverFlood: 'River flood', flashFlood: 'Flash flood', foodSecurity: 'Food security',
  unknown: 'unknown', areasEvaluated: '{count} areas evaluated', noEvidence: 'No governed evidence available',
  stale: 'STALE', current: 'CURRENT', sources: '{count} SOURCES', asOf: 'As of {date}',
  notFound: 'NOT FOUND', pageUnavailable: 'Page unavailable', requestMissing: 'The requested page does not exist.',
} as const;

type TranslationKey = keyof typeof en;
const so: Record<TranslationKey, string> = {
  earlyWarningAction: 'Digniin Hore iyo Tallaabo', executiveDashboard: 'Guddiga Fulinta',
  mapExplorer: 'Sahamiyaha Khariidadda', districtProfile: 'Xogta Degmada', alerts: 'Digniinaha',
  fieldVerification: 'Xaqiijinta Goobta', exposure: 'Soo-gaadhista', earlyActions: 'Tallaabooyinka Hore',
  notifications: 'Ogeysiisyada', dataHealth: 'Caafimaadka Xogta', mlOperations: 'Hawlgallada ML',
  scenarioLab: 'Shaybaarka Muuqaallada', reports: 'Warbixinnada', publicWarnings: 'Digniinaha Dadweynaha',
  partnerPortal: 'Bogga Wada-hawlgalayaasha', administration: 'Maamulka',
  signIn: 'Gal', dataStatus: 'Xaaladda xogta', governedApi: 'API la maamulo', language: 'Luqadda',
  executiveEyebrow: 'QOLKA XAALADDA QARANKA', trustedEvidence: 'Caddeyn lagu kalsoon yahay.',
  earlierAction: 'Tallaabo hore.', executiveLead: 'Sirdoon ay dadku maamulaan oo ku saabsan abaarta, fatahaadda webiga, daadadka degdegga ah iyo sii xumaanshaha sugnaanta cuntada Soomaaliya.',
  executiveGeography: 'Juqraafiga fulinta', national: 'Qaran', signInRequired: 'Gelitaan ayaa loo baahan yahay',
  nationalRestricted: 'Soo koobidda falanqaynta qaranka waxaa heli kara oo keliya isticmaalayaasha qaranka ee la oggolaaday.',
  loadingEvidence: 'Waxaa la soo rarayaa caddeynta qaranka ee la maamulo…', accessNotAuthorized: 'Gelitaanka lama oggola',
  summaryUnavailable: 'Soo koobidda qaranka lama heli karo', publishedWarnings: '{count} digniino la daabacay',
  boundary: 'Soohdin {version}', currentRiskDomains: 'Qaybaha khatarta hadda', drought: 'Abaar',
  riverFlood: 'Fatahaad webi', flashFlood: 'Daad degdeg ah', foodSecurity: 'Sugnaanta cuntada',
  unknown: 'aan la garanayn', areasEvaluated: '{count} deegaan la qiimeeyay', noEvidence: 'Caddeyn la maamulo lama heli karo',
  stale: 'DUUG AH', current: 'HADDA', sources: '{count} ILOOD', asOf: 'Waqtiga {date}',
  notFound: 'LAMA HELIN', pageUnavailable: 'Bogga lama heli karo', requestMissing: 'Bogga la codsaday ma jiro.',
};

type I18nValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: TranslationKey, values?: Record<string, string | number>) => string;
};

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() =>
    localStorage.getItem('somalia-ai-language') === 'so' ? 'so' : 'en');
  useEffect(() => {
    localStorage.setItem('somalia-ai-language', language);
    document.documentElement.lang = language;
  }, [language]);
  const value = useMemo<I18nValue>(() => ({
    language,
    setLanguage,
    t: (key, values = {}) => Object.entries(values).reduce(
      (message, [name, replacement]) => message.replace(`{${name}}`, String(replacement)),
      (language === 'so' ? so : en)[key],
    ),
  }), [language]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error('useI18n must be used within I18nProvider');
  return value;
}
