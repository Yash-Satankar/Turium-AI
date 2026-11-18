import { useState } from "react";
import type { Item } from "../api/types";
import { ItemCard } from "./ItemCard";

type Filter = "all" | "ready" | "processing" | "failed";

const FILTERS: { id: Filter; label: string; match: (i: Item) => boolean }[] = [
  { id: "all", label: "All", match: () => true },
  { id: "ready", label: "Ready", match: (i) => i.status === "ready" },
  { id: "processing", label: "Processing", match: (i) => i.status === "pending" || i.status === "processing" },
  { id: "failed", label: "Failed", match: (i) => i.status === "failed" },
];

interface Props {
  items: Item[];
  loading: boolean;
  error: string | null;
  onReload: () => void;
  onRetryUrl: (url: string) => Promise<unknown>;
}

export function ItemList({ items, loading, error, onReload, onRetryUrl }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const active = FILTERS.find((f) => f.id === filter)!;
  const visible = items.filter(active.match);

  return (
    <section aria-labelledby="items-heading" className="rounded-xl border border-stone-200 bg-stone-100/60 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="items-heading" className="text-sm font-semibold text-stone-700">
          Saved items
        </h2>
        <div role="group" aria-label="Filter items" className="flex flex-wrap gap-1">
          {FILTERS.map((f) => {
            const count = items.filter(f.match).length;
            const selected = f.id === filter;
            return (
              <button
                key={f.id}
                type="button"
                aria-pressed={selected}
                onClick={() => setFilter(f.id)}
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition ${
                  selected ? "bg-stone-800 text-white" : "bg-white text-stone-600 ring-1 ring-stone-200 hover:bg-stone-50"
                }`}
              >
                {f.label} <span className={selected ? "text-stone-300" : "text-stone-400"}>{count}</span>
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-2 flex items-center justify-between rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          <span>{error}</span>
          <button type="button" onClick={onReload} className="font-medium underline">
            Reload
          </button>
        </div>
      )}

      {loading && items.length === 0 ? (
        <p className="p-3 text-sm text-stone-400">Loading…</p>
      ) : items.length === 0 && !error ? (
        <p className="rounded-lg border border-dashed border-stone-300 bg-white p-6 text-center text-sm text-stone-500">
          Nothing saved yet. Add a note or a URL above.
        </p>
      ) : visible.length === 0 ? (
        <p className="p-3 text-center text-sm text-stone-500">No {active.label.toLowerCase()} items.</p>
      ) : (
        <ul className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
          {visible.map((item) => (
            <ItemCard key={item.id} item={item} onRetryUrl={onRetryUrl} />
          ))}
        </ul>
      )}
    </section>
  );
}
