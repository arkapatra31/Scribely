import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  Download,
  FileText,
  Globe,
  ListTree,
  LoaderCircle,
  MessagesSquare,
  Minimize2,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import type { ExportSessionCommand, NotesJobMessage, RestructureCommand } from "@scribely/schemas";

export type Tab = "transcript" | "notes";
type Style = RestructureCommand["style"];
export type ExportFormat = NonNullable<ExportSessionCommand["format"]>;

interface MenuItem<T> {
  value: T;
  label: string;
  hint: string;
  icon: typeof ListTree;
}

const FORMATS: MenuItem<ExportFormat>[] = [
  { value: "pdf", label: "PDF document", hint: "To print or share", icon: FileText },
  { value: "html", label: "Web page", hint: "Opens in any browser", icon: Globe },
];

const STYLES: MenuItem<Style>[] = [
  { value: "outline", label: "Study outline", hint: "Grouped by topic", icon: ListTree },
  { value: "qa", label: "Questions & answers", hint: "For revision", icon: MessagesSquare },
  { value: "condensed", label: "Condensed", hint: "Just the essentials", icon: Minimize2 },
];

interface Props {
  tab: Tab;
  hasNotes: boolean;
  canSummarize: boolean;
  canExport: boolean;
  job: NotesJobMessage | undefined;
  llmIssue: string | null;
  onTab: (tab: Tab) => void;
  onSummarize: () => void;
  onRestructure: (style: Style) => void;
  onExport: (format: ExportFormat) => void;
  onOpenSettings: () => void;
}

/** Underline tabs plus the session's actions: Export (PDF/HTML), Restructure, Summarize. */
export function Toolbar(props: Props) {
  const { tab, hasNotes, canSummarize, canExport, job, llmIssue } = props;
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

        <div className="ml-auto flex min-w-0 items-center gap-2 py-2">
          {running ? (
            <span className="mr-1 truncate text-xs text-ink-muted">{job.message}</span>
          ) : canSummarize && llmIssue ? (
            <button
              type="button"
              onClick={props.onOpenSettings}
              title={llmIssue}
              className="mr-1 truncate text-xs text-warn hover:underline"
            >
              {llmIssue}
            </button>
          ) : null}
          {canExport && (
            <Menu label="Export" icon={Download} items={FORMATS} onPick={props.onExport} />
          )}
          {canSummarize && hasNotes && (
            <Menu
              label="Restructure"
              icon={WandSparkles}
              items={STYLES}
              disabled={running}
              onPick={props.onRestructure}
            />
          )}
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
              {running ? "Working" : hasNotes ? "Summarize again" : "Summarize"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Menu<T extends string>(props: {
  label: string;
  icon: typeof ListTree;
  items: MenuItem<T>[];
  disabled?: boolean;
  onPick: (value: T) => void;
}) {
  const { label, icon: ButtonIcon, items, disabled = false, onPick } = props;
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !root.current?.contains(e.target as Node))
        setOpen(false);
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={root} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-sm text-ink-muted transition hover:border-line-strong hover:text-ink disabled:opacity-50"
      >
        <ButtonIcon className="h-4 w-4" aria-hidden />
        {label}
        <ChevronDown className="h-3.5 w-3.5" aria-hidden />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-20 mt-2 w-56 rounded-2xl border border-line bg-paper-raised p-1.5 shadow-float"
        >
          {items.map((item) => (
            <button
              key={item.value}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onPick(item.value);
              }}
              className="flex w-full items-start gap-3 rounded-xl px-3 py-2 text-left transition hover:bg-paper-sunken"
            >
              <item.icon className="mt-0.5 h-4 w-4 text-accent" aria-hidden />
              <span>
                <span className="block text-sm font-medium">{item.label}</span>
                <span className="block text-xs text-ink-muted">{item.hint}</span>
              </span>
            </button>
          ))}
        </div>
      )}
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
