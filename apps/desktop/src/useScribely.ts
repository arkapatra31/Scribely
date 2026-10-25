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
    showLive: useCallback(() => dispatch({ kind: "showLive" }), []),
    dismissError: useCallback(() => dispatch({ kind: "dismissError" }), []),
  };
}
