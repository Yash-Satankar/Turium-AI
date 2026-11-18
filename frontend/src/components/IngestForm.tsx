import { useState, type FormEvent } from "react";
import { errorMessage } from "../api/client";
import type { IngestRequest, SourceType } from "../api/types";

const NOTE_MAX = 20_000;

interface Props {
  onIngest: (body: IngestRequest) => Promise<unknown>;
}

export function IngestForm({ onIngest }: Props) {
  const [mode, setMode] = useState<SourceType>("note");
  const [note, setNote] = useState("");
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const value = mode === "note" ? note : url;
  const canSubmit = value.trim().length > 0 && !submitting && (mode === "url" || note.length <= NOTE_MAX);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await onIngest(mode === "note" ? { source_type: "note", content: note } : { source_type: "url", url: url.trim() });
      if (mode === "note") setNote("");
      else setUrl("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-stone-700">Save to inbox</h2>
        <div role="tablist" className="flex rounded-lg bg-stone-100 p-0.5 text-sm">
          {(["note", "url"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={`rounded-md px-3 py-1 transition ${
                mode === m ? "bg-white font-medium text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-800"
              }`}
            >
              {m === "note" ? "Note" : "URL"}
            </button>
          ))}
        </div>
      </div>

      {mode === "note" ? (
        <div>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit(e);
            }}
            rows={5}
            placeholder="Paste or write a note. The first line becomes its title."
            className="w-full resize-y rounded-lg border border-stone-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
          />
          <p className={`mt-1 text-right text-xs ${note.length > NOTE_MAX ? "text-red-600" : "text-stone-400"}`}>
            {note.length.toLocaleString()} / {NOTE_MAX.toLocaleString()}
          </p>
        </div>
      ) : (
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/article"
          className="mb-5 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
        />
      )}

      {error && (
        <p role="alert" className="mb-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={!canSubmit}
        className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-stone-300"
      >
        {submitting ? "Saving…" : mode === "note" ? "Save note" : "Save URL"}
      </button>
    </form>
  );
}
