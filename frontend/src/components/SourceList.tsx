import { useState } from "react";
import type { Source } from "../api/types";
import { groupConsecutive, hostname, type SourceGroup } from "../utils/sources";
import { CitationChip, SourceTypeBadge } from "./Badges";

interface Props {
  sources: Source[];
  cited: ReadonlySet<number>;
  highlighted: number | null;
}

function GroupCard({ group, muted, highlighted }: { group: SourceGroup; muted: boolean; highlighted: number | null }) {
  const title = group.title ?? (group.url ? hostname(group.url) : "Untitled note");
  return (
    <li className={`rounded-lg border border-stone-200 bg-white p-3 ${muted ? "opacity-70" : ""}`}>
      <div className="flex min-w-0 items-center gap-2">
        <SourceTypeBadge type={group.sourceType} />
        {group.url ? (
          <a
            href={group.url}
            target="_blank"
            rel="noreferrer noopener"
            className="truncate text-sm font-medium text-indigo-700 hover:underline"
            title={group.url}
          >
            {title}
          </a>
        ) : (
          <span className="truncate text-sm font-medium text-stone-800">{title}</span>
        )}
        {muted && <span className="ml-auto shrink-0 text-[11px] text-stone-400">not cited</span>}
      </div>
      <ol className="mt-2 space-y-2">
        {group.chunks.map((s) => (
          <li
            key={s.index}
            id={`source-${s.index}`}
            className={`flex gap-2 rounded-md p-1.5 transition-colors ${highlighted === s.index ? "bg-indigo-50 ring-1 ring-indigo-300" : ""}`}
          >
            <CitationChip n={s.index} muted={muted} />
            <div className="min-w-0 flex-1">
              <p className="whitespace-pre-line text-xs leading-relaxed text-stone-600">{s.snippet}</p>
              <p className="mt-1 text-[11px] tabular-nums text-stone-400" title="cosine similarity">
                match {s.score.toFixed(2)}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </li>
  );
}

/** Cited sources stay expanded; sources the answer never cites are muted behind a toggle. */
export function SourceList({ sources, cited, highlighted }: Props) {
  const [showUncited, setShowUncited] = useState(false);
  const citedGroups = groupConsecutive(sources.filter((s) => cited.has(s.index)));
  const uncited = sources.filter((s) => !cited.has(s.index));
  const uncitedGroups = groupConsecutive(uncited);

  if (sources.length === 0) return null;
  return (
    <section aria-label="Sources" className="mt-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Sources</h3>
      {citedGroups.length > 0 && (
        <ul className="space-y-2">
          {citedGroups.map((g) => (
            <GroupCard key={`c-${g.chunks[0].index}`} group={g} muted={false} highlighted={highlighted} />
          ))}
        </ul>
      )}
      {uncited.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setShowUncited((v) => !v)}
            aria-expanded={showUncited}
            className="mt-2 text-xs font-medium text-stone-500 hover:text-stone-800"
          >
            {showUncited ? "Hide" : "Show"} {uncited.length} more {uncited.length === 1 ? "source" : "sources"} (not cited)
          </button>
          {showUncited && (
            <ul className="mt-2 space-y-2">
              {uncitedGroups.map((g) => (
                <GroupCard key={`u-${g.chunks[0].index}`} group={g} muted highlighted={highlighted} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
