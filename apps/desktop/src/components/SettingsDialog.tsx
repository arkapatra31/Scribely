import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CircleCheck, ClipboardCopy, Cloud, Cpu, LoaderCircle, TriangleAlert, X } from "lucide-react";
import type {
  DiagnosticsMessage,
  LlmSettings,
  LlmSettingsMessage,
  LlmTestMessage,
  SpeechModelMessage,
  SpeechSettings,
  SpeechSettingsMessage,
} from "@scribely/schemas";
import { SHORTCUT_LABEL } from "../shell";
import { SpeechSettingsPanel } from "./SpeechSettingsPanel";

export type SettingsTab = "speech" | "notes" | "help";

const TABS: { value: SettingsTab; label: string }[] = [
  { value: "speech", label: "Speech" },
  { value: "notes", label: "Notes model" },
  { value: "help", label: "Help" },
];

type Provider = LlmSettings["provider"];

const PROVIDERS: { value: Provider; label: string; note: string; keyEnv?: string }[] = [
  { value: "azure_openai", label: "Azure OpenAI", note: "Cloud", keyEnv: "AZURE_OPENAI_API_KEY" },
  { value: "openai", label: "OpenAI", note: "Cloud", keyEnv: "OPENAI_API_KEY" },
  { value: "anthropic", label: "Anthropic", note: "Cloud", keyEnv: "ANTHROPIC_API_KEY" },
  { value: "gemini", label: "Gemini", note: "Cloud", keyEnv: "GOOGLE_API_KEY" },
  { value: "ollama", label: "Ollama", note: "On this computer" },
];

interface Props {
  open: boolean;
  /** The tab shown when the dialog opens. */
  initialTab: SettingsTab;
  speech: SpeechSettingsMessage | null;
  speechModel: SpeechModelMessage | null;
  recording: boolean;
  onSaveSpeech: (settings: SpeechSettings) => void;
  diagnostics: DiagnosticsMessage | null;
  onGetDiagnostics: () => void;
  message: LlmSettingsMessage | null;
  llmIssue: string | null;
  test: LlmTestMessage | "pending" | null;
  onClose: () => void;
  onSave: (settings: LlmSettings, apiKey: string | null) => void;
  onTest: () => void;
}

