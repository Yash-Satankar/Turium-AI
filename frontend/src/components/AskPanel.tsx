import { useMemo, useState, type FormEvent } from "react";
import type { QueryResponse } from "../api/types";
import { citedSources } from "../utils/answer";
import { AnswerText } from "./AnswerText";
import { SourceList } from "./SourceList";

const MAX_QUESTION = 2000;
const COUNTER_FROM = 1800;
const EXAMPLES = [
  "What are the main points of the last article I saved?",
  "What did I write down about deadlines?",
  "Which of my saved links mention pricing?",
];

interface Props {
  onAsk: (question: string) => void;
  question: string | null;
  result: QueryResponse | null;
  loading: boolean;
  error: string | null;
}

export function AskPanel({ onAsk, question, result, loading, error }: Props) {
  const [draft, setDraft] = useState("");
  const [highlighted, setHighlighted] = useState<number | null>(null);

  const valid = useMemo(() => new Set(result?.sources.map((s) => s.index) ?? []), [result]);
  const cited = useMemo(() => (result ? citedSources(result.answer, valid) : new Set<number>()), [result, valid]);

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

  const showEmptyState = !result && !loading && !error && question === null;

  return (
    <section className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-stone-700">Ask your inbox</h2>
      <form onSubmit={submit}>
        <label htmlFor="question" className="sr-only">
          Question
        </label>
        <div className="flex gap-2">
          <input
            id="question"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={MAX_QUESTION}
            disabled={loading}
            placeholder="What did I save about…?"
            className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-stone-50"
          />
          <button
            type="submit"
            disabled={!draft.trim() || loading}
            className="shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-stone-300"
          >
            {loading ? "Asking…" : "Ask"}
          </button>
        </div>
        {draft.length >= COUNTER_FROM && (
          <p className="mt-1 text-right text-xs text-stone-400">
            {draft.length.toLocaleString()} / {MAX_QUESTION.toLocaleString()}
          </p>
        )}
      </form>

      {showEmptyState && (
        <div className="mt-4">
          <p className="text-sm text-stone-500">Ask a question; answers come only from what you've saved, with sources.</p>
          <ul className="mt-2 flex flex-col items-start gap-1.5">
            {EXAMPLES.map((ex) => (
              <li key={ex}>
                <button
                  type="button"
                  onClick={() => setDraft(ex)}
                  className="rounded-full bg-stone-100 px-3 py-1 text-left text-xs text-stone-700 hover:bg-stone-200"
                >
                  {ex}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div aria-live="polite">
        {loading && <p className="mt-4 animate-pulse text-sm text-stone-500">Searching your saved content…</p>}

        {error && !loading && (
          <p role="alert" className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        {result && !loading && (
          <div className="mt-4">
            {question && <p className="mb-2 text-xs text-stone-400">Q: {question}</p>}
            {result.found ? (
              <div className="rounded-lg bg-stone-50 p-3 text-sm leading-relaxed text-stone-800">
                <AnswerText answer={result.answer} validSources={valid} onCite={cite} />
              </div>
            ) : (
              <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                <p>{result.answer}</p>
                <p className="mt-1 text-xs text-amber-700">Try rephrasing, or save something about it first.</p>
              </div>
            )}
            <SourceList sources={result.sources} cited={cited} highlighted={highlighted} />
          </div>
        )}
      </div>
    </section>
  );
}
