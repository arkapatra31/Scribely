import type { NotesJobMessage } from "@scribely/schemas";

interface Props {
  hasNotes: boolean;
  job: NotesJobMessage | undefined;
  llmIssue: string | null;
  tab: "notes" | "transcript";
  onTab: (tab: "notes" | "transcript") => void;
  onSummarize: () => void;
  onOpenSettings: () => void;
}

/** Notes/Transcript tabs plus the on-demand Summarize action for a stopped session. */
export function SummarizeBar(props: Props) {
  const { hasNotes, job, llmIssue, tab, onTab, onSummarize, onOpenSettings } = props;
  const running = job?.state === "running";
  return (
    <div className="border-b border-stone-200 px-6 py-2 dark:border-stone-800">
      <div className="mx-auto flex max-w-2xl items-center gap-3">
        {hasNotes && (
          <div className="flex rounded-lg bg-stone-200/60 p-0.5 text-sm dark:bg-stone-800/60">
            {(["notes", "transcript"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onTab(t)}
                className={`rounded-md px-3 py-1 capitalize transition ${
                  tab === t
                    ? "bg-white shadow-sm dark:bg-stone-700"
                    : "text-stone-500 hover:text-stone-800 dark:hover:text-stone-200"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        )}
        <div className="min-w-0 flex-1 truncate text-xs text-stone-500">
          {running ? (
            <span className="animate-pulse">{job.message}</span>
          ) : llmIssue ? (
            <button
              type="button"
              onClick={onOpenSettings}
              title={llmIssue}
              className="max-w-full truncate text-amber-700 hover:underline dark:text-amber-400"
            >
              Notes unavailable: {llmIssue}
            </button>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onSummarize}
          disabled={running}
          className="shrink-0 rounded-full bg-stone-900 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-stone-700 disabled:cursor-wait disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-300"
        >
          {running ? "Summarizing…" : hasNotes ? "Summarize again" : "✦ Summarize"}
        </button>
      </div>
    </div>
  );
}
