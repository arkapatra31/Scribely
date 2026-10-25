import { useEffect, useId, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { LlmSettings, LlmSettingsMessage, LlmTestMessage } from "@scribely/schemas";

type Provider = LlmSettings["provider"];

const PROVIDERS: { value: Provider; label: string; keyEnv?: string }[] = [
  { value: "azure_openai", label: "Azure OpenAI", keyEnv: "AZURE_OPENAI_API_KEY" },
  { value: "openai", label: "OpenAI", keyEnv: "OPENAI_API_KEY" },
  { value: "anthropic", label: "Anthropic", keyEnv: "ANTHROPIC_API_KEY" },
  { value: "gemini", label: "Google Gemini", keyEnv: "GOOGLE_API_KEY" },
  { value: "ollama", label: "Ollama (local, no key)" },
];

interface Props {
  open: boolean;
  message: LlmSettingsMessage | null;
  llmIssue: string | null;
  test: LlmTestMessage | "pending" | null;
  onClose: () => void;
  onSave: (settings: LlmSettings, apiKey: string | null) => void;
  onTest: () => void;
}

export function SettingsDialog({ open, message, llmIssue, test, onClose, onSave, onTest }: Props) {
  const ids = useId();
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
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(e) => e.target === e.currentTarget && onClose()}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${ids}-title`}
            initial={{ y: 12, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 12, opacity: 0 }}
            className="max-h-full w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl dark:bg-stone-900"
          >
            <h2 id={`${ids}-title`} className="text-lg font-semibold">
              Notes model
            </h2>
            <p className="mt-1 text-sm text-stone-500">
              Used only when you press Summarize. Only the transcript text is sent.
            </p>

            {!form ? (
              <p className="mt-6 text-sm text-stone-500">Loading…</p>
            ) : (
              <form
                className="mt-5 space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  save();
                }}
              >
                <Field label="Provider" htmlFor={`${ids}-provider`}>
                  <select
                    id={`${ids}-provider`}
                    value={form.provider}
                    onChange={(e) => changeProvider(e.target.value as Provider)}
                    className={inputClass}
                  >
                    {PROVIDERS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </Field>

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
                          className="shrink-0 rounded-lg px-3 text-sm text-stone-500 hover:text-red-600"
                        >
                          Forget
                        </button>
                      )}
                    </div>
                  </Field>
                )}

                <StatusLine dirty={dirty} llmIssue={llmIssue} test={test} />

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={onTest}
                    disabled={dirty || test === "pending"}
                    title={dirty ? "Save first" : "Send one tiny request"}
                    className="mr-auto rounded-full px-4 py-2 text-sm text-stone-600 hover:bg-stone-100 disabled:opacity-40 dark:text-stone-300 dark:hover:bg-stone-800"
                  >
                    {test === "pending" ? "Testing…" : "Test connection"}
                  </button>
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded-full px-4 py-2 text-sm text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
                  >
                    {dirty ? "Cancel" : "Close"}
                  </button>
                  <button
                    type="submit"
                    disabled={!dirty}
                    className="rounded-full bg-stone-900 px-5 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40 dark:bg-stone-100 dark:text-stone-900"
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

const inputClass =
  "w-full rounded-lg border border-stone-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-stone-500 dark:border-stone-700";

function Field(props: { label: string; htmlFor: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={props.htmlFor} className="mb-1 block text-sm font-medium">
        {props.label}
      </label>
      {props.children}
      {props.hint && <p className="mt-1 text-xs text-stone-500">{props.hint}</p>}
    </div>
  );
}

function StatusLine({ dirty, llmIssue, test }: Pick<Props, "llmIssue" | "test"> & { dirty: boolean }) {
  if (test && test !== "pending") {
    return (
      <p className={`text-sm ${test.ok ? "text-emerald-600" : "text-red-600"}`}>
        {test.ok ? "✓ " : ""}
        {test.message}
      </p>
    );
  }
  if (dirty) return <p className="text-sm text-stone-500">Unsaved changes.</p>;
  return llmIssue ? (
    <p className="text-sm text-amber-700 dark:text-amber-400">{llmIssue}</p>
  ) : (
    <p className="text-sm text-emerald-600">Ready to summarize.</p>
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
