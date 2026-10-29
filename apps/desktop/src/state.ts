import type {
  CapturePermissionMessage,
  DiagnosticsMessage,
  ErrorMessage,
  ExportedMessage,
  LlmSettingsMessage,
  LlmTestMessage,
  NotesJobMessage,
  SearchResultsMessage,
  SessionNotes,
  Session,
  SessionSummary,
  SpeechModelMessage,
  SpeechSettingsMessage,
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
  /** Whether the backend has been reached at least once since the app opened. */
  everConnected: boolean;
  status: StatusMessage | null;
  /** Segments of the live/current session (the in-memory rolling window). */
  segments: TranscriptSegment[];
  partial: TranscriptPartialMessage | null;
  sessions: SessionSummary[];
  view: View;
  /** Generated notes by session id. */
  notes: Record<string, SessionNotes>;
  /** Latest summarize progress by session id. */
  jobs: Record<string, NotesJobMessage>;
  llmSettings: LlmSettingsMessage | null;
  llmTest: LlmTestMessage | "pending" | null;
  exported: ExportedMessage | null;
  error: ErrorMessage | null;
  speechSettings: SpeechSettingsMessage | null;
  /** The speech model being downloaded/loaded, or the last result. */
  speechModel: SpeechModelMessage | null;
  /** Loudness of the captured audio, 0..1. */
  level: number;
  search: SearchResultsMessage | null;
  capturePermission: CapturePermissionMessage | null;
  diagnostics: DiagnosticsMessage | null;
}

export type Action =
  | { kind: "connection"; value: ConnectionState }
  | { kind: "message"; message: ServerMessage }
  | { kind: "showLive" }
  | { kind: "llmTestPending" }
  | { kind: "llmTestReset" }
  | { kind: "dismissExported" }
  | { kind: "dismissError" }
  | { kind: "clearSearch" }
  | { kind: "clearDiagnostics" };

export const initialState: AppState = {
  connection: "connecting",
  everConnected: false,
  status: null,
  segments: [],
  partial: null,
  sessions: [],
  view: { kind: "live" },
  notes: {},
  jobs: {},
  llmSettings: null,
  llmTest: null,
  exported: null,
  error: null,
  speechSettings: null,
  speechModel: null,
  level: 0,
  search: null,
  capturePermission: null,
  diagnostics: null,
};

export function reducer(state: AppState, action: Action): AppState {
  switch (action.kind) {
    case "connection":
      return {
        ...state,
        connection: action.value,
        everConnected: state.everConnected || action.value === "open",
      };
    case "dismissExported":
      return { ...state, exported: null };
    case "dismissError":
      return { ...state, error: null };
    case "clearSearch":
      return { ...state, search: null };
    case "clearDiagnostics":
      return { ...state, diagnostics: null };
    case "showLive":
      return { ...state, view: { kind: "live" } };
    case "llmTestPending":
      return { ...state, llmTest: "pending" };
    case "llmTestReset":
      return { ...state, llmTest: null };
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
        level: message.state === "recording" ? state.level : 0,
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
      const recordingIt =
        message.session.id === state.status?.session?.id && state.status?.state !== "idle";
      const notes = message.notes
        ? { ...state.notes, [message.session.id]: message.notes }
        : state.notes;
      return {
        ...state,
        notes,
        view: recordingIt
          ? { kind: "live" }
          : { kind: "saved", session: message.session, segments: message.segments },
      };
    }
    case "notes_job":
      return { ...state, jobs: { ...state.jobs, [message.session_id]: message } };
    case "notes":
      return { ...state, notes: { ...state.notes, [message.notes.session_id]: message.notes } };
    case "llm_settings":
      return { ...state, llmSettings: message };
    case "llm_test":
      return { ...state, llmTest: message };
    case "exported":
      return { ...state, exported: message };
    case "speech_settings":
      return { ...state, speechSettings: message };
    case "speech_model":
      return { ...state, speechModel: message };
    case "audio_level":
      return { ...state, level: message.level };
    case "search_results":
      return { ...state, search: message };
    case "capture_permission":
      return { ...state, capturePermission: message };
    case "diagnostics":
      return { ...state, diagnostics: message };
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
