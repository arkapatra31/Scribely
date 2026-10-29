import { useState } from "react";
import { EmptyState } from "./components/EmptyState";
import { Notice } from "./components/Notice";
import { RecordDock } from "./components/RecordDock";
import { SessionPane } from "./components/SessionPane";
import { SettingsDialog } from "./components/SettingsDialog";
import { Sidebar } from "./components/Sidebar";
import type { AppState } from "./state";
import { useScribely } from "./useScribely";

const PROVIDER_NAMES: Record<string, string> = {
  azure_openai: "Azure OpenAI",
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Gemini",
  ollama: "Ollama",
};

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

  const backendState = state.status?.state;
  const isConnected = connected(state);
  const recording = backendState === "recording" || backendState === "stopping";
  const liveSession = state.status?.session ?? null;
  const llm = state.llmSettings;
  const llmIssue = state.status?.llm_issue ?? null;
  const needsKey = isConnected && llm?.key_sources[llm.settings.provider] === "missing";

  const viewingSaved = state.view.kind === "saved";
  const shown = state.view.kind === "saved" ? state.view.session : liveSession;
  const segments = state.view.kind === "saved" ? state.view.segments : state.segments;

  // The recording session is shown live; anything else (including the just-stopped one)
  // is opened from storage so its saved notes come along.
  const openFromList = (id: string) =>
    id === liveSession?.id && recording ? showLive() : openSession(id);

  return (
    <div className="flex h-full">
      <Sidebar
        sessions={state.sessions}
        selectedId={shown?.id ?? null}
        recordingId={recording ? (liveSession?.id ?? null) : null}
        connection={connectionInfo(state)}
        llm={
          llm
            ? {
                label: `${PROVIDER_NAMES[llm.settings.provider]} · ${llm.settings.model}`,
                ready: llmIssue === null,
              }
            : null
        }
        onOpen={openFromList}
        onDelete={deleteSession}
        onOpenSettings={openSettings}
      />

      <main className="relative flex min-w-0 flex-1 flex-col">
        <div data-tauri-drag-region className="h-0 shrink-0 [.platform-mac_&]:h-7" />
        <Notice show={state.connection === "closed"} kind="offline">
          Can't reach the Scribely backend. Start it by running “uv run scribely-backend” in
          the backend folder.
        </Notice>
        <Notice show={state.error !== null} kind="warn" onDismiss={dismissError}>
          {state.error?.message}
        </Notice>
        <Notice
          show={needsKey && !settingsOpen}
          kind="key"
          action={{ label: "Add API key", onClick: openSettings }}
        >
          Enter your API key to enable Summarize. It's kept only until Scribely closes.
        </Notice>

        {shown ? (
          <SessionPane
            key={shown.id}
            session={shown}
            segments={segments}
            partial={viewingSaved ? null : state.partial}
            live={!viewingSaved}
            recording={recording}
            notes={state.notes[shown.id]}
            job={state.jobs[shown.id]}
            llmIssue={llmIssue}
            onRename={(title) => renameSession(shown.id, title)}
            onSummarize={() => summarize(shown.id)}
            onOpenSettings={openSettings}
            onBackToLive={viewingSaved && recording ? showLive : undefined}
          />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <EmptyState />
          </div>
        )}

        <RecordDock
          canStart={isConnected && backendState === "idle"}
          recording={recording}
          stopping={backendState === "stopping"}
          loadingModel={backendState === "loading_model"}
          startedAt={liveSession?.started_at}
          onStart={start}
          onStop={stop}
        />
      </main>

      <SettingsDialog
        open={settingsOpen}
        message={state.llmSettings}
        llmIssue={llmIssue}
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

function connectionInfo(state: AppState): { label: string; tone: "ok" | "busy" | "off" } {
  if (state.connection === "connecting") return { label: "Connecting", tone: "busy" };
  if (!connected(state)) return { label: "Offline", tone: "off" };
  return state.status?.state === "loading_model"
    ? { label: "Loading model", tone: "busy" }
    : { label: "Connected", tone: "ok" };
}
