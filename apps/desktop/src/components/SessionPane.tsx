import { useEffect, useRef, useState } from "react";
import type {
  NoteDoc,
  NotesJobMessage,
  RestructureCommand,
  Session,
  SessionNotes,
  TranscriptPartialMessage,
  TranscriptSegment,
} from "@scribely/schemas";
import { NotesEditor } from "./NotesEditor";
import { NotesView } from "./NotesView";
import { SessionHeader } from "./SessionHeader";
import { type ExportFormat, type Tab, Toolbar } from "./Toolbar";
import { Transcript } from "./Transcript";

interface Props {
  session: Session;
  segments: TranscriptSegment[];
  partial: TranscriptPartialMessage | null;
  /** Showing the live/current session (vs. a saved one opened from the list). */
  live: boolean;
  recording: boolean;
  notes: SessionNotes | undefined;
  job: NotesJobMessage | undefined;
  llmIssue: string | null;
  onRename: (title: string) => void;
  onSummarize: () => void;
  onRestructure: (style: RestructureCommand["style"]) => void;
  onUpdateNotes: (doc: NoteDoc) => void;
  onExport: (format: ExportFormat) => void;
  onOpenSettings: () => void;
  onBackToLive?: () => void;
  /** Open on the transcript, scrolled to this time (e.g. a search hit). */
  initialFocus?: number | null;
}

/** One session's main pane. Keyed by session id, so tab and scroll state reset per session. */
export function SessionPane(props: Props) {
  const { session, segments, partial, live, recording, notes, job } = props;
  const [tab, setTab] = useState<Tab>(
    notes && props.initialFocus == null ? "notes" : "transcript",
  );
  const [focusTime, setFocusTime] = useState<number | null>(props.initialFocus ?? null);
  useEffect(() => {
    if (props.initialFocus == null) return;
    setFocusTime(props.initialFocus);
    setEditing(false);
    setTab("transcript");
  }, [props.initialFocus]);
  const [editing, setEditing] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  // Fresh notes (e.g. after pressing Summarize) open the Notes tab.
  const hadNotes = useRef(notes !== undefined);
  useEffect(() => {
    if (notes && !hadNotes.current) setTab("notes");
    hadNotes.current = notes !== undefined;
  }, [notes]);

  const recordingThis = live && recording; // recording or paused
  const duration = segments.length ? segments[segments.length - 1].end : 0;
  const showNotes = notes !== undefined && tab === "notes";
  const running = job?.state === "running";

  return (
    <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto pb-32">
      <SessionHeader
        session={session}
        duration={duration}
        recording={recordingThis}
        onRename={props.onRename}
        onBackToLive={props.onBackToLive}
      />
      <div className="h-6" />
      <Toolbar
        tab={showNotes ? "notes" : "transcript"}
        hasNotes={notes !== undefined}
        canSummarize={!recordingThis && segments.length > 0 && !editing}
        canExport={!recordingThis && (segments.length > 0 || notes !== undefined) && !editing}
        job={job}
        llmIssue={props.llmIssue}
        onTab={(t) => {
          setFocusTime(null);
          setEditing(false);
          setTab(t);
        }}
        onSummarize={props.onSummarize}
        onRestructure={(style) => {
          setTab("notes");
          props.onRestructure(style);
        }}
        onExport={props.onExport}
        onOpenSettings={props.onOpenSettings}
      />
      {showNotes && editing ? (
        <NotesEditor
          doc={notes.doc}
          onCancel={() => setEditing(false)}
          onSave={(doc) => {
            props.onUpdateNotes(doc);
            setEditing(false);
          }}
        />
      ) : showNotes ? (
        <NotesView
          notes={notes}
          busy={running}
          onEdit={() => setEditing(true)}
          onJump={(seconds) => {
            setFocusTime(seconds);
            setTab("transcript");
          }}
        />
      ) : (
        <Transcript
          segments={segments}
          partial={partial}
          listening={recordingThis}
          emptyMessage={
            recordingThis
              ? "Listening… the transcript appears here as people speak."
              : "Nothing was transcribed in this session."
          }
          focusTime={focusTime}
          scroller={scroller}
        />
      )}
    </div>
  );
}
