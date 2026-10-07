import type { ChatSession } from '@/types/api';
import { CloseIcon, PlusIcon, TrashIcon } from './icons';

interface SessionListProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  loading: boolean;
  mobileOpen: boolean;
  onSelect(sessionId: string): void;
  onNewSession(): void;
  onDelete(sessionId: string): void;
  onCloseMobile(): void;
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function SessionList({
  sessions,
  activeSessionId,
  loading,
  mobileOpen,
  onSelect,
  onNewSession,
  onDelete,
  onCloseMobile,
}: SessionListProps) {
  return (
    <>
      {/* Scrim closes the drawer on mobile; hidden on desktop where the rail is static. */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        aria-label="Conversation history"
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-white/10 bg-ink-900 transition-transform duration-200 lg:static lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-3.5">
          <h2 className="text-sm font-semibold tracking-wide text-slate-200 uppercase">Conversations</h2>
          <button
            type="button"
            className="btn-ghost h-8 w-8 p-0 lg:hidden"
            onClick={onCloseMobile}
            aria-label="Close conversation list"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="px-3 py-3">
          <button type="button" className="btn-primary w-full" onClick={onNewSession}>
            <PlusIcon className="h-4 w-4" />
            New conversation
          </button>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          {loading ? (
            <ul className="space-y-2" aria-hidden="true">
              {[0, 1, 2].map((i) => (
                <li key={i} className="h-14 animate-pulse rounded-xl bg-white/5" />
              ))}
            </ul>
          ) : sessions.length === 0 ? (
            <p className="px-2 py-8 text-center text-sm text-slate-500">
              No conversations yet.
              <br />
              Start one below.
            </p>
          ) : (
            <ul className="space-y-1">
              {sessions.map((session) => {
                const active = session.sessionId === activeSessionId;
                return (
                  <li key={session.sessionId}>
                    <div
                      className={`group flex items-start gap-1 rounded-xl transition-colors ${
                        active ? 'bg-brand-500/15 ring-1 ring-brand-500/30' : 'hover:bg-white/5'
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          onSelect(session.sessionId);
                          onCloseMobile();
                        }}
                        aria-current={active ? 'true' : undefined}
                        className="min-w-0 flex-1 px-3 py-2.5 text-left"
                      >
                        <span
                          className={`block truncate text-sm font-medium ${
                            active ? 'text-brand-100' : 'text-slate-200'
                          }`}
                        >
                          {session.title}
                        </span>
                        <span className="mt-0.5 block text-xs text-slate-500">
                          {relativeTime(session.updatedAt)}
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(session.sessionId)}
                        aria-label={`Delete conversation: ${session.title}`}
                        title="Delete conversation"
                        className="mt-2.5 mr-1.5 rounded-lg p-1.5 text-slate-500 opacity-0 transition group-hover:opacity-100 focus-visible:opacity-100 hover:bg-red-500/15 hover:text-red-300"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>
      </aside>
    </>
  );
}