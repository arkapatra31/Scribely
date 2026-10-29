import type { LlmSettings, NoteDoc, RestructureCommand } from "@scribely/schemas";
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
    if (state.connection === "open") send({ type: "get_llm_settings" });
  }, [state.connection, send]);

  return {
    state,
    start: useCallback(() => send({ type: "start" }), [send]),
    stop: useCallback(() => send({ type: "stop" }), [send]),
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
      (session_id: string) => send({ type: "export_session", session_id }),
      [send],
    ),
    revealExport: useCallback((path: string) => send({ type: "reveal_export", path }), [send]),
    dismissExported: useCallback(() => dispatch({ kind: "dismissExported" }), []),
    showLive: useCallback(() => dispatch({ kind: "showLive" }), []),
    dismissError: useCallback(() => dispatch({ kind: "dismissError" }), []),
  };
}
