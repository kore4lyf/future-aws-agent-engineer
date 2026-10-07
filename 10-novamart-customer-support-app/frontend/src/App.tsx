import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useChatStore } from '@/hooks/useChatStore';
import { config } from '@/config';
import { AuthScreen } from '@/components/AuthScreen';
import { Composer } from '@/components/Composer';
import { MessageBubble, TypingIndicator } from '@/components/MessageBubble';
import { SessionList } from '@/components/SessionList';
import { BotIcon, MenuIcon, SignOutIcon } from '@/components/icons';

export function App() {
  const { user, initialising, signOut } = useAuth();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);

  const handleUnauthorized = useCallback(() => {
    // The gateway rejected the token. Sign out so the user lands on a clean
    // sign-in form instead of a chat that silently fails.
    void signOut();
  }, [signOut]);

  const chat = useChatStore(handleUnauthorized);
  const { messages, sending } = chat;

  // Pin to the newest message, but only when the transcript is already near the
  // bottom. Scrolling away to read history should not be hijacked.
  const nearBottomRef = useRef(true);

  useEffect(() => {
    const el = transcriptRef.current;
    if (!el) return;
    const onScroll = () => {
      nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  useLayoutEffect(() => {
    const el = transcriptRef.current;
    if (el && nearBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, sending]);

  if (initialising) {
    return (
      <div className="flex min-h-full items-center justify-center" role="status" aria-live="polite">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-white/20 border-t-brand-400" />
        <span className="sr-only">Loading your session</span>
      </div>
    );
  }

  if (!user) {
    return (
      <>
        <AuthScreen />
        {!config.cognito && !config.demoMode && <ConfigNotice />}
      </>
    );
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <SessionList
        sessions={chat.sessions}
        activeSessionId={chat.activeSessionId}
        loading={chat.loadingSessions}
        mobileOpen={mobileNavOpen}
        onSelect={chat.selectSession}
        onNewSession={chat.newSession}
        onDelete={(id: string) => void chat.deleteSession(id)}
        onCloseMobile={() => setMobileNavOpen(false)}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-white/10 bg-ink-950/80 px-4 py-3 backdrop-blur">
          <button
            type="button"
            className="btn-ghost h-9 w-9 p-0 lg:hidden"
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open conversation list"
            aria-expanded={mobileNavOpen}
          >
            <MenuIcon />
          </button>

          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-500/15 text-brand-300 ring-1 ring-brand-400/30">
            <BotIcon />
          </div>

          <div className="min-w-0 flex-1">
            <h1 className="truncate text-sm font-semibold text-slate-100">NovaMart Support</h1>
            <p className="truncate text-xs text-slate-500">
              {config.demoMode ? 'Demo agent · offline sample replies' : chat.health?.live
                ? 'Connected to support agent'
                : 'Reconnecting…'}
            </p>
          </div>

          <span className="hidden max-w-[14rem] truncate text-xs text-slate-400 sm:block">
            {user.email}
          </span>
          <button type="button" className="btn-ghost" onClick={() => void signOut()}>
            <SignOutIcon />
            <span className="hidden sm:inline">Sign out</span>
            <span className="sr-only sm:hidden">Sign out</span>
          </button>
        </header>

        {chat.error && (
          <div
            role="alert"
            className="flex items-start gap-3 border-b border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-200"
          >
            <span className="flex-1">{chat.error}</span>
            <button
              type="button"
              className="rounded-lg px-2 py-0.5 text-xs font-medium text-red-200 hover:bg-red-500/20"
              onClick={chat.clearError}
            >
              Dismiss
            </button>
          </div>
        )}

        <div
          ref={transcriptRef}
          className="min-h-0 flex-1 overflow-y-auto px-4 py-6"
          role="log"
          aria-live="polite"
          aria-label="Conversation"
        >
          <div className="mx-auto flex max-w-3xl flex-col gap-5">
            {isEmpty ? (
              <EmptyState />
            ) : (
              messages.map((message) => <MessageBubble key={message.id} message={message} />)
            )}
            {sending && <TypingIndicator />}
          </div>
        </div>

        <Composer disabled={sending} onSend={(text: string) => void chat.sendMessage(text)} />
      </div>
    </div>
  );
}

function EmptyState() {
  const prompts = [
    'Where is my order?',
    'How do I return an item?',
    'I cannot log in to my account',
  ];
  return (
    <div className="flex flex-col items-center py-12 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-500/10 text-brand-300 ring-1 ring-brand-400/20">
        <BotIcon className="h-6 w-6" />
      </div>
      <h2 className="text-base font-medium text-slate-200">How can we help?</h2>
      <p className="mt-1 max-w-sm text-sm text-slate-400">
        Ask a question and our support agent will get back to you right away.
      </p>
      <ul className="mt-6 flex flex-wrap justify-center gap-2">
        {prompts.map((prompt) => (
          <li
            key={prompt}
            className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300"
          >
            {prompt}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Shown when no Cognito values are present, so the setup gap is explicit. */
function ConfigNotice() {
  return (
    <div className="fixed inset-x-4 bottom-4 mx-auto max-w-lg rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100 shadow-lg">
      <p className="font-medium">Cognito is not configured yet</p>
      <p className="mt-1 text-amber-200/80">
        Sign-in is running against the local demo provider. Set{' '}
        <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-xs">
          VITE_COGNITO_USER_POOL_ID
        </code>{' '}
        and{' '}
        <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-xs">
          VITE_COGNITO_USER_POOL_CLIENT_ID
        </code>{' '}
        in <code className="font-mono text-xs">frontend/.env.local</code> to connect the real user
        pool.
      </p>
    </div>
  );
}