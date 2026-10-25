import { motion, useReducedMotion } from "framer-motion";
import type { SessionNotes } from "@scribely/schemas";
import { formatClock, formatDate } from "../format";

const PROVIDERS: Record<string, string> = {
  azure_openai: "Azure OpenAI",
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Gemini",
  ollama: "Ollama",
};

interface Props {
  notes: SessionNotes;
  onJump: (seconds: number) => void;
}

export function NotesView({ notes, onJump }: Props) {
  const reduceMotion = useReducedMotion();
  const { doc } = notes;
  return (
    <motion.article
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex-1 overflow-y-auto px-6 py-6"
    >
      <div className="mx-auto max-w-2xl">
        <h2 className="text-2xl font-semibold tracking-tight">{doc.title}</h2>
        <p className="mt-3 leading-relaxed text-stone-600 dark:text-stone-300">{doc.summary}</p>
        <div className="mt-8 space-y-7">
          {doc.sections.map((section, i) => (
            <section key={i}>
              <div className="flex items-baseline gap-3">
                <h3 className="font-semibold">{section.heading}</h3>
                <button
                  type="button"
                  onClick={() => onJump(section.start)}
                  title="Show in transcript"
                  className="shrink-0 rounded font-mono text-xs tabular-nums text-stone-400 hover:text-stone-700 hover:underline dark:hover:text-stone-200"
                >
                  {formatClock(section.start)}–{formatClock(section.end)}
                </button>
              </div>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 leading-relaxed marker:text-stone-400">
                {section.points.map((point, j) => (
                  <li key={j}>{point}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <p className="mt-10 text-xs text-stone-400">
          Written by {PROVIDERS[notes.provider] ?? notes.provider} · {notes.model} ·{" "}
          {formatDate(notes.created_at)}
        </p>
      </div>
    </motion.article>
  );
}
