import { motion, useReducedMotion } from "framer-motion";
import { AudioLines, Mic, Play, Sparkles } from "lucide-react";

const STEPS = [
  { icon: Mic, title: "Press Record", text: "Scribely listens to your computer's audio." },
  { icon: Play, title: "Play your lecture", text: "Watch as usual. The transcript writes itself." },
  { icon: Sparkles, title: "Summarize", text: "Turn it into clean study notes when you're done." },
];

export function EmptyState() {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="mx-auto flex max-w-xl flex-col items-center px-10 pb-32 pt-[14vh] text-center"
    >
      <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <AudioLines className="h-8 w-8" aria-hidden />
      </span>
      <h1 className="mt-6 font-serif text-4xl font-semibold tracking-tight">Ready when you are</h1>
      <p className="mt-3 text-ink-muted">
        Stay focused on the video. Scribely takes the notes.
      </p>
      <ol className="mt-10 grid w-full grid-cols-3 gap-3 text-left">
        {STEPS.map(({ icon: Icon, title, text }, i) => (
          <li key={title} className="rounded-2xl border border-line bg-paper-raised p-4 shadow-soft">
            <span className="flex items-center gap-2 text-xs font-medium text-ink-faint">
              <span className="font-mono">{i + 1}</span>
              <Icon className="h-3.5 w-3.5" aria-hidden />
            </span>
            <p className="mt-2 text-sm font-medium">{title}</p>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">{text}</p>
          </li>
        ))}
      </ol>
    </motion.div>
  );
}
