import { useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';
import { BotIcon } from './icons';

type Mode = 'signin' | 'signup';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Cognito requires 8+ chars with upper, lower, and a digit. */
function passwordProblems(password: string): string[] {
  const problems: string[] = [];
  if (password.length < 8) problems.push('at least 8 characters');
  if (!/[a-z]/.test(password)) problems.push('a lowercase letter');
  if (!/[A-Z]/.test(password)) problems.push('an uppercase letter');
  if (!/\d/.test(password)) problems.push('a number');
  return problems;
}

export function AuthScreen() {
  const { signIn, signUp, challenge, confirmSignUp, resolveChallenge, clearChallenge } = useAuth();
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Verification-code form state.
  const [code, setCode] = useState('');
  const [resolveBusy, setResolveBusy] = useState(false);

  const isSignUp = mode === 'signup';
  const passwordIssues = isSignUp ? passwordProblems(password) : [];
  const canSubmit =
    !busy &&
    EMAIL_PATTERN.test(email.trim()) &&
    password.length >= 8 &&
    passwordIssues.length === 0;

  const isConfirmingEmail = challenge?.step === 'CONFIRM_SIGN_UP';
  const canResolve = !resolveBusy && code.trim().length === 6;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (isSignUp) {
        const result = await signUp(email.trim(), password);
        // A CONFIRMED sign-up signs the user in already; anything else needs
        // the message to stay on screen.
        setNotice(result.message);
        if (result.status === 'CONFIRMED') setPassword('');
      } else {
        await signIn(email.trim(), password);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function onResolve(event: FormEvent) {
    event.preventDefault();
    if (!canResolve) return;
    setResolveBusy(true);
    setError(null);
    try {
      if (isConfirmingEmail && challenge && challenge.step === 'CONFIRM_SIGN_UP') {
        await confirmSignUp({ email: challenge.email, code: code.trim(), password: challenge.password });
      } else {
        await resolveChallenge({ code: code.trim() });
      }
      setCode('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed. Try again.');
    } finally {
      setResolveBusy(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setNotice(null);
    setPassword('');
  }

  function backToSignIn() {
    clearChallenge();
    setMode('signin');
    setError(null);
    setNotice(null);
  }

  return (
    <main className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-500/15 text-brand-300 ring-1 ring-brand-400/30">
            <BotIcon className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-50">NovaMart Support</h1>
          <p className="mt-1.5 text-sm text-slate-400">
            {isConfirmingEmail
              ? 'Enter the code we sent to your email.'
              : isSignUp
                ? 'Create an account to chat with our team.'
                : 'Sign in to chat with our team.'}
          </p>
        </div>

        <div className="card p-6 shadow-xl shadow-black/20">
          {isConfirmingEmail ? (
            <form onSubmit={onResolve} noValidate>
              <label className="mb-1.5 block text-sm font-medium text-slate-300" htmlFor="code">
                Confirmation code
              </label>
              <input
                id="code"
                name="code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                className="field mb-2"
                placeholder="123456"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                disabled={resolveBusy}
                maxLength={6}
              />
              <p className="text-xs text-slate-400">
                Check <span className="font-medium text-slate-200">{challenge.email}</span> for the 6-digit code.
              </p>

              {error && (
                <p
                  role="alert"
                  className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 py-2.5 text-sm text-red-200"
                >
                  {error}
                </p>
              )}

              <button type="submit" className="btn-primary mt-5 w-full" disabled={!canResolve}>
                {resolveBusy ? 'Verifying…' : 'Verify email'}
              </button>

              <div className="mt-5 border-t border-white/10 pt-4 text-center">
                <p className="text-sm text-slate-400">
                  <button
                    type="button"
                    onClick={backToSignIn}
                    className="font-medium text-brand-300 hover:text-brand-200"
                  >
                    Back to sign in
                  </button>
                </p>
              </div>
            </form>
          ) : (
            <>
              <form onSubmit={onSubmit} noValidate>
                <label className="mb-1.5 block text-sm font-medium text-slate-300" htmlFor="email">
                  Email
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  className="field mb-4"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={busy}
                />

                <label className="mb-1.5 block text-sm font-medium text-slate-300" htmlFor="password">
                  Password
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete={isSignUp ? 'new-password' : 'current-password'}
                  required
                  className="field"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={busy}
                  aria-describedby={isSignUp ? 'password-hint' : undefined}
                />

                {isSignUp && password.length > 0 && (
                  <div id="password-hint" className="mt-3">
                    {passwordIssues.length > 0 ? (
                      <ul className="space-y-1 text-xs text-slate-400">
                        {passwordIssues.map((issue) => (
                          <li key={issue} className="flex items-center gap-1.5">
                            <span className="h-1 w-1 rounded-full bg-amber-400" aria-hidden="true" />
                            Add {issue}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="flex items-center gap-1.5 text-xs text-brand-300">
                        <span className="h-1.5 w-1.5 rounded-full bg-brand-400" aria-hidden="true" />
                        Password looks good
                      </p>
                    )}
                  </div>
                )}

                {error && (
                  <p
                    role="alert"
                    className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 py-2.5 text-sm text-red-200"
                  >
                    {error}
                  </p>
                )}

                {notice && (
                  <p
                    role="status"
                    className="mt-4 rounded-xl border border-brand-500/30 bg-brand-500/10 px-3.5 py-2.5 text-sm text-brand-100"
                  >
                    {notice}
                  </p>
                )}

                <button type="submit" className="btn-primary mt-5 w-full" disabled={!canSubmit}>
                  {busy ? 'Please wait…' : isSignUp ? 'Create account' : 'Sign in'}
                </button>
              </form>

              <div className="mt-5 border-t border-white/10 pt-4 text-center">
                <p className="text-sm text-slate-400">
                  {isSignUp ? 'Already have an account?' : 'New to NovaMart?'}{' '}
                  <button
                    type="button"
                    onClick={() => switchMode(isSignUp ? 'signin' : 'signup')}
                    className="font-medium text-brand-300 hover:text-brand-200"
                  >
                    {isSignUp ? 'Sign in' : 'Create an account'}
                  </button>
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </main>
  );
}