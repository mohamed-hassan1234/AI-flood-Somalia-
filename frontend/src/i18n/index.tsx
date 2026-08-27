import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type Language = 'en' | 'so';

/**
 * Bilingual strings for navigation, session flow and the status vocabulary an
 * operator reads constantly.
 *
 * Scope note: this dictionary deliberately covers wayfinding and common
 * operational status rather than every string in the product. Domain-technical
 * copy — model driver names, methodology caveats, lineage fields — stays in
 * English, which is the working language of the underlying scientific
 * contract. Half-translating a suppression reason or a scope limitation would
 * be worse than not translating it, because a mistranslated caveat is a
 * safety problem, not a cosmetic one.
 */
const en = {
  /* identity */
  earlyWarningAction: 'Early Warning & Early Action',
  productName: 'Somalia AI',

  /* navigation */
  navOverview: 'Overview',
  navRiskMap: 'Risk Map',
  navDrought: 'Drought',
  navFlood: 'River Flood',
  navFoodSecurity: 'Food Security',
  navWarnings: 'Warning Center',
  navHistory: 'Historical Intelligence',
  navReports: 'Reports',
  navDataHealth: 'Data Health',
  navModels: 'Model Operations',
  navAdmin: 'Administration',
  navProfile: 'Profile & Access',

  /* session */
  signIn: 'Sign in',
  signOut: 'Sign out',
  signingIn: 'Signing in…',
  emailLabel: 'Email address',
  passwordLabel: 'Password',
  showPassword: 'Show password',
  hidePassword: 'Hide password',
  signInRequired: 'Sign in required',
  language: 'Language',

  /* risk domains */
  drought: 'Drought',
  riverFlood: 'River flood',
  flashFlood: 'Flash flood',
  foodSecurity: 'Food security',

  /* severity */
  severityNormal: 'Normal',
  severityWatch: 'Watch',
  severityWarning: 'Warning',
  severityCritical: 'Critical',
  severityUnknown: 'Unknown',

  /* status vocabulary */
  national: 'National',
  asOf: 'As of {date}',
  stale: 'Stale',
  current: 'Current',
  unknown: 'Unknown',
  dataStatus: 'Data status',
  loading: 'Loading…',
  retry: 'Try again',
  accessNotAuthorized: 'Access not authorised',
  noEvidence: 'No evidence available',
  notFound: 'Not found',
  pageUnavailable: 'Page unavailable',
  requestMissing: 'The requested page does not exist.',
} as const;

type TranslationKey = keyof typeof en;

const so: Record<TranslationKey, string> = {
  earlyWarningAction: 'Digniin Hore iyo Tallaabo Hore',
  productName: 'Somalia AI',

  navOverview: 'Guudmar',
  navRiskMap: 'Khariidadda Khatarta',
  navDrought: 'Abaar',
  navFlood: 'Fatahaad Webi',
  navFoodSecurity: 'Sugnaanta Cuntada',
  navWarnings: 'Xarunta Digniinaha',
  navHistory: 'Sirdoonka Taariikhiga',
  navReports: 'Warbixinnada',
  navDataHealth: 'Caafimaadka Xogta',
  navModels: 'Hawlgallada Moodalka',
  navAdmin: 'Maamulka',
  navProfile: 'Astaanta & Gelitaanka',

  signIn: 'Gal',
  signOut: 'Ka bax',
  signingIn: 'Waa la galayaa…',
  emailLabel: 'Cinwaanka iimaylka',
  passwordLabel: 'Furaha sirta ah',
  showPassword: 'Muuji furaha',
  hidePassword: 'Qari furaha',
  signInRequired: 'Gelitaan ayaa loo baahan yahay',
  language: 'Luqadda',

  drought: 'Abaar',
  riverFlood: 'Fatahaad webi',
  flashFlood: 'Daad degdeg ah',
  foodSecurity: 'Sugnaanta cuntada',

  severityNormal: 'Caadi',
  severityWatch: 'Ilaalin',
  severityWarning: 'Digniin',
  severityCritical: 'Halis weyn',
  severityUnknown: 'Aan la garanayn',

  national: 'Qaran',
  asOf: 'Waqtiga {date}',
  stale: 'Duug ah',
  current: 'Hadda',
  unknown: 'Aan la garanayn',
  dataStatus: 'Xaaladda xogta',
  loading: 'Waa la soo rarayaa…',
  retry: 'Isku day mar kale',
  accessNotAuthorized: 'Gelitaanka lama oggola',
  noEvidence: 'Caddeyn lama heli karo',
  notFound: 'Lama helin',
  pageUnavailable: 'Bogga lama heli karo',
  requestMissing: 'Bogga la codsaday ma jiro.',
};

interface I18nValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: TranslationKey, values?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

const STORAGE_KEY = 'somalia-ai-language';

function readStoredLanguage(): Language {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'so' ? 'so' : 'en';
  } catch {
    // Storage access can throw in hardened browser configurations.
    return 'en';
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(readStoredLanguage);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, language);
    } catch {
      // Persisting the preference is best-effort; the session still works.
    }
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo<I18nValue>(
    () => ({
      language,
      setLanguage,
      t: (key, values = {}) => {
        const dictionary = language === 'so' ? so : en;
        // An unknown key returns the key itself rather than `undefined`, so a
        // missing translation degrades to a visible label instead of a crash.
        const template: string = dictionary[key] ?? String(key);
        return Object.entries(values).reduce(
          (message, [name, replacement]) => message.replace(`{${name}}`, String(replacement)),
          template,
        );
      },
    }),
    [language],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error('useI18n must be used within I18nProvider');
  return value;
}

/** Language toggle used in the sign-in page and profile screen. */
export function LanguageToggle({ className }: { className?: string }) {
  const { language, setLanguage, t } = useI18n();
  return (
    <label className={className}>
      <span className="sr-only">{t('language')}</span>
      <select
        aria-label={t('language')}
        value={language}
        onChange={(event) => setLanguage(event.target.value as Language)}
        className="h-9 rounded-[--radius-md] bg-[--color-surface] px-2.5 text-[13px] text-[--color-ink] ring-1 ring-inset ring-[--color-line-strong] focus:ring-2 focus:ring-[--color-brand-600]"
      >
        <option value="en">English</option>
        <option value="so">Soomaali</option>
      </select>
    </label>
  );
}
