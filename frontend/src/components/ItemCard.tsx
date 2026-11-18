import { useState } from "react";
import { errorMessage } from "../api/client";
import type { Item } from "../api/types";
import { hostname } from "../utils/sources";
import { SourceTypeBadge, StatusBadge } from "./Badges";

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

interface Props {
  item: Item;
  /** Re-ingests a failed URL as a new item. */
  onRetryUrl: (url: string) => Promise<unknown>;
}

export function ItemCard({ item, onRetryUrl }: Props) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const title = item.title ?? (item.url ? hostname(item.url) : "Untitled");
  const canRetry = item.status === "failed" && item.source_type === "url" && item.url;

  async function retry() {
    if (!item.url) return;
    setRetrying(true);
    setRetryError(null);
    try {
      await onRetryUrl(item.url);
    } catch (err) {
      setRetryError(errorMessage(err));
    } finally {
      setRetrying(false);
    }
  }

  return (
    <li className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <SourceTypeBadge type={item.source_type} />
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

      <div className="mt-2 flex items-center justify-between gap-2">
        <p className="text-[11px] text-stone-400">
          {relativeTime(item.created_at)}
          {item.status === "ready" && ` · ${item.chunk_count} chunk${item.chunk_count === 1 ? "" : "s"}`}
        </p>
        {canRetry && (
          <button
            type="button"
            onClick={() => void retry()}
            disabled={retrying}
            className="rounded-md border border-stone-300 px-2 py-0.5 text-xs font-medium text-stone-700 hover:bg-stone-50 disabled:opacity-50"
            title="Saves this URL again as a new item"
          >
            {retrying ? "Retrying…" : "Retry"}
          </button>
        )}
      </div>
      {retryError && (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {retryError}
        </p>
      )}
    </li>
  );
}
