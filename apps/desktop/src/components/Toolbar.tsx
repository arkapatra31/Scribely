import { LoaderCircle, Sparkles } from "lucide-react";
import type { NotesJobMessage } from "@scribely/schemas";

export type Tab = "transcript" | "notes";

interface Props {
  tab: Tab;
  hasNotes: boolean;
  canSummarize: boolean;
  job: NotesJobMessage | undefined;
  llmIssue: string | null;
  onTab: (tab: Tab) => void;
  onSummarize: () => void;
  onOpenSettings: () => void;
}

/** Underline tabs plus the on-demand Summarize action. */
export function Toolbar(props: Props) {
  const { tab, hasNotes, canSummarize, job, llmIssue } = props;
  const running = job?.state === "running";

  return (
    <div className="sticky top-0 z-10 border-b border-line bg-paper/85 px-10 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center gap-6">
        <div className="flex gap-6" role="tablist">
          <TabButton active={tab === "transcript"} onClick={() => props.onTab("transcript")}>
            Transcript
          </TabButton>
          <TabButton
            active={tab === "notes"}
            disabled={!hasNotes}
            onClick={() => props.onTab("notes")}
          >
            Notes
          </TabButton>
        </div>

        <div className="ml-auto flex min-w-0 items-center gap-3 py-2">
          {running ? (
            <span className="truncate text-xs text-ink-muted">{job.message}</span>
          ) : canSummarize && llmIssue ? (
            <button
              type="button"
              onClick={props.onOpenSettings}
              title={llmIssue}
              className="truncate text-xs text-warn hover:underline"
            >
              {llmIssue}
            </button>
          ) : null}
          {canSummarize && (
            <button
              type="button"
              onClick={props.onSummarize}
              disabled={running}
              className="inline-flex shrink-0 items-center gap-2 rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white shadow-soft transition hover:bg-accent-strong disabled:cursor-wait disabled:opacity-70 dark:text-paper"
            >
              {running ? (
                <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Sparkles className="h-4 w-4" aria-hidden />
              )}
              {running ? "Summarizing" : hasNotes ? "Summarize again" : "Summarize"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function TabButton(props: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={props.active}
      disabled={props.disabled}
      onClick={props.onClick}
      className={`-mb-px border-b-2 py-3 text-sm font-medium transition ${
        props.active
          ? "border-accent text-ink"
          : "border-transparent text-ink-muted hover:text-ink disabled:cursor-default disabled:text-ink-faint disabled:hover:text-ink-faint"
      }`}
    >
      {props.children}
    </button>
  );
}
