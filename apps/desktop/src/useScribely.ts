import { useCallback, useEffect, useReducer, useRef } from "react";
import { initialState, reducer } from "./state";
import { DEFAULT_WS_URL, ScribelyClient } from "./ws/client";

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

  const start = useCallback(() => client.current?.send({ type: "start" }), []);
  const stop = useCallback(() => client.current?.send({ type: "stop" }), []);
  const dismissError = useCallback(() => dispatch({ kind: "dismissError" }), []);

  return { state, start, stop, dismissError };
}
