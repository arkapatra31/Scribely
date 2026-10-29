import { useEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { TranscriptPartialMessage, TranscriptSegment } from "@scribely/schemas";
import { formatClock } from "../format";
import { Listening } from "./Listening";

interface Props {
  segments: TranscriptSegment[];
  partial: TranscriptPartialMessage | null;
  listening: boolean;
  emptyMessage: string;
  /** Scroll to (and highlight) the segment at this time, in seconds. */
  focusTime?: number | null;
  scroller: React.RefObject<HTMLDivElement | null>;
}

export function Transcript(props: Props) {
  const { segments, partial, listening, emptyMessage, focusTime = null, scroller } = props;
  const reduceMotion = useReducedMotion();
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
  }, [segments, partial, focusIndex, scroller]);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onScroll = () => {
      stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 64;
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, [scroller]);

  if (segments.length === 0 && partial === null) {
    return (
      <div className="flex flex-col items-center gap-3 px-10 py-24 text-center text-sm text-ink-muted">
        {listening && <Listening className="text-rec" />}
        {emptyMessage}
      </div>
    );
  }

  return (
    <ol className="mx-auto max-w-3xl space-y-1 px-10 py-8">
      <AnimatePresence initial={false}>
        {segments.map((s) => (
          <motion.li
            key={s.index}
            initial={reduceMotion ? false : { opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            data-index={s.index}
            className={`group -mx-3 grid grid-cols-[3.5rem_1fr] gap-4 rounded-lg px-3 py-1.5 transition-colors ${
              s.index === focusIndex ? "bg-accent-soft" : "hover:bg-paper-sunken/70"
            }`}
          >
            <Timestamp seconds={s.start} />
            <p className="text-[15px] leading-7">{s.text}</p>
          </motion.li>
        ))}
      </AnimatePresence>
      {partial && (
        <li className="-mx-3 grid grid-cols-[3.5rem_1fr] gap-4 px-3 py-1.5" aria-live="polite">
          <Timestamp seconds={partial.start} />
          <p className="text-[15px] italic leading-7 text-ink-faint">
            {partial.text}
            <Listening className="ml-2 align-middle text-rec/70" />
          </p>
        </li>
      )}
    </ol>
  );
}

function Timestamp({ seconds }: { seconds: number }) {
  return (
    <span className="pt-[5px] text-right font-mono text-[11px] tabular-nums text-ink-faint">
      {formatClock(seconds)}
    </span>
  );
}
