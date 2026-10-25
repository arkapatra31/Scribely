import { useEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { TranscriptPartialMessage, TranscriptSegment } from "@scribely/schemas";
import { formatClock } from "../format";

interface Props {
  segments: TranscriptSegment[];
  partial: TranscriptPartialMessage | null;
  emptyMessage: string;
  /** Scroll to (and highlight) the segment at this time, in seconds. */
  focusTime?: number | null;
}

export function Transcript({ segments, partial, emptyMessage, focusTime = null }: Props) {
  const reduceMotion = useReducedMotion();
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  const focusIndex =
    focusTime === null
      ? null
      : (segments.find((s) => s.end >= focusTime)?.index ?? segments[segments.length - 1]?.index ?? null);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (focusIndex !== null) {
      stickToBottom.current = false;
      el.querySelector(`[data-index="${focusIndex}"]`)?.scrollIntoView({ block: "center" });
    } else if (stickToBottom.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [segments, partial, focusIndex]);

  const onScroll = () => {
    const el = scroller.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };

  if (segments.length === 0 && partial === null) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-stone-500">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div ref={scroller} onScroll={onScroll} className="flex-1 overflow-y-auto px-6 py-6">
      <ol className="mx-auto max-w-2xl space-y-4">
        <AnimatePresence initial={false}>
          {segments.map((s) => (
            <motion.li
              key={s.index}
              initial={reduceMotion ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              data-index={s.index}
              className={`-mx-2 flex gap-4 rounded px-2 ${
                s.index === focusIndex ? "bg-amber-100/70 dark:bg-amber-900/30" : ""
              }`}
            >
              <Timestamp seconds={s.start} />
              <p className="leading-relaxed">{s.text}</p>
            </motion.li>
          ))}
        </AnimatePresence>
        {partial && (
          <li className="flex gap-4 text-stone-400 dark:text-stone-500" aria-live="polite">
            <Timestamp seconds={partial.start} />
            <p className="italic leading-relaxed">
              {partial.text}
              <span className="ml-0.5 inline-block w-1.5 animate-pulse">▍</span>
            </p>
          </li>
        )}
      </ol>
    </div>
  );
}

function Timestamp({ seconds }: { seconds: number }) {
  return (
    <span className="mt-0.5 shrink-0 font-mono text-xs tabular-nums text-stone-400">
      {formatClock(seconds)}
    </span>
  );
}
