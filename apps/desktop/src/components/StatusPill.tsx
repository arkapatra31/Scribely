import type { AppState } from "../state";

export function StatusPill({ state }: { state: AppState }) {
  const { label, dot } = describe(state);
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-stone-200 px-3 py-1 text-xs text-stone-600 dark:border-stone-800 dark:text-stone-400">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {label}
    </span>
  );
}

function describe({ connection, status }: AppState): { label: string; dot: string } {
  if (connection !== "open" || status === null) {
    return connection === "connecting"
      ? { label: "Connecting…", dot: "bg-stone-400 animate-pulse" }
      : { label: "Backend offline", dot: "bg-stone-400" };
  }
  switch (status.state) {
    case "idle":
      return { label: "Ready", dot: "bg-emerald-500" };
    case "loading_model":
      return { label: `Loading speech model “${status.model}”…`, dot: "bg-amber-500 animate-pulse" };
    case "recording":
      return { label: "Recording", dot: "bg-red-500 animate-pulse" };
    case "stopping":
      return { label: "Finishing…", dot: "bg-amber-500 animate-pulse" };
  }
}
