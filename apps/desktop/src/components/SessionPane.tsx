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
import { SummarizeBar } from "./SummarizeBar";
import { Transcript } from "./Transcript";

interface Props {
  session: Session | null;
  segments: TranscriptSegment[];
  partial: TranscriptPartialMessage | null;
  /** Showing the live/current session (vs. a saved one opened from the list). */
  live: boolean;
  recording: boolean;
  notes: SessionNotes | undefined;
  job: NotesJobMessage | undefined;
  llmIssue: string | null;
  emptyMessage: string;
  onRename: (title: string) => void;
  onSummarize: () => void;
  onBackToLive?: () => void;
}

/** One session's main pane. Keyed by session id, so tab and scroll state reset per session. */
export function SessionPane(props: Props) {
  const { session, segments, partial, live, recording, notes, job } = props;
  const [tab, setTab] = useState<"notes" | "transcript">(notes ? "notes" : "transcript");
  const [focusTime, setFocusTime] = useState<number | null>(null);

  // Fresh notes (e.g. after pressing Summarize) open the Notes tab.
  const hadNotes = useRef(notes !== undefined);
  useEffect(() => {
    if (notes && !hadNotes.current) setTab("notes");
    hadNotes.current = notes !== undefined;
  }, [notes]);

  const recordingThis = live && recording;
  const canSummarize = session !== null && !recordingThis && segments.length > 0;
  const duration = segments.length ? segments[segments.length - 1].end : 0;
  const showNotes = notes !== undefined && tab === "notes";

  return (
    <>
      {session && (
        <SessionHeader
          session={session}
          duration={duration}
          live={live}
          onRename={props.onRename}
          onBackToLive={props.onBackToLive}
        />
      )}
      {canSummarize && (
        <SummarizeBar
          hasNotes={notes !== undefined}
          job={job}
          llmIssue={props.llmIssue}
          tab={tab}
          onTab={(t) => {
            setFocusTime(null);
            setTab(t);
          }}
          onSummarize={props.onSummarize}
        />
      )}
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
          emptyMessage={props.emptyMessage}
          focusTime={focusTime}
        />
      )}
    </>
  );
}
