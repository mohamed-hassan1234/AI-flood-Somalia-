/**
 * Sign-in.
 *
 * Two-panel on desktop (context left, form right), single column on mobile.
 * The left panel states plainly what the platform does and — equally important
 * — what it does not do, so the governance model is visible before a user ever
 * reaches a warning.
 *
 * There is no social/OAuth sign-in and no self-service password reset: the
 * backend exposes neither, and offering a control that leads nowhere is worse
 * than omitting it.
 */

import { useEffect, useId, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, ShieldCheck, TriangleAlert } from 'lucide-react';

import { ApiError } from '../../api/client';
import { useAuth } from '../../app/providers/AuthProvider';
import { landingRoute } from '../../app/layouts/navigation';
import { Button, Field, Input, cx } from '../../components/ui/primitives';
import { LanguageToggle, useI18n } from '../../i18n';

interface LocationState {
  from?: string;
}

export function LoginPage() {
  const { t } = useI18n();
  const { state, signIn, capabilities } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const emailId = useId();
  const passwordId = useId();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const from = (location.state as LocationState | null)?.from;

  // Once the principal resolves, route onward to the first page this role can
  // actually use — a viewer has no business landing on a review queue.
  useEffect(() => {
    if (state === 'authenticated') {
      void navigate(from ?? landingRoute(capabilities), { replace: true });
    }
  }, [state, from, capabilities, navigate]);

  if (state === 'authenticated') {
    return <Navigate to={from ?? landingRoute(capabilities)} replace />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    setError(null);
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      // Navigation happens in the effect above once /auth/me resolves.
    } catch (caught) {
      if (caught instanceof ApiError) {
        // Never disclose which of the two fields was wrong.
        setError(
          caught.kind === 'unauthorized' || caught.kind === 'validation'
            ? 'Those credentials were not accepted. Check your email address and password.'
            : caught.message,
        );
      } else {
        setError('Sign-in could not be completed. Try again.');
      }
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-dvh bg-[--color-canvas] lg:grid lg:grid-cols-[1.05fr_minmax(420px,0.95fr)]">
      {/* Context panel — desktop only. */}
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-[--color-brand-900] p-10 text-white lg:flex xl:p-14">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 22% 18%, white 0, transparent 46%), radial-gradient(circle at 78% 74%, white 0, transparent 42%)',
          }}
        />

        <div className="relative flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-[--radius-md] bg-white/10">
            <svg viewBox="0 0 24 24" className="size-5" fill="currentColor" aria-hidden="true">
              <path d="M12 2.4l2.7 8.2h8.6l-6.9 5.1 2.6 8.3-7-5.1-7 5.1 2.6-8.3-6.9-5.1h8.6z" />
            </svg>
          </span>
          <span>
            <span className="block text-[13px] font-bold tracking-[0.03em]">SOMALIA AI</span>
            <span className="block text-[11px] text-white/60">{t('earlyWarningAction')}</span>
          </span>
        </div>

        <div className="relative max-w-lg">
          <h1 className="text-[32px] font-semibold leading-[1.15] tracking-[-0.025em] xl:text-[38px]">
            Earlier warning, backed by evidence you can inspect.
          </h1>
          <p className="mt-4 text-[15px] leading-6 text-white/70">
            Drought, river-flood and food-security risk intelligence for Somalia — with the
            underlying drivers, data freshness and model version attached to every signal.
          </p>

          <dl className="mt-9 flex flex-col gap-4 border-t border-white/15 pt-7">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-white/50" aria-hidden="true" />
              <div>
                <dt className="text-[13px] font-semibold">No warning publishes itself</dt>
                <dd className="mt-0.5 text-[13px] leading-5 text-white/60">
                  Every warning passes through analyst review and authorised approval before it
                  reaches anyone.
                </dd>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <TriangleAlert className="mt-0.5 size-4 shrink-0 text-white/50" aria-hidden="true" />
              <div>
                <dt className="text-[13px] font-semibold">Scope is stated, not implied</dt>
                <dd className="mt-0.5 text-[13px] leading-5 text-white/60">
                  Flood coverage is tied to supported river gauges. Food-security output is a model
                  signal, not an official IPC classification.
                </dd>
              </div>
            </div>
          </dl>
        </div>

        <p className="relative text-[12px] text-white/40">
          Authorised use only. Activity in this system is attributable to your account.
        </p>
      </aside>

      {/* Form panel. */}
      <div className="flex min-h-dvh flex-col justify-center px-5 py-10 sm:px-10 lg:min-h-0">
        <div className="mx-auto w-full max-w-[380px]">
          {/* Compact brand for small screens, where the context panel is hidden. */}
          <div className="mb-8 flex items-center justify-between lg:hidden">
            <div className="flex items-center gap-2.5">
              <span className="flex size-8 items-center justify-center rounded-[--radius-md] bg-[--color-brand-700] text-white">
                <svg viewBox="0 0 24 24" className="size-4.5" fill="currentColor" aria-hidden="true">
                  <path d="M12 2.4l2.7 8.2h8.6l-6.9 5.1 2.6 8.3-7-5.1-7 5.1 2.6-8.3-6.9-5.1h8.6z" />
                </svg>
              </span>
              <span>
                <span className="block text-[13px] font-bold tracking-[0.02em] text-[--color-ink]">
                  SOMALIA AI
                </span>
                <span className="block text-[11px] text-[--color-ink-muted]">
                  {t('earlyWarningAction')}
                </span>
              </span>
            </div>
          </div>

          <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-[--color-ink]">
            Sign in
          </h2>
          <p className="mt-1.5 text-[13px] leading-5 text-[--color-ink-secondary]">
            Use the account issued by your platform administrator.
          </p>

          {state === 'expired' && (
            <div
              className="mt-5 rounded-[--radius-md] bg-[--color-risk-watch-bg] px-3.5 py-3 text-[13px] leading-5 text-[--color-risk-watch-fg] ring-1 ring-inset ring-[--color-risk-watch-line]"
              role="status"
            >
              Your previous session ended and could not be renewed. Sign in again to continue.
            </div>
          )}

          <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4" noValidate>
            <Field label={t('emailLabel')} htmlFor={emailId}>
              <Input
                id={emailId}
                name="email"
                type="email"
                autoComplete="username"
                inputMode="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={error ? true : undefined}
                disabled={submitting}
              />
            </Field>

            <Field label={t('passwordLabel')} htmlFor={passwordId}>
              <div className="relative">
                <Input
                  id={passwordId}
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-invalid={error ? true : undefined}
                  disabled={submitting}
                  className="pr-11"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? t('hidePassword') : t('showPassword')}
                  aria-pressed={showPassword}
                  className={cx(
                    'absolute inset-y-0 right-0 flex w-10 items-center justify-center',
                    'text-[--color-ink-muted] transition-colors hover:text-[--color-ink]',
                  )}
                >
                  {showPassword ? (
                    <EyeOff className="size-4" aria-hidden="true" />
                  ) : (
                    <Eye className="size-4" aria-hidden="true" />
                  )}
                </button>
              </div>
            </Field>

            {error && (
              <div
                className="rounded-[--radius-md] bg-[--color-danger-bg] px-3.5 py-2.5 text-[13px] leading-5 text-[--color-danger-fg] ring-1 ring-inset ring-[--color-danger-line]"
                role="alert"
              >
                {error}
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              fullWidth
              loading={submitting || state === 'loading'}
              className="mt-1"
            >
              {submitting || state === 'loading' ? t('signingIn') : t('signIn')}
            </Button>
          </form>

          <div className="mt-8 flex items-center justify-between border-t border-[--color-line] pt-5">
            <LanguageToggle />
            <p className="text-[11px] text-[--color-ink-faint]">Authorised use only</p>
          </div>
        </div>
      </div>
    </div>
  );
}
