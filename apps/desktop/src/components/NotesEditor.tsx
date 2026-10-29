import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { NoteDoc, NoteSection } from "@scribely/schemas";
import { formatClock } from "../format";

interface Props {
  doc: NoteDoc;
  onSave: (doc: NoteDoc) => void;
  onCancel: () => void;
}

interface Draft {
  heading: string;
  points: string; // one point per line
  start: number;
  end: number;
}

/** Hand-edit notes: title, summary, section headings and points (one per line). */
export function NotesEditor({ doc, onSave, onCancel }: Props) {
  const [title, setTitle] = useState(doc.title);
  const [summary, setSummary] = useState(doc.summary);
  const [sections, setSections] = useState<Draft[]>(() =>
    doc.sections.map((s) => ({ ...s, points: s.points.join("\n") })),
  );

  const update = (i: number, patch: Partial<Draft>) =>
    setSections((all) => all.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  const save = () => {
    const cleaned: NoteSection[] = sections
      .map((s) => ({
        heading: s.heading.trim(),
        points: s.points.split("\n").map((p) => p.trim()).filter(Boolean),
        start: s.start,
        end: s.end,
      }))
      .filter((s) => s.heading || s.points.length);
    onSave({ title: title.trim() || doc.title, summary: summary.trim(), sections: cleaned });
  };

  return (
    <div className="mx-auto max-w-3xl px-10 py-10">
      <div className="sticky top-14 z-10 -mx-3 mb-6 flex items-center gap-2 rounded-2xl border border-accent/20 bg-accent-soft/80 px-4 py-2.5 backdrop-blur">
        <p className="flex-1 text-sm text-accent-ink">Editing notes. One point per line.</p>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-full px-3 py-1.5 text-sm text-ink-muted transition hover:bg-paper-raised hover:text-ink"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          className="rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white shadow-soft transition hover:bg-accent-strong dark:text-paper"
        >
          Save changes
        </button>
      </div>

      <input
        aria-label="Title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className={`${field} font-serif text-[1.75rem] font-semibold tracking-tight`}
      />
      <textarea
        aria-label="Summary"
        value={summary}
        rows={4}
        onChange={(e) => setSummary(e.target.value)}
        className={`${field} mt-4 resize-y font-serif text-[1.075rem] leading-relaxed`}
      />

      <div className="mt-8 space-y-6">
        {sections.map((s, i) => (
          <div key={i} className="rounded-2xl border border-line bg-paper-raised p-4 shadow-soft">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-ink-faint">
                {formatClock(s.start)} – {formatClock(s.end)}
              </span>
              <button
                type="button"
                onClick={() => setSections((all) => all.filter((_, j) => j !== i))}
                aria-label="Remove section"
                className="ml-auto rounded-lg p-1.5 text-ink-faint transition hover:bg-rec-soft hover:text-rec"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <input
              aria-label={`Section ${i + 1} heading`}
              value={s.heading}
              onChange={(e) => update(i, { heading: e.target.value })}
              className={`${field} mt-2 font-serif text-lg font-semibold`}
            />
            <textarea
              aria-label={`Section ${i + 1} points`}
              value={s.points}
              rows={Math.max(3, s.points.split("\n").length + 1)}
              onChange={(e) => update(i, { points: e.target.value })}
              className={`${field} mt-2 resize-y text-[15px] leading-7`}
            />
          </div>
        ))}
        <button
          type="button"
          onClick={() => {
            const last = sections[sections.length - 1];
            setSections((all) => [
              ...all,
              { heading: "", points: "", start: last?.end ?? 0, end: last?.end ?? 0 },
            ]);
          }}
          className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-line-strong px-4 py-2 text-sm text-ink-muted transition hover:border-accent hover:text-accent"
        >
          <Plus className="h-4 w-4" /> Add section
        </button>
      </div>
    </div>
  );
}

const field =
  "w-full rounded-xl border border-line bg-paper px-3 py-2 outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/10";
