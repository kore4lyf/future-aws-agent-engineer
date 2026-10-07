import type { ChatMessage } from '@/types/api';
import { BotIcon } from './icons';

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  if (message.role === 'system') {
    return (
      <div className="my-1 flex justify-center">
        <p className="rounded-full bg-white/5 px-3 py-1 text-center text-xs text-slate-400">
          {message.content}
        </p>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          isUser ? 'bg-brand-500 text-ink-950' : 'bg-ink-800 text-brand-200 ring-1 ring-white/10'
        }`}
        aria-hidden="true"
      >
        {isUser ? 'You' : <BotIcon className="h-4 w-4" />}
      </div>

      <div className={`max-w-[min(42rem,80%)] ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-[0.9375rem] leading-relaxed whitespace-pre-wrap ${
            isUser
              ? 'rounded-tr-sm bg-brand-600 text-white'
              : 'rounded-tl-sm bg-ink-800 text-slate-100 ring-1 ring-white/5'
          }`}
        >
          {message.content}
        </div>
        <time
          dateTime={message.createdAt}
          className="mt-1 px-1 text-[0.6875rem] text-slate-500 tabular-nums"
        >
          {formatTime(message.createdAt)}
        </time>
      </div>
    </div>
  );
}

/** Three-dot placeholder shown while the agent is generating a reply. */
export function TypingIndicator() {
  return (
    <div className="flex gap-3" aria-live="polite" aria-label="Agent is typing">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-800 text-brand-200 ring-1 ring-white/10">
        <BotIcon className="h-4 w-4" />
      </div>
      <div className="rounded-2xl rounded-tl-sm bg-ink-800 px-4 py-3 ring-1 ring-white/5">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400"
              style={{ animationDelay: `${i * 160}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}