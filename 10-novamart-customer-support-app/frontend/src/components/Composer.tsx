import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { SendIcon } from './icons';

interface ComposerProps {
  disabled: boolean;
  onSend(text: string): void;
}

const MAX_ROWS_PX = 160;

export function Composer({ disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Grow the textarea with its content, then let it scroll at the cap.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_ROWS_PX)}px`;
  }, [value]);

  const trimmed = value.trim();
  const canSend = trimmed.length > 0 && !disabled;

  function submit() {
    if (!canSend) return;
    onSend(trimmed);
    setValue('');
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter inserts a newline, which is what people expect
    // from a chat box.
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={onSubmit} className="border-t border-white/10 bg-ink-950/80 px-4 py-4 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-end gap-3">
        <label className="sr-only" htmlFor="composer-input">
          Message
        </label>
        <textarea
          id="composer-input"
          ref={textareaRef}
          rows={1}
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={disabled ? 'Waiting for the agent…' : 'Ask about an order, return, or your account…'}
          aria-label="Message"
          className="field max-h-40 min-h-[2.75rem] flex-1 resize-none py-3"
        />
        <button
          type="submit"
          className="btn-primary h-11 w-11 shrink-0 p-0"
          disabled={!canSend}
          aria-label="Send message"
          title="Send message (Enter)"
        >
          <SendIcon />
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-[0.6875rem] text-slate-500">
        Press <kbd className="rounded bg-white/10 px-1 py-0.5 font-sans">Enter</kbd> to send,{' '}
        <kbd className="rounded bg-white/10 px-1 py-0.5 font-sans">Shift + Enter</kbd> for a new
        line.
      </p>
    </form>
  );
}