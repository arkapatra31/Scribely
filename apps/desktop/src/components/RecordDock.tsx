import { useEffect, useState } from "react";
import { LoaderCircle, Mic, Square } from "lucide-react";
import { formatClock } from "../format";
import { Listening } from "./Listening";

interface Props {
  canStart: boolean;
  recording: boolean;
  stopping: boolean;
  loadingModel: boolean;
  startedAt: string | undefined;
  onStart: () => void;
  onStop: () => void;
}

/** Floating record control at the bottom of the main pane. */
export function RecordDock(props: Props) {
  const { canStart, recording, stopping, loadingModel } = props;
  const elapsed = useElapsed(recording ? props.startedAt : undefined);

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
      <div className="pointer-events-auto flex items-center gap-3 rounded-full border border-line bg-paper-raised/90 py-2 pl-2 pr-5 shadow-float backdrop-blur">
        {recording ? (
          <button
            key="stop"
            type="button"
            onClick={props.onStop}
            disabled={stopping}
            aria-label="Stop recording"
            className="flex h-11 w-11 animate-ring items-center justify-center rounded-full bg-rec text-white transition hover:brightness-110 disabled:animate-none disabled:opacity-60"
          >
            <Square className="h-4 w-4 fill-current" aria-hidden />
          </button>
        ) : (
          <button
            key="start"
            type="button"
            onClick={props.onStart}
            disabled={!canStart || loadingModel}
            aria-label="Record"
            className="flex h-11 w-11 items-center justify-center rounded-full bg-rec text-white shadow-soft transition hover:scale-105 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
          >
            {loadingModel ? (
              <LoaderCircle className="h-5 w-5 animate-spin" aria-hidden />
            ) : (
              <Mic className="h-5 w-5" aria-hidden />
            )}
          </button>
        )}
        {recording ? (
          <span className="flex items-center gap-3">
            <span className="font-mono text-sm tabular-nums">{formatClock(elapsed)}</span>
            <span className="flex items-center gap-2 text-sm text-ink-muted">
              <Listening className="text-rec" />
              {stopping ? "Finishing…" : "Listening"}
            </span>
          </span>
        ) : (
          <span className="text-sm text-ink-muted">
            {loadingModel ? "Loading the speech model…" : canStart ? "Record" : "Offline"}
          </span>
        )}
      </div>
    </div>
  );
}

function useElapsed(startedAt: string | undefined): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return startedAt ? (now - Date.parse(startedAt)) / 1000 : 0;
}
