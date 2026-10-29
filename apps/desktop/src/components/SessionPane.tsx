import { useEffect, useRef, useState } from "react";
import type {
  NotesJobMessage,
  Session,
  SessionNotes,
  TranscriptPartialMessage,
  TranscriptSegment,
} from "@scribely/schemas";
import { NotesView } from "./NotesView";
import { SessionHeader } from "./SessionHeader";
import { type Tab, Toolbar } from "./Toolbar";
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
  onOpenSettings: () => void;
  onBackToLive?: () => void;
}

/** One session's main pane. Keyed by session id, so tab and scroll state reset per session. */
export function SessionPane(props: Props) {
  const { session, segments, partial, live, recording, notes, job } = props;
  const [tab, setTab] = useState<Tab>(notes ? "notes" : "transcript");
  const [focusTime, setFocusTime] = useState<number | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  // Fresh notes (e.g. after pressing Summarize) open the Notes tab.
  const hadNotes = useRef(notes !== undefined);
  useEffect(() => {
    if (notes && !hadNotes.current) setTab("notes");
    hadNotes.current = notes !== undefined;
  }, [notes]);

  const recordingThis = live && recording;
  const duration = segments.length ? segments[segments.length - 1].end : 0;
  const showNotes = notes !== undefined && tab === "notes";

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
        canSummarize={!recordingThis && segments.length > 0}
        job={job}
        llmIssue={props.llmIssue}
        onTab={(t) => {
          setFocusTime(null);
          setTab(t);
        }}
        onSummarize={props.onSummarize}
        onOpenSettings={props.onOpenSettings}
      />
      {showNotes ? (
        <NotesView
          notes={notes}
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
