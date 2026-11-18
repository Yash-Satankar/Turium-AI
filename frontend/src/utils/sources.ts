import type { Source } from "../api/types";

export interface SourceGroup {
  itemId: string;
  title: string | null;
  url: string | null;
  sourceType: Source["source_type"];
  chunks: Source[];
}

/** Groups consecutive sources that come from the same saved item, keeping order. */
export function groupConsecutive(sources: Source[]): SourceGroup[] {
  const groups: SourceGroup[] = [];
  for (const s of sources) {
    const last = groups[groups.length - 1];
    if (last && last.itemId === s.item_id) {
      last.chunks.push(s);
    } else {
      groups.push({ itemId: s.item_id, title: s.title, url: s.url, sourceType: s.source_type, chunks: [s] });
    }
  }
  return groups;
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}
