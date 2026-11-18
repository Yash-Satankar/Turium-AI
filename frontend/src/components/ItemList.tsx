import type { Item, ItemStatus } from "../api/types";

const STATUS_STYLES: Record<ItemStatus, string> = {
  pending: "bg-amber-50 text-amber-700 ring-amber-200",
  processing: "bg-sky-50 text-sky-700 ring-sky-200",
  ready: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
};

function StatusBadge({ status }: { status: ItemStatus }) {
  const active = status === "pending" || status === "processing";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${STATUS_STYLES[status]}`}>
      {active && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {status}
    </span>
  );
}

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function ItemCard({ item }: { item: Item }) {
  const title = item.title ?? (item.url ? hostname(item.url) : "Untitled");
  return (
    <li className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-500">
              {item.source_type}
            </span>
            <h3 className="truncate text-sm font-medium text-stone-900" title={title}>
              {title}
            </h3>
          </div>
          {item.url && (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-0.5 block truncate text-xs text-indigo-600 hover:underline"
            >
              {item.url}
            </a>
          )}
        </div>
        <StatusBadge status={item.status} />
      </div>

      {item.status === "failed" && item.error ? (
        <p className="mt-2 text-xs text-red-700">{item.error}</p>
      ) : (
        item.preview && <p className="mt-2 line-clamp-2 text-xs text-stone-600">{item.preview}</p>
      )}

      <p className="mt-2 text-[11px] text-stone-400">
        {relativeTime(item.created_at)}
        {item.status === "ready" && ` · ${item.chunk_count} chunk${item.chunk_count === 1 ? "" : "s"}`}
      </p>
    </li>
  );
}

interface Props {
  items: Item[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export function ItemList({ items, loading, error, onRetry }: Props) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-stone-700">
        Saved items {items.length > 0 && <span className="font-normal text-stone-400">({items.length})</span>}
      </h2>

      {error && (
        <div role="alert" className="mb-2 flex items-center justify-between rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          <span>{error}</span>
          <button onClick={onRetry} className="font-medium underline">
            Retry
          </button>
        </div>
      )}

      {loading && items.length === 0 ? (
        <p className="text-sm text-stone-400">Loading…</p>
      ) : items.length === 0 && !error ? (
        <p className="rounded-xl border border-dashed border-stone-300 p-6 text-center text-sm text-stone-500">
          Nothing saved yet. Add a note or a URL above.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </ul>
      )}
    </section>
  );
}
