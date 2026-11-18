export type SourceType = "note" | "url";
export type ItemStatus = "pending" | "processing" | "ready" | "failed";

export interface Item {
  id: string;
  source_type: SourceType;
  title: string | null;
  url: string | null;
  preview: string | null;
  status: ItemStatus;
  error: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export type IngestRequest =
  | { source_type: "note"; content: string }
  | { source_type: "url"; url: string };

export interface Source {
  index: number;
  item_id: string;
  source_type: SourceType;
  title: string | null;
  url: string | null;
  snippet: string;
  score: number;
}

export interface QueryResponse {
  answer: string;
  found: boolean;
  sources: Source[];
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown[];
    request_id: string | null;
  };
}
