import { useState, type FormEvent, type ReactNode } from "react";
import type { QueryResponse, Source } from "../api/types";

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/** Turns "[1]" / "[1, 2]" in the answer into chips that jump to the matching source. */
function renderAnswer(answer: string, sources: Source[], onCite: (n: number) => void): ReactNode[] {
  const valid = new Set(sources.map((s) => s.index));
  const out: ReactNode[] = [];
  let last = 0;
  for (const match of answer.matchAll(CITATION)) {
    const nums = match[1].split(",").map((n) => Number(n.trim()));
    if (!nums.every((n) => valid.has(n))) continue;
    out.push(answer.slice(last, match.index));
    nums.forEach((n) =>
      out.push(
        <button
          key={`${match.index}-${n}`}
          type="button"
          onClick={() => onCite(n)}
          className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded bg-indigo-100 px-1 align-text-top text-[11px] font-semibold text-indigo-700 hover:bg-indigo-200"
          aria-label={`Source ${n}`}
        >
          {n}
        </button>,
      ),
    );
    last = match.index + match[0].length;
  }
  out.push(answer.slice(last));
  return out;
}

function SourceCard({ source, highlighted }: { source: Source; highlighted: boolean }) {
  return (
    <li
      id={`source-${source.index}`}
      className={`rounded-lg border p-3 transition ${highlighted ? "border-indigo-400 bg-indigo-50" : "border-stone-200 bg-white"}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded bg-indigo-100 px-1 text-[11px] font-semibold text-indigo-700">
            {source.index}
          </span>
          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer noopener"
              className="truncate text-sm font-medium text-indigo-700 hover:underline"
            >
              {source.title ?? source.url}
            </a>
          ) : (
            <span className="truncate text-sm font-medium text-stone-800">{source.title ?? "Untitled note"}</span>
          )}
        </div>
        <span className="shrink-0 text-[11px] tabular-nums text-stone-400" title="Cosine similarity">
          {source.score.toFixed(2)}
        </span>
      </div>
      <p className="mt-1.5 whitespace-pre-line text-xs leading-relaxed text-stone-600">{source.snippet}</p>
    </li>
  );
}

interface Props {
  onAsk: (question: string) => void;
  question: string | null;
  result: QueryResponse | null;
  loading: boolean;
  error: string | null;
  hasReadyItems: boolean;
}

export function AskPanel({ onAsk, question, result, loading, error, hasReadyItems }: Props) {
  const [draft, setDraft] = useState("");
  const [highlighted, setHighlighted] = useState<number | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = draft.trim();
    if (!q || loading) return;
    setHighlighted(null);
    onAsk(q);
  }

  function cite(n: number) {
    setHighlighted(n);
    document.getElementById(`source-${n}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  return (
    <section className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-stone-700">Ask your inbox</h2>
      <form onSubmit={submit} className="flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={2000}
          placeholder={hasReadyItems ? "What did I save about…?" : "Save something first, then ask about it"}
          className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
        />
        <button
          type="submit"
          disabled={!draft.trim() || loading}
          className="shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-stone-300"
        >
          {loading ? "Thinking…" : "Ask"}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {loading && !result && <p className="mt-4 animate-pulse text-sm text-stone-400">Searching your saved content…</p>}

      {result && (
        <div className={`mt-4 transition-opacity ${loading ? "opacity-50" : ""}`}>
          {question && <p className="mb-2 text-xs text-stone-400">Q: {question}</p>}
          <div
            className={`rounded-lg p-3 text-sm leading-relaxed ${
              result.found ? "bg-stone-50 text-stone-800" : "bg-amber-50 text-amber-800"
            }`}
          >
            <p className="whitespace-pre-line">{renderAnswer(result.answer, result.sources, cite)}</p>
          </div>

          {result.sources.length > 0 && (
            <>
              <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-stone-500">Sources</h3>
              <ol className="space-y-2">
                {result.sources.map((s) => (
                  <SourceCard key={s.index} source={s} highlighted={highlighted === s.index} />
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </section>
  );
}
