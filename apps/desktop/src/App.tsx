import { useCallback, useEffect, useRef, useState } from "react";
import type { SearchHit } from "@scribely/schemas";
import { EmptyState } from "./components/EmptyState";
import { Notice } from "./components/Notice";
import { Onboarding } from "./components/Onboarding";
import { RecordDock } from "./components/RecordDock";
import { SessionPane } from "./components/SessionPane";
import { SettingsDialog, type SettingsTab } from "./components/SettingsDialog";
import { Sidebar } from "./components/Sidebar";
import { onShellAction, setTrayState } from "./shell";
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
    pause,
    resume,
    openSession,
    renameSession,
    deleteSession,
    summarize,
    getLlmSettings,
    saveLlmSettings,
    testLlm,
    restructure,
    updateNotes,
    exportSession,
    revealExport,
    dismissExported,
    showLive,
    dismissError,
    saveSpeechSettings,
    search,
    capturePermission,
    finishOnboarding,
    getDiagnostics,
  } = useScribely();
  const starting = useStarting(state.everConnected);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("notes");
  const openSettings = (tab: SettingsTab = "notes") => {
    getLlmSettings();
    setSettingsTab(tab);
    setSettingsOpen(true);
  };
  // A search hit to open at: the session and the transcript time to scroll to.
  const [focus, setFocus] = useState<{ sessionId: string; time: number | null } | null>(null);

  const backendState = state.status?.state;
  const isConnected = connected(state);
  const paused = backendState === "paused";
  const recording = backendState === "recording" || paused || backendState === "stopping";
  const liveSession = state.status?.session ?? null;
  const llm = state.llmSettings;
  const llmIssue = state.status?.llm_issue ?? null;
  const needsKey = isConnected && llm?.key_sources[llm.settings.provider] === "missing";

  const viewingSaved = state.view.kind === "saved";
  const shown = state.view.kind === "saved" ? state.view.session : liveSession;
  const segments = state.view.kind === "saved" ? state.view.segments : state.segments;

  // The recording session is shown live; anything else (including the just-stopped one)
  // is opened from storage so its saved notes come along.
  const openFromList = (id: string) => {
    setFocus(null);
    if (id === liveSession?.id && recording) showLive();
    else openSession(id);
  };
  const openHit = (hit: SearchHit) => {
    openFromList(hit.session_id);
    setFocus({ sessionId: hit.session_id, time: hit.field === "transcript" ? (hit.start ?? null) : null });
  };

  const speech = state.speechSettings;
  const speechLanguage = speech?.settings.language ?? null;
  const englishOnly =
    speech?.models.find((m) => m.name === speech.settings.model)?.english_only ?? false;
  const setLanguage = (language: string | null) =>
    speech && saveSpeechSettings({ ...speech.settings, language });

  // Tray menu and global shortcut. A ref keeps the handler on the latest state.
  const controls = useRef({ backendState, isConnected, start, stop, pause, resume });
  controls.current = { backendState, isConnected, start, stop, pause, resume };
  useEffect(
    () =>
      onShellAction((action) => {
        const c = controls.current;
        if (action === "toggle-recording") {
          if (c.backendState === "recording" || c.backendState === "paused") c.stop();
          else if (c.backendState === "idle" && c.isConnected) c.start();
        } else if (c.backendState === "recording") c.pause();
        else if (c.backendState === "paused") c.resume();
      }),
    [],
  );
  useEffect(() => {
    setTrayState(
      backendState === "recording" || backendState === "paused" || backendState === "idle"
        ? backendState
        : "busy",
    );
  }, [backendState]);
  const onSearch = useCallback((q: string) => search(q), [search]);

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
        search={state.search}
        onSearch={onSearch}
        onOpenHit={openHit}
        onOpen={openFromList}
        onDelete={deleteSession}
        onOpenSettings={() => openSettings()}
      />

      <main className="relative flex min-w-0 flex-1 flex-col">
        <div data-tauri-drag-region className="h-0 shrink-0 [.platform-mac_&]:h-7" />
        <Notice show={starting} kind="starting">
          Starting Scribely… The first launch can take a minute.
        </Notice>
        <Notice show={!starting && state.connection === "closed"} kind="offline">
          Can't reach the Scribely backend. Restart Scribely, or run “uv run scribely-backend” in
          the backend folder.
        </Notice>
        <Notice
          show={state.exported !== null}
          kind="ok"
          action={
            state.exported
              ? { label: REVEAL_LABEL, onClick: () => revealExport(state.exported!.path) }
              : undefined
          }
          onDismiss={dismissExported}
        >
          Exported “{state.exported?.filename}”.
        </Notice>
        <Notice show={state.error !== null} kind="warn" onDismiss={dismissError}>
          {state.error?.message}
        </Notice>
        <Notice
          show={needsKey && !settingsOpen && state.status?.onboarded !== false}
          kind="key"
          action={{ label: "Add API key", onClick: () => openSettings("notes") }}
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
            onRestructure={(style) => restructure(shown.id, style)}
            onUpdateNotes={(doc) => updateNotes(shown.id, doc)}
            onExport={(format) => exportSession(shown.id, format)}
            onOpenSettings={() => openSettings("notes")}
            onBackToLive={viewingSaved && recording ? showLive : undefined}
            initialFocus={focus?.sessionId === shown.id ? focus.time : null}
          />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <EmptyState />
          </div>
        )}

        <RecordDock
          canStart={isConnected && backendState === "idle"}
          recording={recording && !paused}
          paused={paused}
          stopping={backendState === "stopping"}
          loadingModel={backendState === "loading_model"}
          elapsed={state.status?.elapsed ?? 0}
          level={state.level}
          speechModel={state.speechModel}
          language={speechLanguage}
          languages={speech?.languages ?? []}
          englishOnly={englishOnly}
          onLanguage={setLanguage}
          onStart={start}
          onStop={stop}
          onPause={pause}
          onResume={resume}
        />
      </main>

      <Onboarding
        open={isConnected && state.status?.onboarded === false}
        speech={speech}
        speechModel={state.speechModel}
        permission={state.capturePermission}
        llmReady={llmIssue === null}
        onSaveSpeech={saveSpeechSettings}
        onPermission={capturePermission}
        onOpenNotesSettings={() => openSettings("notes")}
        onFinish={finishOnboarding}
      />

      <SettingsDialog
        open={settingsOpen}
        initialTab={settingsTab}
        speech={speech}
        speechModel={state.speechModel}
        recording={recording}
        onSaveSpeech={saveSpeechSettings}
        diagnostics={state.diagnostics}
        onGetDiagnostics={getDiagnostics}
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

const REVEAL_LABEL = /Mac/.test(navigator.userAgent)
  ? "Show in Finder"
  : /Win/.test(navigator.userAgent)
    ? "Show in Explorer"
    : "Open folder";

/** True while the app has just opened and the backend it launched is still starting. */
function useStarting(everConnected: boolean): boolean {
  const [gracePeriod, setGracePeriod] = useState(true);
  useEffect(() => {
    const id = setTimeout(() => setGracePeriod(false), 60_000);
    return () => clearTimeout(id);
  }, []);
  return gracePeriod && !everConnected;
}

function connected(state: AppState): boolean {
  return state.connection === "open" && state.status !== null;
}

function connectionInfo(state: AppState): { label: string; tone: "ok" | "busy" | "off" } {
  if (state.connection === "connecting") return { label: "Connecting", tone: "busy" };
  if (!connected(state)) return { label: "Offline", tone: "off" };
  if (state.status?.state === "loading_model") return { label: "Loading model", tone: "busy" };
  if (state.speechModel?.state === "downloading") return { label: "Downloading", tone: "busy" };
  return { label: "Connected", tone: "ok" };
}
