import { useEffect, useRef, useState } from "react";
import { Languages, LoaderCircle, Mic, Pause, Play, Square } from "lucide-react";
import type { LanguageOption, SpeechModelMessage } from "@scribely/schemas";
import { formatClock } from "../format";
import { SHORTCUT_LABEL } from "../shell";

const SILENCE_LEVEL = 0.08;
const SILENCE_HINT_MS = 6000;

interface Props {
  canStart: boolean;
  recording: boolean;
  paused: boolean;
  stopping: boolean;
  loadingModel: boolean;
  /** Seconds recorded (pauses excluded) as of the last status message. */
  elapsed: number;
  level: number;
  speechModel: SpeechModelMessage | null;
  language: string | null;
  languages: LanguageOption[];
  englishOnly: boolean;
  onLanguage: (code: string | null) => void;
  onStart: () => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
}

/** Floating record control at the bottom of the main pane. */
export function RecordDock(props: Props) {
  const { canStart, recording, paused, stopping, loadingModel, speechModel } = props;
  const active = recording || paused;
  const elapsed = useTicking(props.elapsed, recording && !stopping);
  const silent = useSilence(props.level, recording && !paused && !stopping);
  const downloading = speechModel?.state === "downloading";
  const preparing = loadingModel || downloading || speechModel?.state === "loading";

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
      <div className="pointer-events-auto flex items-center gap-3 rounded-full border border-line bg-paper-raised/90 py-2 pl-2 pr-3 shadow-float backdrop-blur">
        {active ? (
          <button
            key="stop"
            type="button"
            onClick={props.onStop}
            disabled={stopping}
            aria-label="Stop recording"
            title={`Stop (${SHORTCUT_LABEL})`}
            className={`flex h-11 w-11 items-center justify-center rounded-full bg-rec text-white transition hover:brightness-110 disabled:opacity-60 ${
              paused || stopping ? "" : "animate-ring"
            }`}
          >
            <Square className="h-4 w-4 fill-current" aria-hidden />
          </button>
        ) : (
          <button
            key="start"
            type="button"
            onClick={props.onStart}
            disabled={!canStart || loadingModel}
            aria-label="Record"
            title={`Record (${SHORTCUT_LABEL})`}
            className="flex h-11 w-11 items-center justify-center rounded-full bg-rec text-white shadow-soft transition hover:scale-105 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
          >
            {loadingModel ? (
              <LoaderCircle className="h-5 w-5 animate-spin" aria-hidden />
            ) : (
              <Mic className="h-5 w-5" aria-hidden />
            )}
          </button>
        )}

        {active ? (
          <span className="flex items-center gap-3">
            <button
              type="button"
              onClick={paused ? props.onResume : props.onPause}
              disabled={stopping}
              aria-label={paused ? "Resume recording" : "Pause recording"}
              title={paused ? "Resume" : "Pause"}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-line text-ink-muted transition hover:border-line-strong hover:text-ink disabled:opacity-40"
            >
              {paused ? (
                <Play className="h-4 w-4 fill-current" aria-hidden />
              ) : (
                <Pause className="h-4 w-4 fill-current" aria-hidden />
              )}
            </button>
            <span className="w-14 font-mono text-sm tabular-nums">{formatClock(elapsed)}</span>
            <span className="flex min-w-[9.5rem] items-center gap-2 text-sm text-ink-muted">
              <LevelMeter level={paused || stopping ? 0 : props.level} />
              {stopping
                ? "Finishing…"
                : paused
                  ? "Paused"
                  : silent
                    ? "No sound yet — is it playing?"
                    : "Listening"}
            </span>
          </span>
        ) : downloading ? (
          <span className="flex min-w-48 flex-col gap-1 pr-2">
            <span className="text-sm text-ink-muted">{speechModel.message}</span>
            <Progress value={speechModel.progress ?? null} />
          </span>
        ) : (
          <span className="pr-1 text-sm text-ink-muted">
            {preparing ? "Loading the speech model…" : canStart ? "Record" : "Offline"}
          </span>
        )}

        {!stopping && (
          <LanguagePicker
            value={props.language}
            languages={props.languages}
            englishOnly={props.englishOnly}
            onChange={props.onLanguage}
          />
        )}
      </div>
    </div>
  );
}

function LanguagePicker(props: {
  value: string | null;
  languages: LanguageOption[];
  englishOnly: boolean;
  onChange: (code: string | null) => void;
}) {
  if (props.languages.length === 0) return null;
  const options = props.englishOnly
    ? props.languages.filter((l) => l.code === "en")
    : props.languages;
  return (
    <label
      className="relative flex items-center gap-1.5 rounded-full border border-line py-1.5 pl-2.5 pr-3 text-xs text-ink-muted transition focus-within:border-accent hover:border-line-strong hover:text-ink"
      title="Spoken language (setting it makes the transcript more accurate)"
    >
      <Languages className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="sr-only">Spoken language</span>
      <select
        value={props.value ?? ""}
        onChange={(e) => props.onChange(e.target.value || null)}
        className="max-w-28 cursor-pointer appearance-none bg-transparent pr-0.5 outline-none"
      >
        {!props.englishOnly && <option value="">Auto-detect</option>}
        {options.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Five bars that follow the captured audio's loudness. */
function LevelMeter({ level }: { level: number }) {
  return (
    <span className="inline-flex h-4 items-end gap-[3px] text-rec" aria-hidden>
      {[0.1, 0.3, 0.5, 0.7, 0.85].map((threshold, i) => {
        const fill = Math.min(1, Math.max(0, (level - threshold + 0.2) / 0.2));
        return (
          <span
            key={i}
            className="w-[3px] rounded-full bg-current transition-[height,opacity] duration-100"
            style={{ height: `${30 + 70 * fill}%`, opacity: 0.3 + 0.7 * fill }}
          />
        );
      })}
    </span>
  );
}

export function Progress({ value }: { value: number | null }) {
  return (
    <span className="block h-1.5 w-full overflow-hidden rounded-full bg-paper-sunken">
      {value === null ? (
        <span className="block h-full w-1/3 animate-pulse rounded-full bg-accent" />
      ) : (
        <span
          className="block h-full rounded-full bg-accent transition-[width] duration-300"
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      )}
    </span>
  );
}

/** ``base`` seconds as of when it changed, counting up once a second while ``running``. */
function useTicking(base: number, running: boolean): number {
  const [anchor, setAnchor] = useState(() => ({ base, at: Date.now() }));
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => setAnchor({ base, at: Date.now() }), [base]);
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);
  return running ? anchor.base + Math.max(0, now - anchor.at) / 1000 : anchor.base;
}

/** True after a few seconds of near-silence while listening. */
function useSilence(level: number, listening: boolean): boolean {
  const lastSound = useRef(Date.now());
  const [silent, setSilent] = useState(false);
  useEffect(() => {
    if (!listening || level > SILENCE_LEVEL) {
      lastSound.current = Date.now();
      setSilent(false);
    }
  }, [level, listening]);
  useEffect(() => {
    if (!listening) return;
    const id = setInterval(
      () => setSilent(Date.now() - lastSound.current > SILENCE_HINT_MS),
      1000,
    );
    return () => clearInterval(id);
  }, [listening]);
  return silent;
}
