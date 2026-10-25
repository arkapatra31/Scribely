import { useEffect, useState } from "react";
import type { Session } from "@scribely/schemas";
import { formatClock } from "../format";

interface Props {
  canStart: boolean;
  recording: boolean;
  busy: boolean;
  session: Session | null;
  onStart: () => void;
  onStop: () => void;
}

export function RecordControls({ canStart, recording, busy, session, onStart, onStop }: Props) {
  const elapsed = useElapsed(recording ? session?.started_at : undefined);
  return (
    <div className="flex items-center justify-center gap-4">
      {recording ? (
        <button
          key="stop"
          type="button"
          onClick={onStop}
          className="flex items-center gap-2 rounded-full bg-stone-900 px-6 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-stone-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-900 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-300"
        >
          <span className="h-3 w-3 rounded-sm bg-current" aria-hidden />
          Stop
        </button>
      ) : (
        <button
          key="start"
          type="button"
          onClick={onStart}
          disabled={!canStart || busy}
          className="flex items-center gap-2 rounded-full bg-red-600 px-6 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-red-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span className="h-3 w-3 rounded-full bg-white" aria-hidden />
          {busy ? "Starting…" : "Record"}
        </button>
      )}
      {recording && (
        <span className="font-mono text-sm tabular-nums text-stone-500" aria-label="Elapsed time">
          {formatClock(elapsed)}
        </span>
      )}
    </div>
  );
}

function useElapsed(startedAt: string | undefined): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return startedAt ? (now - Date.parse(startedAt)) / 1000 : 0;
}