export function SettingsDialog(props: Props) {
  const { open, message, llmIssue, test, onClose, onSave, onTest } = props;
  const ids = useId();
  const [tab, setTab] = useState<SettingsTab>(props.initialTab);
  useEffect(() => {
    if (open) setTab(props.initialTab);
  }, [open, props.initialTab]);
  const [form, setForm] = useState<LlmSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [dirty, setDirty] = useState(false);

  // Load the server's settings when the dialog opens or after a save round-trips.
  useEffect(() => {
    if (open && message && !dirty) setForm(message.settings);
  }, [open, message, dirty]);
  useEffect(() => {
    if (!open) {
      setDirty(false);
      setApiKey("");
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const update = (patch: Partial<LlmSettings>) => {
    setForm((f) => (f ? { ...f, ...patch } : f));
    setDirty(true);
  };

  const changeProvider = (provider: Provider) => {
    const options = modelOptions(message, provider);
    update({
      provider,
      model: options.includes(form?.model ?? "") ? form!.model : (options[0] ?? ""),
    });
    setApiKey("");
  };

  const save = (forgetKey = false) => {
    if (!form) return;
    onSave(form, forgetKey ? "" : apiKey.trim() || null);
    setApiKey("");
    setDirty(false);
  };

  const provider = PROVIDERS.find((p) => p.value === form?.provider);
  const keySource = form ? message?.key_sources[form.provider] : undefined;
  const options = form ? modelOptions(message, form.provider) : [];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-6 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(e) => e.target === e.currentTarget && onClose()}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${ids}-title`}
            initial={{ y: 12, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 12, opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className="relative max-h-full w-full max-w-xl overflow-y-auto rounded-3xl border border-line bg-paper-raised p-7 shadow-float"
          >
            <button
              type="button"
              onClick={onClose}
              aria-label="Close settings"
              className="absolute right-5 top-5 rounded-full p-1.5 text-ink-faint transition hover:bg-paper-sunken hover:text-ink"
            >
              <X className="h-4 w-4" />
            </button>
            <h2 id={`${ids}-title`} className="font-serif text-2xl font-semibold tracking-tight">
              Settings
            </h2>
            <div role="tablist" className="mt-4 flex gap-1 rounded-full bg-paper-sunken p-1">
              {TABS.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.value}
                  onClick={() => setTab(t.value)}
                  className={`flex-1 rounded-full px-3 py-1.5 text-sm font-medium transition ${
                    tab === t.value
                      ? "bg-paper-raised text-ink shadow-soft"
                      : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {tab === "speech" ? (
              <div className="mt-6">
                <SpeechSettingsPanel
                  message={props.speech}
                  speechModel={props.speechModel}
                  recording={props.recording}
                  onSave={props.onSaveSpeech}
                />
              </div>
            ) : tab === "help" ? (
              <HelpTab diagnostics={props.diagnostics} onGetDiagnostics={props.onGetDiagnostics} />
            ) : !form ? (
              <p className="mt-6 flex items-center gap-2 text-sm text-ink-muted">
                <LoaderCircle className="h-4 w-4 animate-spin" /> Loading…
              </p>
            ) : (
              <form
                className="mt-6 space-y-4"
                aria-describedby={`${ids}-notes-hint`}
                onSubmit={(e) => {
                  e.preventDefault();
                  save();
                }}
              >
                <p id={`${ids}-notes-hint`} className="text-sm text-ink-muted">
                  Used only when you press Summarize. Only the transcript text is sent.
                </p>
                <fieldset>
                  <legend className="mb-2 text-sm font-medium">Provider</legend>
                  <div className="grid grid-cols-5 gap-2">
                    {PROVIDERS.map((p) => {
                      const active = form.provider === p.value;
                      const Icon = p.keyEnv ? Cloud : Cpu;
                      return (
                        <button
                          key={p.value}
                          type="button"
                          aria-pressed={active}
                          onClick={() => changeProvider(p.value)}
                          className={`flex flex-col items-start gap-1.5 rounded-2xl border px-3 py-2.5 text-left transition ${
                            active
                              ? "border-accent bg-accent-soft shadow-soft"
                              : "border-line hover:border-line-strong hover:bg-paper-sunken"
                          }`}
                        >
                          <Icon
                            className={`h-4 w-4 ${active ? "text-accent" : "text-ink-faint"}`}
                            aria-hidden
                          />
                          <span>
                            <span className="block text-[13px] font-medium leading-tight">
                              {p.label}
                            </span>
                            <span className="block text-[11px] text-ink-muted">{p.note}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </fieldset>

                <Field
                  label="Model"
                  htmlFor={`${ids}-model`}
                  hint={
                    form.provider === "azure_openai"
                      ? "The model behind your deployment (used to size requests)."
                      : form.provider === "ollama" && options.length === 0
                        ? "No pulled models found. Run `ollama pull <model>`, or type a name."
                        : "Pick one or type any model name."
                  }
                >
                  <input
                    id={`${ids}-model`}
                    list={`${ids}-models`}
                    value={form.model}
                    onChange={(e) => update({ model: e.target.value })}
                    required
                    className={inputClass}
                  />
                  <datalist id={`${ids}-models`}>
                    {options.map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                </Field>

                {form.provider === "azure_openai" && (
                  <>
                    <Field label="Endpoint" htmlFor={`${ids}-endpoint`}>
                      <input
                        id={`${ids}-endpoint`}
                        type="url"
                        placeholder="https://your-resource.openai.azure.com/"
                        value={form.azure_endpoint ?? ""}
                        onChange={(e) => update({ azure_endpoint: e.target.value || null })}
                        className={inputClass}
                      />
                    </Field>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Deployment" htmlFor={`${ids}-deployment`}>
                        <input
                          id={`${ids}-deployment`}
                          placeholder="gpt-4o"
                          value={form.azure_deployment ?? ""}
                          onChange={(e) => update({ azure_deployment: e.target.value || null })}
                          className={inputClass}
                        />
                      </Field>
                      <Field label="API version" htmlFor={`${ids}-version`}>
                        <input
                          id={`${ids}-version`}
                          value={form.azure_api_version}
                          onChange={(e) => update({ azure_api_version: e.target.value })}
                          className={inputClass}
                        />
                      </Field>
                    </div>
                  </>
                )}

                {form.provider === "ollama" && (
                  <Field label="Ollama host" htmlFor={`${ids}-host`}>
                    <input
                      id={`${ids}-host`}
                      value={form.ollama_host}
                      onChange={(e) => update({ ollama_host: e.target.value })}
                      className={inputClass}
                    />
                  </Field>
                )}

                {provider?.keyEnv && (
                  <Field
                    label="API key"
                    htmlFor={`${ids}-key`}
                    hint={keyHint(keySource, provider.keyEnv)}
                  >
                    <div className="flex gap-2">
                      <input
                        id={`${ids}-key`}
                        type="password"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder={keySource === "session" ? "•••••••• (entered)" : "Paste your API key"}
                        value={apiKey}
                        onChange={(e) => {
                          setApiKey(e.target.value);
                          setDirty(true);
                        }}
                        className={inputClass}
                      />
                      {keySource === "session" && (
                        <button
                          type="button"
                          onClick={() => save(true)}
                          className="shrink-0 rounded-xl px-3 text-sm text-ink-muted transition hover:bg-rec-soft hover:text-rec"
                        >
                          Forget
                        </button>
                      )}
                    </div>
                  </Field>
                )}

                <StatusLine dirty={dirty} llmIssue={llmIssue} test={test} />

                <div className="flex items-center justify-end gap-2 border-t border-line pt-4">
                  <button
                    type="button"
                    onClick={onTest}
                    disabled={dirty || test === "pending"}
                    title={dirty ? "Save first" : "Send one tiny request"}
                    className="mr-auto inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm text-ink transition hover:bg-paper-sunken disabled:opacity-40"
                  >
                    {test === "pending" && <LoaderCircle className="h-4 w-4 animate-spin" />}
                    {test === "pending" ? "Testing…" : "Test connection"}
                  </button>
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded-full px-4 py-2 text-sm text-ink-muted transition hover:bg-paper-sunken hover:text-ink"
                  >
                    {dirty ? "Cancel" : "Close"}
                  </button>
                  <button
                    type="submit"
                    disabled={!dirty}
                    className="rounded-full bg-accent px-5 py-2 text-sm font-medium text-white shadow-soft transition hover:bg-accent-strong disabled:opacity-40 dark:text-paper"
                  >
                    Save
                  </button>
                </div>
              </form>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function HelpTab(props: {
  diagnostics: DiagnosticsMessage | null;
  onGetDiagnostics: () => void;
}) {
  const { diagnostics, onGetDiagnostics } = props;
  const [copy, setCopy] = useState<"idle" | "pending" | "copied" | "failed">("idle");
  const fallback = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (copy !== "pending" || !diagnostics) return;
    navigator.clipboard
      .writeText(diagnostics.text)
      .then(() => setCopy("copied"))
      .catch(() => setCopy("failed"));
  }, [copy, diagnostics]);
  useEffect(() => {
    if (copy === "failed") fallback.current?.select();
    if (copy !== "copied") return;
    const id = setTimeout(() => setCopy("idle"), 2500);
    return () => clearTimeout(id);
  }, [copy]);

  return (
    <div className="mt-6 space-y-5 text-sm">
      <section>
        <h3 className="font-medium">Keyboard shortcut</h3>
        <p className="mt-1 text-ink-muted">
          <kbd className="rounded-md border border-line bg-paper px-1.5 py-0.5 font-mono text-xs">
            {SHORTCUT_LABEL}
          </kbd>{" "}
          starts or stops recording from anywhere, even when Scribely is in the background.
        </p>
      </section>
      <section>
        <h3 className="font-medium">Something not working?</h3>
        <p className="mt-1 text-ink-muted">
          Copy a diagnostics report and paste it into your bug report. It has version numbers,
          settings and recent log lines — never API keys or transcripts.
        </p>
        <button
          type="button"
          onClick={() => {
            setCopy("pending");
            onGetDiagnostics();
          }}
          disabled={copy === "pending"}
          className="mt-3 inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-ink transition hover:bg-paper-sunken disabled:opacity-50"
        >
          {copy === "copied" ? (
            <CircleCheck className="h-4 w-4 text-ok" />
          ) : (
            <ClipboardCopy className="h-4 w-4" />
          )}
          {copy === "copied" ? "Copied" : "Copy diagnostics"}
        </button>
        {copy === "failed" && diagnostics && (
          <textarea
            ref={fallback}
            readOnly
            value={diagnostics.text}
            className="mt-3 h-40 w-full rounded-xl border border-line bg-paper p-2 font-mono text-[11px]"
          />
        )}
        {diagnostics?.log_path && (
          <p className="mt-3 break-all text-xs text-ink-faint">Log file: {diagnostics.log_path}</p>
        )}
      </section>
    </div>
  );
}

const inputClass =
  "w-full rounded-xl border border-line-strong bg-paper px-3.5 py-2 text-sm outline-none transition placeholder:text-ink-faint focus:border-accent focus:ring-4 focus:ring-accent/10";

function Field(props: { label: string; htmlFor: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={props.htmlFor} className="mb-1.5 block text-sm font-medium">
        {props.label}
      </label>
      {props.children}
      {props.hint && <p className="mt-1.5 text-xs text-ink-muted">{props.hint}</p>}
    </div>
  );
}

function StatusLine({ dirty, llmIssue, test }: Pick<Props, "llmIssue" | "test"> & { dirty: boolean }) {
  const box = "flex items-start gap-2 rounded-xl px-3.5 py-2.5 text-sm";
  if (test && test !== "pending") {
    return test.ok ? (
      <p className={`${box} bg-ok/10 text-ok`}>
        <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" /> {test.message}
      </p>
    ) : (
      <p className={`${box} bg-rec-soft text-rec`}>
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" /> {test.message}
      </p>
    );
  }
  if (dirty) return <p className={`${box} bg-paper-sunken text-ink-muted`}>Unsaved changes.</p>;
  return llmIssue ? (
    <p className={`${box} bg-warn-soft text-warn`}>
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" /> {llmIssue}
    </p>
  ) : (
    <p className={`${box} bg-ok/10 text-ok`}>
      <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" /> Ready to summarize.
    </p>
  );
}

function keyHint(source: string | undefined, env: string): string {
  switch (source) {
    case "session":
      return "Entered this session. Leave blank to keep it. It's forgotten when Scribely closes.";
    case "env":
      return `Using ${env} from your environment. Paste a key to use a different one.`;
    default:
      return "Required. Kept in memory until Scribely closes — never saved.";
  }
}

function modelOptions(message: LlmSettingsMessage | null, provider: Provider): string[] {
  if (!message) return [];
  return provider === "ollama" ? message.ollama_models : (message.suggested_models[provider] ?? []);
}
