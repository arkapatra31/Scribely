import { useEffect, useId, useState } from "react";
import { CircleCheck, Download, LoaderCircle, RotateCw, TriangleAlert } from "lucide-react";
import type { SpeechModelMessage, SpeechSettings, SpeechSettingsMessage } from "@scribely/schemas";
import { Progress } from "./RecordDock";

interface Props {
  message: SpeechSettingsMessage | null;
  speechModel: SpeechModelMessage | null;
  /** Model changes wait until the recording stops. */
  recording: boolean;
  onSave: (settings: SpeechSettings) => void;
}

/** Spoken language + speech model, with download progress. Changes apply right away. */
export function SpeechSettingsPanel({ message, speechModel, recording, onSave }: Props) {
  const ids = useId();
  const current = message?.settings;
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => setPicked(null), [current?.model]);

  if (!message || !current) {
    return (
      <p className="flex items-center gap-2 text-sm text-ink-muted">
        <LoaderCircle className="h-4 w-4 animate-spin" /> Loading…
      </p>
    );
  }

  const selected = message.models.find((m) => m.name === (picked ?? current.model));
  const currentInfo = message.models.find((m) => m.name === current.model);
  const englishOnly = currentInfo?.english_only ?? false;
  const status = speechModel?.model === current.model ? speechModel : null;
  const busy = status?.state === "downloading" || status?.state === "loading";

  const useModel = () => {
    if (!selected) return;
    onSave({ model: selected.name, language: selected.english_only ? "en" : current.language });
  };

  return (
    <div className="space-y-6">
      <div>
        <label htmlFor={`${ids}-language`} className="mb-1.5 block text-sm font-medium">
          Spoken language
        </label>
        <select
          id={`${ids}-language`}
          value={current.language ?? ""}
          onChange={(e) => onSave({ ...current, language: e.target.value || null })}
          className="w-full rounded-xl border border-line-strong bg-paper px-3 py-2 text-sm outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/10"
        >
          {!englishOnly && <option value="">Auto-detect</option>}
          {message.languages
            .filter((l) => !englishOnly || l.code === "en")
            .map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
        </select>
        <p className="mt-1.5 text-xs text-ink-muted">
          Pick the language of your lecture for a faster, more accurate transcript.
          {englishOnly && " The current model understands English only."}
        </p>
      </div>

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Speech model</legend>
        <p className="mb-3 text-xs text-ink-muted">
          Runs on this computer. Downloaded once; your audio never leaves the machine.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {message.models.map((m) => {
            const active = m.name === (picked ?? current.model);
            const inUse = m.name === current.model;
            return (
              <button
                key={m.name}
                type="button"
                aria-pressed={active}
                disabled={recording && !inUse}
                onClick={() => setPicked(inUse ? null : m.name)}
                className={`rounded-2xl border px-3.5 py-2.5 text-left transition disabled:opacity-40 ${
                  active
                    ? "border-accent bg-accent-soft shadow-soft"
                    : "border-line hover:border-line-strong hover:bg-paper-sunken"
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="text-[13px] font-medium">{m.label}</span>
                  {m.size_mb > 0 && (
                    <span className="text-[11px] text-ink-faint">{formatSize(m.size_mb)}</span>
                  )}
                  {inUse ? (
                    <span className="ml-auto rounded-full bg-accent px-1.5 text-[10px] font-medium text-white dark:text-paper">
                      In use
                    </span>
                  ) : m.downloaded ? (
                    <CircleCheck className="ml-auto h-3.5 w-3.5 text-ok" aria-label="Downloaded" />
                  ) : null}
                </span>
                <span className="mt-0.5 block text-[11px] leading-snug text-ink-muted">
                  {m.description}
                </span>
              </button>
            );
          })}
        </div>
      </fieldset>

      {picked && selected && selected.name !== current.model ? (
        <div className="flex items-center justify-between gap-3 rounded-xl bg-paper-sunken px-3.5 py-2.5 text-sm">
          <span className="text-ink-muted">
            {selected.downloaded
              ? `Switch to ${selected.label}?`
              : `${selected.label} is a ${formatSize(selected.size_mb)} download.`}
          </span>
          <button
            type="button"
            onClick={useModel}
            disabled={busy || recording}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white shadow-soft transition hover:bg-accent-strong disabled:opacity-40 dark:text-paper"
          >
            {!selected.downloaded && <Download className="h-4 w-4" aria-hidden />}
            {selected.downloaded ? "Use this model" : "Download and use"}
          </button>
        </div>
      ) : status ? (
        <ModelStatus status={status} onRetry={() => onSave(current)} />
      ) : currentInfo && !currentInfo.downloaded ? (
        <div className="flex items-center justify-between gap-3 rounded-xl bg-paper-sunken px-3.5 py-2.5 text-sm">
          <span className="text-ink-muted">
            {currentInfo.label} isn't downloaded yet ({formatSize(currentInfo.size_mb)}).
          </span>
          <button
            type="button"
            onClick={() => onSave(current)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white shadow-soft transition hover:bg-accent-strong dark:text-paper"
          >
            <Download className="h-4 w-4" aria-hidden /> Download
          </button>
        </div>
      ) : null}
      {recording && (
        <p className="text-xs text-ink-muted">Stop the recording to change the speech model.</p>
      )}
    </div>
  );
}

function ModelStatus({ status, onRetry }: { status: SpeechModelMessage; onRetry: () => void }) {
  const box = "flex items-start gap-2 rounded-xl px-3.5 py-2.5 text-sm";
  switch (status.state) {
    case "downloading":
      return (
        <div className="space-y-2 rounded-xl bg-paper-sunken px-3.5 py-3 text-sm">
          <p className="flex items-center justify-between text-ink-muted">
            <span>{status.message}</span>
            {status.progress != null && (
              <span className="font-mono text-xs tabular-nums">
                {Math.round(status.progress * 100)}%
              </span>
            )}
          </p>
          <Progress value={status.progress ?? null} />
        </div>
      );
    case "loading":
      return (
        <p className={`${box} bg-paper-sunken text-ink-muted`}>
          <LoaderCircle className="mt-0.5 h-4 w-4 shrink-0 animate-spin" /> {status.message}
        </p>
      );
    case "ready":
      return (
        <p className={`${box} bg-ok/10 text-ok`}>
          <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" /> {status.message}
        </p>
      );
    case "failed":
      return (
        <div className={`${box} bg-rec-soft text-rec`}>
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">{status.message}</span>
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium hover:underline"
          >
            <RotateCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      );
  }
}

export function formatSize(mb: number): string {
  return mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${mb} MB`;
}
