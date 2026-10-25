import type {
  ErrorMessage,
  StatusMessage,
  TranscriptPartialMessage,
  TranscriptSegment,
} from "@scribely/schemas";
import type { ConnectionState, ServerMessage } from "./ws/client";

export interface AppState {
  connection: ConnectionState;
  status: StatusMessage | null;
  segments: TranscriptSegment[];
  partial: TranscriptPartialMessage | null;
  error: ErrorMessage | null;
}

export type Action =
  | { kind: "connection"; value: ConnectionState }
  | { kind: "message"; message: ServerMessage }
  | { kind: "dismissError" };

export const initialState: AppState = {
  connection: "connecting",
  status: null,
  segments: [],
  partial: null,
  error: null,
};

export function reducer(state: AppState, action: Action): AppState {
  switch (action.kind) {
    case "connection":
      return { ...state, connection: action.value };
    case "dismissError":
      return { ...state, error: null };
    case "message":
      return applyMessage(state, action.message);
  }
}

function applyMessage(state: AppState, message: ServerMessage): AppState {
  switch (message.type) {
    case "status": {
      const newSession = message.session?.id !== state.status?.session?.id;
      return {
        ...state,
        status: message,
        segments: newSession ? [] : state.segments,
        partial: message.state === "recording" && !newSession ? state.partial : null,
        // A fresh recording clears the last problem.
        error: message.state === "recording" && newSession ? null : state.error,
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
    case "error":
      return { ...state, error: message };
  }
}
