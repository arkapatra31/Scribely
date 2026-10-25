import type {
  ErrorMessage,
  Session,
  SessionSummary,
  StatusMessage,
  TranscriptPartialMessage,
  TranscriptSegment,
} from "@scribely/schemas";
import type { ConnectionState, ServerMessage } from "./ws/client";

/** What the main pane shows: the live/current session, or a saved one opened from the list. */
export type View =
  | { kind: "live" }
  | { kind: "saved"; session: Session; segments: TranscriptSegment[] };

export interface AppState {
  connection: ConnectionState;
  status: StatusMessage | null;
  /** Segments of the live/current session (the in-memory rolling window). */
  segments: TranscriptSegment[];
  partial: TranscriptPartialMessage | null;
  sessions: SessionSummary[];
  view: View;
  error: ErrorMessage | null;
}

export type Action =
  | { kind: "connection"; value: ConnectionState }
  | { kind: "message"; message: ServerMessage }
  | { kind: "showLive" }
  | { kind: "dismissError" };

export const initialState: AppState = {
  connection: "connecting",
  status: null,
  segments: [],
  partial: null,
  sessions: [],
  view: { kind: "live" },
  error: null,
};

export function reducer(state: AppState, action: Action): AppState {
  switch (action.kind) {
    case "connection":
      return { ...state, connection: action.value };
    case "dismissError":
      return { ...state, error: null };
    case "showLive":
      return { ...state, view: { kind: "live" } };
    case "message":
      return applyMessage(state, action.message);
  }
}

function applyMessage(state: AppState, message: ServerMessage): AppState {
  switch (message.type) {
    case "status": {
      const newSession = message.session?.id !== state.status?.session?.id;
      const startedRecording = message.state === "recording" && newSession;
      return {
        ...state,
        status: message,
        segments: newSession ? [] : state.segments,
        partial: message.state === "recording" && !newSession ? state.partial : null,
        // A fresh recording takes over the main pane and clears the last problem.
        view: startedRecording ? { kind: "live" } : state.view,
        error: startedRecording ? null : state.error,
      };
    }
    case "transcript_snapshot":
      return { ...state, segments: message.segments, partial: null };
    case "transcript_partial":
      return { ...state, partial: message };
    case "transcript_final": {
      const exists = state.segments.some((s) => s.index === message.segment.index);
      return {
        ...state,
        segments: exists ? state.segments : [...state.segments, message.segment],
        partial: null,
      };
    }
    case "sessions":
      return { ...state, sessions: message.sessions, view: syncView(state.view, message.sessions) };
    case "session_opened": {
      const isLive = message.session.id === state.status?.session?.id;
      return {
        ...state,
        view: isLive
          ? { kind: "live" }
          : { kind: "saved", session: message.session, segments: message.segments },
      };
    }
    case "error":
      return { ...state, error: message };
  }
}

/** Keep an open saved session in step with the list (renamed -> new title, deleted -> live). */
function syncView(view: View, sessions: SessionSummary[]): View {
  if (view.kind !== "saved") return view;
  const match = sessions.find((s) => s.session.id === view.session.id);
  return match ? { ...view, session: match.session } : { kind: "live" };
}
