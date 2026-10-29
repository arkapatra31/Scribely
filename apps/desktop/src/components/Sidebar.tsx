import { useEffect, useState } from "react";
import { CircleAlert, NotebookPen, Settings, Sparkles, Trash2 } from "lucide-react";
import type { SessionSummary } from "@scribely/schemas";
import { dayGroup, formatDuration, formatTime, sessionTitle } from "../format";

interface Props {
  sessions: SessionSummary[];
  selectedId: string | null;
  recordingId: string | null;
  connection: { label: string; tone: "ok" | "busy" | "off" };
  llm: { label: string; ready: boolean } | null;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
}

export function Sidebar(props: Props) {
  const { sessions, selectedId, recordingId, connection, llm } = props;
  const groups = groupByDay(sessions);

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-line bg-paper-sunken">
      <div
        data-tauri-drag-region
        className="flex h-16 shrink-0 items-center gap-2.5 px-5 [.platform-mac_&]:h-[5.5rem] [.platform-mac_&]:pt-7"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-accent text-white shadow-soft dark:text-paper">
          <NotebookPen className="h-4 w-4" aria-hidden />
        </span>
        <span className="font-serif text-[1.35rem] font-semibold tracking-tight">Scribely</span>
        <span
          className="ml-auto flex items-center gap-1.5 text-[11px] text-ink-faint"
          title={connection.label}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              connection.tone === "ok"
                ? "bg-ok"
                : connection.tone === "busy"
                  ? "animate-pulse bg-warn"
                  : "bg-ink-faint"
            }`}
          />
          {connection.label}
        </span>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-4" aria-label="Sessions">
        {sessions.length === 0 ? (
          <div className="mx-2 mt-2 rounded-xl border border-dashed border-line-strong px-4 py-6 text-center text-sm text-ink-muted">
            Your recordings will appear here.
          </div>
        ) : (
          groups.map(([label, items]) => (
            <section key={label} className="mb-3">
              <h2 className="px-3 pb-1.5 pt-3 text-[11px] font-medium uppercase tracking-[0.08em] text-ink-faint">
                {label}
              </h2>
              <ul className="space-y-0.5">
                {items.map((s) => (
                  <SessionItem
                    key={s.session.id}
                    summary={s}
                    selected={s.session.id === selectedId}
                    recording={s.session.id === recordingId}
                    onOpen={props.onOpen}
                    onDelete={props.onDelete}
                  />
                ))}
              </ul>
            </section>
          ))
        )}
      </nav>

      <div className="border-t border-line p-3">
        <button
          type="button"
          onClick={props.onOpenSettings}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-paper-raised"
        >
          <Settings className="h-4 w-4 text-ink-muted" aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">Settings</span>
            <span className="block truncate text-xs text-ink-muted">
              {llm ? llm.label : "Notes model"}
            </span>
          </span>
          {llm && (
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${llm.ready ? "bg-ok" : "bg-warn"}`}
              title={llm.ready ? "Ready to summarize" : "Needs attention"}
            />
          )}
        </button>
      </div>
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
  const { session, duration, segment_count, has_notes } = summary;
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
        aria-current={selected ? "true" : undefined}
        className={`w-full rounded-xl px-3 py-2.5 text-left transition ${
          selected ? "bg-paper-raised shadow-soft" : "hover:bg-paper-raised/60"
        }`}
      >
        <span className="flex items-center gap-1.5 pr-7">
          <span className="truncate text-sm font-medium">
            {sessionTitle(session)}
          </span>
          {has_notes && (
            <Sparkles className="h-3 w-3 shrink-0 text-accent" aria-label="Has notes" />
          )}
        </span>
        <span className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-muted">
          {recording ? (
            <span className="flex items-center gap-1.5 font-medium text-rec">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rec" />
              Recording
            </span>
          ) : (
            <>
              <span>{formatTime(session.started_at)}</span>
              <span className="text-ink-faint">·</span>
              <span>{segment_count === 0 ? "Empty" : formatDuration(duration)}</span>
              {(session.status === "interrupted" || session.status === "failed") && (
                <CircleAlert
                  className="h-3 w-3 text-warn"
                  aria-label={session.status === "failed" ? "Stopped by an error" : "Interrupted"}
                />
              )}
            </>
          )}
        </span>
      </button>
      {!recording && (
        <button
          type="button"
          onClick={() => (confirming ? onDelete(session.id) : setConfirming(true))}
          aria-label={confirming ? "Confirm delete" : "Delete session"}
          className={`absolute right-2 top-2.5 rounded-lg text-xs transition ${
            confirming
              ? "bg-rec px-2 py-1 font-medium text-white"
              : "p-1.5 text-ink-faint opacity-0 hover:bg-rec-soft hover:text-rec focus:opacity-100 group-hover:opacity-100"
          }`}
        >
          {confirming ? "Delete?" : <Trash2 className="h-3.5 w-3.5" />}
        </button>
      )}
    </li>
  );
}

function groupByDay(sessions: SessionSummary[]): [string, SessionSummary[]][] {
  const groups = new Map<string, SessionSummary[]>();
  for (const s of sessions) {
    const label = dayGroup(s.session.started_at);
    groups.set(label, [...(groups.get(label) ?? []), s]);
  }
  return [...groups.entries()];
}
