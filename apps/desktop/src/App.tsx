import { ErrorBanner } from "./components/ErrorBanner";
import { RecordControls } from "./components/RecordControls";
import { SessionHeader } from "./components/SessionHeader";
import { Sidebar } from "./components/Sidebar";
import { StatusPill } from "./components/StatusPill";
import { Transcript } from "./components/Transcript";
import { useScribely } from "./useScribely";

const OFFLINE_MESSAGE =
  "Can't reach the Scribely backend. Start it by running “uv run scribely-backend” in the backend folder.";

export default function App() {
  const { state, start, stop, openSession, renameSession, deleteSession, showLive, dismissError } =
    useScribely();
  const backendState = state.status?.state;
  const connected = state.connection === "open" && state.status !== null;
  const recording = backendState === "recording" || backendState === "stopping";
  const liveSession = state.status?.session ?? null;

  const viewingSaved = state.view.kind === "saved";
  const shown = state.view.kind === "saved" ? state.view.session : liveSession;
  const segments = state.view.kind === "saved" ? state.view.segments : state.segments;
  const partial = viewingSaved ? null : state.partial;
  const duration = segments.length ? segments[segments.length - 1].end : 0;

  const emptyMessage = viewingSaved
    ? "Nothing was transcribed in this session."
    : recording
      ? "Listening… the transcript appears here as people speak."
      : "Press Record, then play your lecture.";

  const openFromList = (id: string) => (id === liveSession?.id ? showLive() : openSession(id));

  return (
    <div className="flex h-screen flex-col bg-stone-50 text-stone-800 dark:bg-stone-950 dark:text-stone-100">
      <header className="flex items-center justify-between border-b border-stone-200 px-6 py-3 dark:border-stone-800">
        <h1 className="text-lg font-semibold tracking-tight">Scribely</h1>
        <StatusPill state={state} />
      </header>

      <ErrorBanner message={state.connection === "closed" ? OFFLINE_MESSAGE : null} />
      <ErrorBanner message={state.error?.message ?? null} onDismiss={dismissError} />

      <div className="flex min-h-0 flex-1">
        <Sidebar
          sessions={state.sessions}
          selectedId={shown?.id ?? null}
          recordingId={recording ? (liveSession?.id ?? null) : null}
          onOpen={openFromList}
          onDelete={deleteSession}
        />

        <main className="flex min-w-0 flex-1 flex-col">
          {shown && (
            <SessionHeader
              key={`header-${shown.id}`}
              session={shown}
              duration={duration}
              live={!viewingSaved}
              onRename={(title) => renameSession(shown.id, title)}
              onBackToLive={viewingSaved && recording ? showLive : undefined}
            />
          )}
          <Transcript
            key={`transcript-${shown?.id ?? "none"}`}
            segments={segments}
            partial={partial}
            emptyMessage={emptyMessage}
          />
          <footer className="border-t border-stone-200 px-6 py-4 dark:border-stone-800">
            <RecordControls
              canStart={connected && backendState === "idle"}
              recording={recording}
              busy={backendState === "loading_model"}
              session={liveSession}
              onStart={start}
              onStop={stop}
            />
          </footer>
        </main>
      </div>
    </div>
  );
}
