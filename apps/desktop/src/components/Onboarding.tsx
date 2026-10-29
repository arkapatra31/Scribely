import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  AudioLines,
  CircleCheck,
  NotebookPen,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import type {
  CapturePermissionCommand,
  CapturePermissionMessage,
  SpeechModelMessage,
  SpeechSettings,
  SpeechSettingsMessage,
} from "@scribely/schemas";
import { SpeechSettingsPanel } from "./SpeechSettingsPanel";

type Step = "welcome" | "speech" | "permission" | "notes";
const STEPS: Step[] = ["welcome", "speech", "permission", "notes"];

interface Props {
  open: boolean;
  speech: SpeechSettingsMessage | null;
  speechModel: SpeechModelMessage | null;
  permission: CapturePermissionMessage | null;
  llmReady: boolean;
  onSaveSpeech: (settings: SpeechSettings) => void;
  onPermission: (action: CapturePermissionCommand["action"]) => void;
  onOpenNotesSettings: () => void;
  onFinish: () => void;
}

/** First-run setup: language + speech model, the macOS audio permission, the notes model. */
export function Onboarding(props: Props) {
  const reduceMotion = useReducedMotion();
  const [step, setStep] = useState<Step>("welcome");
  const index = STEPS.indexOf(step);
  const next = () => (index < STEPS.length - 1 ? setStep(STEPS[index + 1]) : props.onFinish());
  const { onPermission } = props;

  useEffect(() => {
    if (step === "permission") onPermission("check");
  }, [step, onPermission]);

  return (
    <AnimatePresence>
      {props.open && (
        <motion.div
          className="fixed inset-0 z-40 flex items-center justify-center bg-paper/80 p-6 backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Set up Scribely"
            className="flex max-h-full w-full max-w-xl flex-col overflow-hidden rounded-3xl border border-line bg-paper-raised shadow-float"
          >
            <div className="min-h-0 flex-1 overflow-y-auto p-8">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={step}
                  initial={reduceMotion ? false : { opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={reduceMotion ? undefined : { opacity: 0, x: -12 }}
                  transition={{ duration: 0.18 }}
                >
                  {step === "welcome" && <Welcome />}
                  {step === "speech" && (
                    <>
                      <StepTitle icon={AudioLines} title="How should Scribely listen?">
                        Choose the language of your lectures and a speech model.
                      </StepTitle>
                      <SpeechSettingsPanel
                        message={props.speech}
                        speechModel={props.speechModel}
                        recording={false}
                        onSave={props.onSaveSpeech}
                      />
                    </>
                  )}
                  {step === "permission" && (
                    <PermissionStep permission={props.permission} onPermission={onPermission} />
                  )}
                  {step === "notes" && (
                    <NotesStep ready={props.llmReady} onOpen={props.onOpenNotesSettings} />
                  )}
                </motion.div>
              </AnimatePresence>
            </div>

            <div className="flex items-center gap-3 border-t border-line px-8 py-4">
              <div className="flex gap-1.5" aria-label={`Step ${index + 1} of ${STEPS.length}`}>
                {STEPS.map((s, i) => (
                  <span
                    key={s}
                    className={`h-1.5 rounded-full transition-all ${
                      i === index ? "w-5 bg-accent" : i < index ? "w-1.5 bg-accent/50" : "w-1.5 bg-line-strong"
                    }`}
                  />
                ))}
              </div>
              {index > 0 && (
                <button
                  type="button"
                  onClick={() => setStep(STEPS[index - 1])}
                  className="ml-auto rounded-full px-4 py-2 text-sm text-ink-muted transition hover:bg-paper-sunken hover:text-ink"
                >
                  Back
                </button>
              )}
              <button
                type="button"
                onClick={next}
                className={`inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2 text-sm font-medium text-white shadow-soft transition hover:bg-accent-strong dark:text-paper ${
                  index === 0 ? "ml-auto" : ""
                }`}
              >
                {step === "welcome" ? "Get started" : step === "notes" ? "Start using Scribely" : "Continue"}
                <ArrowRight className="h-4 w-4" aria-hidden />
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Welcome() {
  return (
    <div className="py-4 text-center">
      <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white shadow-soft dark:text-paper">
        <NotebookPen className="h-7 w-7" aria-hidden />
      </span>
      <h1 className="mt-5 font-serif text-3xl font-semibold tracking-tight">Welcome to Scribely</h1>
      <p className="mx-auto mt-3 max-w-sm text-ink-muted">
        Scribely listens to the lecture you're watching, writes the transcript as it plays, and
        turns it into study notes when you're done.
      </p>
      <p className="mx-auto mt-6 max-w-sm rounded-2xl bg-paper-sunken px-4 py-3 text-sm text-ink-muted">
        Everything stays on this computer. Only the finished transcript is sent to the notes
        model you choose, and only when you press Summarize.
      </p>
    </div>
  );
}

function StepTitle(props: { icon: typeof AudioLines; title: string; children: string }) {
  const Icon = props.icon;
  return (
    <div className="mb-6">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <h2 className="mt-4 font-serif text-2xl font-semibold tracking-tight">{props.title}</h2>
      <p className="mt-1 text-sm text-ink-muted">{props.children}</p>
    </div>
  );
}

function PermissionStep(props: {
  permission: CapturePermissionMessage | null;
  onPermission: (action: CapturePermissionCommand["action"]) => void;
}) {
  const { permission, onPermission } = props;
  const box = "flex items-start gap-2 rounded-xl px-3.5 py-2.5 text-sm";
  return (
    <>
      <StepTitle icon={ShieldCheck} title="Let Scribely hear your computer">
        Scribely records your computer's sound, never your microphone or screen.
      </StepTitle>
      {!permission ? (
        <p className="text-sm text-ink-muted">Checking…</p>
      ) : permission.state === "granted" || permission.state === "not_needed" ? (
        <p className={`${box} bg-ok/10 text-ok`}>
          <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" /> {permission.message}
        </p>
      ) : permission.state === "denied" ? (
        <div className="space-y-4">
          <p className={`${box} bg-warn-soft text-warn`}>
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" /> {permission.message}
          </p>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-muted">
            <li>Click Allow access. macOS asks once; after that use System Settings.</li>
            <li>
              Turn on Scribely under Screen & System Audio Recording (your terminal app when
              running from source).
            </li>
            <li>Quit and reopen Scribely.</li>
          </ol>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onPermission("request")}
              className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-white shadow-soft transition hover:bg-accent-strong dark:text-paper"
            >
              Allow access
            </button>
            <button
              type="button"
              onClick={() => onPermission("open_settings")}
              className="rounded-full border border-line px-4 py-2 text-sm transition hover:bg-paper-sunken"
            >
              Open System Settings
            </button>
            <button
              type="button"
              onClick={() => onPermission("check")}
              className="rounded-full px-4 py-2 text-sm text-ink-muted transition hover:bg-paper-sunken hover:text-ink"
            >
              Check again
            </button>
          </div>
        </div>
      ) : (
        <p className={`${box} bg-paper-sunken text-ink-muted`}>
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" /> {permission.message}
        </p>
      )}
    </>
  );
}

function NotesStep({ ready, onOpen }: { ready: boolean; onOpen: () => void }) {
  return (
    <>
      <StepTitle icon={Sparkles} title="Choose a notes model">
        Summaries are written by an AI model you pick: Azure OpenAI, OpenAI, Anthropic, Gemini,
        or Ollama running on this computer.
      </StepTitle>
      {ready ? (
        <p className="flex items-start gap-2 rounded-xl bg-ok/10 px-3.5 py-2.5 text-sm text-ok">
          <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" /> Ready to summarize.
        </p>
      ) : (
        <p className="text-sm text-ink-muted">
          Recording and transcripts work without it, so you can also do this later in Settings.
          API keys are kept only until Scribely closes, never saved.
        </p>
      )}
      <button
        type="button"
        onClick={onOpen}
        className="mt-4 rounded-full border border-line px-4 py-2 text-sm transition hover:bg-paper-sunken"
      >
        {ready ? "Review notes settings" : "Set up the notes model"}
      </button>
    </>
  );
}
