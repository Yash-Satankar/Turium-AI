import type { ItemStatus, SourceType } from "../api/types";

export function CitationChip({ n, onClick, muted }: { n: number; onClick?: () => void; muted?: boolean }) {
  const cls = `inline-flex h-5 min-w-5 items-center justify-center rounded px-1 align-text-top text-[11px] font-semibold ${
    muted ? "bg-stone-100 text-stone-500" : "bg-indigo-100 text-indigo-700"
  }`;
  if (!onClick) return <span className={cls}>{n}</span>;
  return (
    <button type="button" onClick={onClick} className={`${cls} mx-0.5 hover:bg-indigo-200`} aria-label={`Show source ${n}`}>
      {n}
    </button>
  );
}

export function SourceTypeBadge({ type }: { type: SourceType }) {
  return (
    <span className="shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-500">
      {type}
    </span>
  );
}

const STATUS_STYLES: Record<ItemStatus, string> = {
  pending: "bg-amber-50 text-amber-700 ring-amber-200",
  processing: "bg-sky-50 text-sky-700 ring-sky-200",
  ready: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
};

export function StatusBadge({ status }: { status: ItemStatus }) {
  const active = status === "pending" || status === "processing";
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${STATUS_STYLES[status]}`}
    >
      {active && (
        <span
          aria-hidden
          className={`h-2.5 w-2.5 rounded-full border-2 border-current ${
            status === "processing" ? "animate-spin border-t-transparent" : "animate-pulse"
          }`}
        />
      )}
      {status}
    </span>
  );
}
