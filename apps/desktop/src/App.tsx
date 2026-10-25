import { useState } from "react";
import { ErrorBanner } from "./components/ErrorBanner";
import { RecordControls } from "./components/RecordControls";
import { SessionPane } from "./components/SessionPane";
import { SettingsDialog } from "./components/SettingsDialog";
import { Sidebar } from "./components/Sidebar";
import { StatusPill } from "./components/StatusPill";
import type { AppState } from "./state";
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
    getLlmSettings,
    saveLlmSettings,
    testLlm,
    showLive,
    dismissError,
  } = useScribely();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const openSettings = () => {
    getLlmSettings();
    setSettingsOpen(true);
  };
  const llm = state.llmSettings;
  const needsKey = connected(state) && llm?.key_sources[llm.settings.provider] === "missing";
  const backendState = state.status?.state;
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
        <div className="flex items-center gap-3">
          <StatusPill state={state} />
          <button
            type="button"
            onClick={openSettings}
            aria-label="Settings"
            title="Settings"
            className="rounded-full p-1.5 text-stone-500 hover:bg-stone-100 hover:text-stone-800 dark:hover:bg-stone-900 dark:hover:text-stone-200"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5" aria-hidden>
              <path
                fillRule="evenodd"
                d="M8.34 1.804A1 1 0 0 1 9.32 1h1.36a1 1 0 0 1 .98.804l.295 1.473c.497.144.971.342 1.416.587l1.25-.834a1 1 0 0 1 1.262.125l.962.962a1 1 0 0 1 .125 1.262l-.834 1.25c.245.445.443.919.587 1.416l1.473.294a1 1 0 0 1 .804.98v1.361a1 1 0 0 1-.804.98l-1.473.295a6.95 6.95 0 0 1-.587 1.416l.834 1.25a1 1 0 0 1-.125 1.262l-.962.962a1 1 0 0 1-1.262.125l-1.25-.834a6.953 6.953 0 0 1-1.416.587l-.294 1.473a1 1 0 0 1-.98.804H9.32a1 1 0 0 1-.98-.804l-.295-1.473a6.957 6.957 0 0 1-1.416-.587l-1.25.834a1 1 0 0 1-1.262-.125l-.962-.962a1 1 0 0 1-.125-1.262l.834-1.25a6.957 6.957 0 0 1-.587-1.416l-1.473-.294A1 1 0 0 1 1 10.68V9.32a1 1 0 0 1 .804-.98l1.473-.295c.144-.497.342-.971.587-1.416l-.834-1.25a1 1 0 0 1 .125-1.262l.962-.962A1 1 0 0 1 5.38 3.03l1.25.834a6.957 6.957 0 0 1 1.416-.587l.294-1.473ZM13 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </header>

      <ErrorBanner message={state.connection === "closed" ? OFFLINE_MESSAGE : null} />
      <ErrorBanner message={state.error?.message ?? null} onDismiss={dismissError} />
      {needsKey && !settingsOpen && (
        <div className="flex items-center gap-3 border-b border-stone-200 bg-stone-100 px-6 py-2 text-sm dark:border-stone-800 dark:bg-stone-900">
          <p className="flex-1 text-stone-600 dark:text-stone-300">
            Enter your API key to enable Summarize. It's kept only until Scribely closes.
          </p>
          <button
            type="button"
            onClick={openSettings}
            className="rounded-full bg-stone-900 px-3 py-1 text-xs font-medium text-white hover:bg-stone-700 dark:bg-stone-100 dark:text-stone-900"
          >
            Add API key
          </button>
        </div>
      )}

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
            onOpenSettings={openSettings}
            onBackToLive={viewingSaved && recording ? showLive : undefined}
          />
          <footer className="border-t border-stone-200 px-6 py-4 dark:border-stone-800">
            <RecordControls
              canStart={connected(state) && backendState === "idle"}
              recording={recording}
              busy={backendState === "loading_model"}
              session={liveSession}
              onStart={start}
              onStop={stop}
            />
          </footer>
        </main>
      </div>

      <SettingsDialog
        open={settingsOpen}
        message={state.llmSettings}
        llmIssue={state.status?.llm_issue ?? null}
        test={state.llmTest}
        onClose={() => setSettingsOpen(false)}
        onSave={saveLlmSettings}
        onTest={testLlm}
      />
    </div>
  );
}

function connected(state: AppState): boolean {
  return state.connection === "open" && state.status !== null;
}
