import type {
  CapturePermissionCommand,
  ExportSessionCommand,
  LlmSettings,
  NoteDoc,
  RestructureCommand,
  SpeechSettings,
} from "@scribely/schemas";
import { useCallback, useEffect, useReducer, useRef } from "react";
import { initialState, reducer } from "./state";
import { type ClientMessage, DEFAULT_WS_URL, ScribelyClient } from "./ws/client";

export function useScribely(url: string = DEFAULT_WS_URL) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const client = useRef<ScribelyClient | null>(null);

  useEffect(() => {
    const c = new ScribelyClient(
      url,
      (message) => dispatch({ kind: "message", message }),
      (value) => dispatch({ kind: "connection", value }),
    );
    client.current = c;
    c.connect();
    return () => c.close();
  }, [url]);

  const send = useCallback((message: ClientMessage) => client.current?.send(message), []);

  // Settings (and whether an API key has been entered this session) on every (re)connect.
  useEffect(() => {
    if (state.connection !== "open") return;
    send({ type: "get_llm_settings" });
    send({ type: "get_speech_settings" });
  }, [state.connection, send]);

  // The model list shows what's downloaded; refresh it when a model finishes loading.
  const modelState = state.speechModel?.state;
  useEffect(() => {
    if (modelState === "ready") send({ type: "get_speech_settings" });
  }, [modelState, send]);

  return {
    state,
    start: useCallback(() => send({ type: "start" }), [send]),
    stop: useCallback(() => send({ type: "stop" }), [send]),
    pause: useCallback(() => send({ type: "pause" }), [send]),
    resume: useCallback(() => send({ type: "resume" }), [send]),
    openSession: useCallback(
      (session_id: string) => send({ type: "open_session", session_id }),
      [send],
    ),
    renameSession: useCallback(
      (session_id: string, title: string) => send({ type: "rename_session", session_id, title }),
      [send],
    ),
    deleteSession: useCallback(
      (session_id: string) => send({ type: "delete_session", session_id }),
      [send],
    ),
    summarize: useCallback(
      (session_id: string) => send({ type: "summarize", session_id }),
      [send],
    ),
    getLlmSettings: useCallback(() => {
      dispatch({ kind: "llmTestReset" });
      send({ type: "get_llm_settings" });
    }, [send]),
    saveLlmSettings: useCallback(
      (settings: LlmSettings, apiKey: string | null) => {
        dispatch({ kind: "llmTestReset" });
        send({ type: "save_llm_settings", settings, api_key: apiKey });
      },
      [send],
    ),
    testLlm: useCallback(() => {
      dispatch({ kind: "llmTestPending" });
      send({ type: "test_llm" });
    }, [send]),
    restructure: useCallback(
      (session_id: string, style: RestructureCommand["style"]) =>
        send({ type: "restructure", session_id, style }),
      [send],
    ),
    updateNotes: useCallback(
      (session_id: string, doc: NoteDoc) => send({ type: "update_notes", session_id, doc }),
      [send],
    ),
    exportSession: useCallback(
      (session_id: string, format: ExportSessionCommand["format"] = "html") =>
        send({ type: "export_session", session_id, format }),
      [send],
    ),
    saveSpeechSettings: useCallback(
      (settings: SpeechSettings) => send({ type: "save_speech_settings", settings }),
      [send],
    ),
    search: useCallback((query: string) => {
      if (query.trim()) send({ type: "search_sessions", query });
      else dispatch({ kind: "clearSearch" });
    }, [send]),
    capturePermission: useCallback(
      (action: CapturePermissionCommand["action"]) => send({ type: "capture_permission", action }),
      [send],
    ),
    finishOnboarding: useCallback(() => send({ type: "finish_onboarding" }), [send]),
    getDiagnostics: useCallback(() => {
      dispatch({ kind: "clearDiagnostics" });
      send({ type: "get_diagnostics" });
    }, [send]),
    revealExport: useCallback((path: string) => send({ type: "reveal_export", path }), [send]),
    dismissExported: useCallback(() => dispatch({ kind: "dismissExported" }), []),
    showLive: useCallback(() => dispatch({ kind: "showLive" }), []),
    dismissError: useCallback(() => dispatch({ kind: "dismissError" }), []),
  };
}
