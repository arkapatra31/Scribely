import { motion, useReducedMotion } from "framer-motion";
import { Pencil, Sparkles } from "lucide-react";
import type { SessionNotes } from "@scribely/schemas";
import { formatClock, formatDate } from "../format";

const PROVIDERS: Record<string, string> = {
  azure_openai: "Azure OpenAI",
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Gemini",
  ollama: "Ollama",
};

const STYLE_LABELS: Record<string, string> = {
  outline: "Study outline",
  qa: "Questions & answers",
  condensed: "Condensed",
};

interface Props {
  notes: SessionNotes;
  busy: boolean;
  onJump: (seconds: number) => void;
  onEdit: () => void;
}

export function NotesView({ notes, busy, onJump, onEdit }: Props) {
  const reduceMotion = useReducedMotion();
  const { doc } = notes;
  return (
    <motion.article
      initial={reduceMotion ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="mx-auto max-w-3xl px-10 py-10"
    >
      <div className="mb-3 flex items-center gap-2">
        {STYLE_LABELS[notes.style ?? "standard"] && (
          <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent-ink">
            {STYLE_LABELS[notes.style ?? "standard"]}
          </span>
        )}
        {notes.edited && <span className="text-xs text-ink-faint">Edited</span>}
        <button
          type="button"
          onClick={onEdit}
          disabled={busy}
          className="ml-auto inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm text-ink-muted transition hover:bg-paper-sunken hover:text-ink disabled:opacity-40"
        >
          <Pencil className="h-3.5 w-3.5" aria-hidden /> Edit
        </button>
      </div>
      <h2 className="font-serif text-[1.75rem] font-semibold leading-snug tracking-tight">
        {doc.title}
      </h2>

      <div className="mt-5 rounded-2xl border border-accent/15 bg-accent-soft/60 px-6 py-5">
        <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-accent-ink">
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
          Summary
        </p>
        <p className="font-serif text-[1.075rem] leading-relaxed text-ink">{doc.summary}</p>
      </div>

      <div className="mt-10 space-y-9">
        {doc.sections.map((section, i) => (
          <section key={i} className="grid grid-cols-[2.5rem_1fr] gap-x-3">
            <span className="pt-1 font-mono text-xs tabular-nums text-ink-faint">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h3 className="font-serif text-xl font-semibold tracking-tight">{section.heading}</h3>
                <button
                  type="button"
                  onClick={() => onJump(section.start)}
                  title="Show in transcript"
                  className="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] tabular-nums text-ink-muted transition hover:border-accent hover:text-accent"
                >
                  {formatClock(section.start)} – {formatClock(section.end)}
                </button>
              </div>
              <ul className="mt-3 space-y-2">
                {section.points.map((point, j) => (
                  <li key={j} className="flex gap-3 text-[15px] leading-7">
                    <span className="mt-[11px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent/60" />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        ))}
      </div>

      <p className="mt-14 border-t border-line pt-4 text-xs text-ink-faint">
        Written by {PROVIDERS[notes.provider] ?? notes.provider} · {notes.model} ·{" "}
        {formatDate(notes.created_at)}
        {notes.edited && " · edited by you"}
      </p>
    </motion.article>
  );
}
