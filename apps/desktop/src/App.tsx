import { ErrorBanner } from "./components/ErrorBanner";
import { RecordControls } from "./components/RecordControls";
import { StatusPill } from "./components/StatusPill";
import { Transcript } from "./components/Transcript";
import { useScribely } from "./useScribely";

const OFFLINE_MESSAGE =
  "Can't reach the Scribely backend. Start it by running “uv run scribely-backend” in the backend folder.";

export default function App() {
  const { state, start, stop, dismissError } = useScribely();
  const backendState = state.status?.state;
  const connected = state.connection === "open" && state.status !== null;
  const recording = backendState === "recording" || backendState === "stopping";

  const emptyMessage = recording
    ? "Listening… the transcript appears here as people speak."
    : "Press Record, then play your lecture.";

  return (
    <div className="flex h-screen flex-col bg-stone-50 text-stone-800 dark:bg-stone-950 dark:text-stone-100">
      <header className="flex items-center justify-between border-b border-stone-200 px-6 py-3 dark:border-stone-800">
        <h1 className="text-lg font-semibold tracking-tight">Scribely</h1>
        <StatusPill state={state} />
      </header>

      <ErrorBanner message={state.connection === "closed" ? OFFLINE_MESSAGE : null} />
      <ErrorBanner message={state.error?.message ?? null} onDismiss={dismissError} />

      <main className="flex min-h-0 flex-1 flex-col">
        <Transcript segments={state.segments} partial={state.partial} emptyMessage={emptyMessage} />
      </main>

      <footer className="border-t border-stone-200 px-6 py-4 dark:border-stone-800">
        <RecordControls
          canStart={connected && backendState === "idle"}
          recording={recording}
          busy={backendState === "loading_model"}
          session={state.status?.session ?? null}
          onStart={start}
          onStop={stop}
        />
      </footer>
    </div>
  );
}
