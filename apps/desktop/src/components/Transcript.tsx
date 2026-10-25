import { useEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { TranscriptPartialMessage, TranscriptSegment } from "@scribely/schemas";
import { formatClock } from "../format";

interface Props {
  segments: TranscriptSegment[];
  partial: TranscriptPartialMessage | null;
  emptyMessage: string;
}

export function Transcript({ segments, partial, emptyMessage }: Props) {
  const reduceMotion = useReducedMotion();
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    const el = scroller.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [segments, partial]);

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
              className="flex gap-4"
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
