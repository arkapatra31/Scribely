import { useState } from "react";
import { ArrowLeft, CalendarDays, CircleAlert, Clock, Pencil } from "lucide-react";
import type { Session } from "@scribely/schemas";
import { formatDate, formatDuration, sessionTitle } from "../format";

interface Props {
  session: Session;
  duration: number;
  recording: boolean;
  onRename: (title: string) => void;
  onBackToLive?: () => void;
}

export function SessionHeader({ session, duration, recording, onRename, onBackToLive }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const save = () => {
    setEditing(false);
    if (draft.trim() !== (session.title ?? "")) onRename(draft);
  };

  return (
    <header className="px-10 pt-9">
      <div className="mx-auto max-w-3xl">
        {onBackToLive && (
          <button
            type="button"
            onClick={onBackToLive}
            className="mb-4 inline-flex items-center gap-1.5 rounded-full bg-rec-soft px-3 py-1 text-xs font-medium text-rec transition hover:brightness-95"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
            Back to the live recording
          </button>
        )}
        {editing ? (
          <input
            autoFocus
            value={draft}
            maxLength={200}
            placeholder="Name this session"
            onChange={(e) => setDraft(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") setEditing(false);
            }}
            className="w-full rounded-lg border border-line-strong bg-paper-raised px-2 py-1 font-serif text-[2rem] font-semibold leading-tight tracking-tight outline-none focus:border-accent"
          />
        ) : (
          <button
            type="button"
            onClick={() => {
              setDraft(session.title ?? "");
              setEditing(true);
            }}
            title="Rename"
            className="group -mx-2 flex max-w-full items-center gap-2 rounded-lg px-2 py-1 text-left transition hover:bg-paper-sunken"
          >
            <h1 className="truncate font-serif text-[2rem] font-semibold leading-tight tracking-tight">
              {sessionTitle(session)}
            </h1>
            <Pencil
              className="h-4 w-4 shrink-0 text-ink-faint opacity-0 transition group-hover:opacity-100"
              aria-hidden
            />
          </button>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <CalendarDays className="h-3.5 w-3.5" aria-hidden />
            {formatDate(session.started_at)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" aria-hidden />
            {formatDuration(duration)}
          </span>
          {recording && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-rec-soft px-2 py-0.5 text-xs font-medium text-rec">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rec" />
              Live
            </span>
          )}
          {session.status === "interrupted" && (
            <span className="inline-flex items-center gap-1.5 text-warn">
              <CircleAlert className="h-3.5 w-3.5" aria-hidden />
              Interrupted — Scribely closed mid-recording
            </span>
          )}
          {session.status === "failed" && (
            <span className="inline-flex items-center gap-1.5 text-warn">
              <CircleAlert className="h-3.5 w-3.5" aria-hidden />
              Stopped by an error
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
