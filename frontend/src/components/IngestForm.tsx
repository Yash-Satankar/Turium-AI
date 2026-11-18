import { useEffect, useState, type FormEvent } from "react";
import { ApiError, errorMessage } from "../api/client";
import type { IngestRequest, SourceType } from "../api/types";

const NOTE_MAX = 20_000;
const CONFIRM_MS = 3000;

const FIELD_CLASS =
  "w-full rounded-lg border px-3 py-2 text-sm outline-none focus:ring-2 aria-[invalid=true]:border-red-400 aria-[invalid=true]:focus:ring-red-100 border-stone-300 focus:border-indigo-500 focus:ring-indigo-100";

interface Props {
  onIngest: (body: IngestRequest) => Promise<unknown>;
}

export function IngestForm({ onIngest }: Props) {
  const [mode, setMode] = useState<SourceType>("note");
  const [note, setNote] = useState("");
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null); // 422 from the API
  const [error, setError] = useState<string | null>(null); // anything else
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!saved) return;
    const t = window.setTimeout(() => setSaved(false), CONFIRM_MS);
    return () => window.clearTimeout(t);
  }, [saved]);

  const value = mode === "note" ? note : url;
  const canSubmit = value.trim().length > 0 && !submitting && (mode === "url" || note.length <= NOTE_MAX);
  const fieldId = mode === "note" ? "note-input" : "url-input";

  function switchMode(m: SourceType) {
    setMode(m);
    setFieldError(null);
    setError(null);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFieldError(null);
    setError(null);
    setSaved(false);
    try {
      await onIngest(mode === "note" ? { source_type: "note", content: note } : { source_type: "url", url: url.trim() });
      if (mode === "note") setNote("");
      else setUrl("");
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setFieldError(err.message);
      else setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm" noValidate>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-stone-700">Save to inbox</h2>
        <div role="group" aria-label="What to save" className="flex rounded-lg bg-stone-100 p-0.5 text-sm">
          {(["note", "url"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => switchMode(m)}
              className={`rounded-md px-3 py-1 transition ${
                mode === m ? "bg-white font-medium text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-800"
              }`}
            >
              {m === "note" ? "Note" : "URL"}
            </button>
          ))}
        </div>
      </div>

      <label htmlFor={fieldId} className="sr-only">
        {mode === "note" ? "Note text" : "Page URL"}
      </label>
      {mode === "note" ? (
        <textarea
          id={fieldId}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit(e);
          }}
          rows={5}
          placeholder="Paste or write a note. The first line becomes its title. (Ctrl+Enter to save)"
          aria-invalid={fieldError ? true : undefined}
          aria-describedby="ingest-feedback"
          className={`${FIELD_CLASS} resize-y`}
        />
      ) : (
        <input
          id={fieldId}
          type="url"
          inputMode="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/article"
          aria-invalid={fieldError ? true : undefined}
          aria-describedby="ingest-feedback"
          className={FIELD_CLASS}
        />
      )}

      <div id="ingest-feedback" aria-live="polite" className="mt-1 flex min-h-5 items-start justify-between gap-2 text-xs">
        <span>
          {fieldError && <span className="text-red-600">{fieldError}</span>}
          {saved && !fieldError && <span className="text-emerald-700">Saved — processing…</span>}
        </span>
        {mode === "note" && (
          <span className={`shrink-0 ${note.length > NOTE_MAX ? "text-red-600" : "text-stone-400"}`}>
            {note.length.toLocaleString()} / {NOTE_MAX.toLocaleString()}
          </span>
        )}
      </div>

      {error && (
        <p role="alert" className="mb-2 mt-1 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={!canSubmit}
        className="mt-2 w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-stone-300"
      >
        {submitting ? "Saving…" : mode === "note" ? "Save note" : "Save URL"}
      </button>
    </form>
  );
}
