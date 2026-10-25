import { ErrorBanner } from "./components/ErrorBanner";
import { RecordControls } from "./components/RecordControls";
import { SessionPane } from "./components/SessionPane";
import { Sidebar } from "./components/Sidebar";
import { StatusPill } from "./components/StatusPill";
import { useScribely } from "./useScribely";

const OFFLINE_MESSAGE =
  "Can't reach the Scribely backend. Start it by running “uv run scribely-backend” in the backend folder.";

export default function App() {
  const {
    state,
    start,
    stop,
    openSession,
    renameSession,
    deleteSession,
    summarize,
    showLive,
    dismissError,
  } = useScribely();
  const backendState = state.status?.state;
  const connected = state.connection === "open" && state.status !== null;
  const recording = backendState === "recording" || backendState === "stopping";
  const liveSession = state.status?.session ?? null;

  const viewingSaved = state.view.kind === "saved";
  const shown = state.view.kind === "saved" ? state.view.session : liveSession;
  const segments = state.view.kind === "saved" ? state.view.segments : state.segments;
  const partial = viewingSaved ? null : state.partial;

  const emptyMessage = viewingSaved
    ? "Nothing was transcribed in this session."
    : recording
      ? "Listening… the transcript appears here as people speak."
      : "Press Record, then play your lecture.";

  // The recording session is shown live; anything else (including the just-stopped one)
  // is opened from storage so its saved notes come along.
  const openFromList = (id: string) =>
    id === liveSession?.id && recording ? showLive() : openSession(id);

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
          <SessionPane
            key={shown?.id ?? "none"}
            session={shown}
            segments={segments}
            partial={partial}
            live={!viewingSaved}
            recording={recording}
            notes={shown ? state.notes[shown.id] : undefined}
            job={shown ? state.jobs[shown.id] : undefined}
            llmIssue={state.status?.llm_issue ?? null}
            emptyMessage={emptyMessage}
            onRename={(title) => shown && renameSession(shown.id, title)}
            onSummarize={() => shown && summarize(shown.id)}
            onBackToLive={viewingSaved && recording ? showLive : undefined}
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
