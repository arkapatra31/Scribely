import { useState } from "react";
import type { Session } from "@scribely/schemas";
import { formatClock, formatDate, sessionTitle } from "../format";

interface Props {
  session: Session;
  duration: number;
  live: boolean;
  onRename: (title: string) => void;
  onBackToLive?: () => void;
}

export function SessionHeader({ session, duration, live, onRename, onBackToLive }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const save = () => {
    setEditing(false);
    if (draft.trim() !== (session.title ?? "")) onRename(draft);
  };

  return (
    <div className="border-b border-stone-200 px-6 py-3 dark:border-stone-800">
      <div className="mx-auto flex max-w-2xl items-center gap-3">
        <div className="min-w-0 flex-1">
          {editing ? (
            <input
              autoFocus
              value={draft}
              maxLength={200}
              placeholder="Session title"
              onChange={(e) => setDraft(e.target.value)}
              onBlur={save}
              onKeyDown={(e) => {
                if (e.key === "Enter") save();
                if (e.key === "Escape") setEditing(false);
              }}
              className="w-full rounded border border-stone-300 bg-transparent px-2 py-0.5 font-medium outline-none focus:border-stone-500 dark:border-stone-700"
            />
          ) : (
            <button
              type="button"
              title="Rename"
              onClick={() => {
                setDraft(session.title ?? "");
                setEditing(true);
              }}
              className="max-w-full truncate rounded px-2 py-0.5 text-left font-medium hover:bg-stone-100 dark:hover:bg-stone-900"
            >
              {sessionTitle(session)}
            </button>
          )}
          <p className="px-2 text-xs text-stone-500">
            {formatDate(session.started_at)} · {formatClock(duration)}
            {live && session.status === "recording" && " · recording"}
            {session.status === "interrupted" && " · interrupted (Scribely closed mid-recording)"}
            {session.status === "failed" && " · stopped by an error"}
          </p>
        </div>
        {onBackToLive && (
          <button
            type="button"
            onClick={onBackToLive}
            className="shrink-0 rounded-full border border-red-300 px-3 py-1 text-xs text-red-600 hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950/40"
          >
            ● Back to live
          </button>
        )}
      </div>
    </div>
  );
}
