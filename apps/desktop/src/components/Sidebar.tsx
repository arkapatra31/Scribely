import { useEffect, useState } from "react";
import type { SessionSummary } from "@scribely/schemas";
import { formatClock, formatDate } from "../format";

interface Props {
  sessions: SessionSummary[];
  selectedId: string | null;
  recordingId: string | null;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}

export function Sidebar({ sessions, selectedId, recordingId, onOpen, onDelete }: Props) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-stone-200 dark:border-stone-800">
      <h2 className="px-4 pb-2 pt-4 text-xs font-medium uppercase tracking-wide text-stone-500">
        Sessions
      </h2>
      {sessions.length === 0 ? (
        <p className="px-4 text-sm text-stone-500">Your recordings will appear here.</p>
      ) : (
        <ul className="flex-1 overflow-y-auto px-2 pb-4">
          {sessions.map((s) => (
            <SessionItem
              key={s.session.id}
              summary={s}
              selected={s.session.id === selectedId}
              recording={s.session.id === recordingId}
              onOpen={onOpen}
              onDelete={onDelete}
            />
          ))}
        </ul>
      )}
    </aside>
  );
}

interface ItemProps {
  summary: SessionSummary;
  selected: boolean;
  recording: boolean;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}

function SessionItem({ summary, selected, recording, onOpen, onDelete }: ItemProps) {
  const { session, duration, segment_count } = summary;
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!confirming) return;
    const id = setTimeout(() => setConfirming(false), 3000);
    return () => clearTimeout(id);
  }, [confirming]);

  return (
    <li className="group relative">
      <button
        type="button"
        onClick={() => onOpen(session.id)}
        className={`w-full rounded-lg px-3 py-2 text-left transition ${
          selected
            ? "bg-stone-200/70 dark:bg-stone-800/70"
            : "hover:bg-stone-100 dark:hover:bg-stone-900"
        }`}
      >
        <span className="block truncate pr-14 text-sm font-medium">
          {session.title || formatDate(session.started_at)}
        </span>
        <span className="mt-0.5 block text-xs text-stone-500">
          {recording ? (
            <span className="text-red-500">● Recording</span>
          ) : (
            <>
              {session.title && <>{formatDate(session.started_at)} · </>}
              {formatClock(duration)}
              {segment_count === 0 && " · empty"}
              {summary.has_notes && <span className="text-emerald-600"> · notes</span>}
              {session.status === "interrupted" && <span className="text-amber-600"> · interrupted</span>}
              {session.status === "failed" && <span className="text-amber-600"> · failed</span>}
            </>
          )}
        </span>
      </button>
      {!recording && (
        <button
          type="button"
          onClick={() => (confirming ? onDelete(session.id) : setConfirming(true))}
          className={`absolute right-2 top-2 rounded px-2 py-0.5 text-xs transition ${
            confirming
              ? "bg-red-600 text-white"
              : "text-stone-500 opacity-0 hover:text-red-600 focus:opacity-100 group-hover:opacity-100"
          }`}
          aria-label={confirming ? "Confirm delete" : "Delete session"}
        >
          {confirming ? "Delete?" : "Delete"}
        </button>
      )}
    </li>
  );
}
