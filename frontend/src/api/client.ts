import type { ApiErrorBody, IngestRequest, Item, QueryResponse } from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_ERROR", "Can't reach the server. Is the backend running?", null);
  }

  if (res.ok) return (await res.json()) as T;

  let body: ApiErrorBody | null = null;
  try {
    body = (await res.json()) as ApiErrorBody;
  } catch {
    // non-JSON error (e.g. proxy failure)
  }
  throw new ApiError(
    res.status,
    body?.error?.code ?? "HTTP_ERROR",
    body?.error?.message ?? `Request failed (HTTP ${res.status})`,
    body?.error?.request_id ?? res.headers.get("X-Request-ID"),
  );
}

export const api = {
  listItems: (limit = 50, signal?: AbortSignal) =>
    request<{ items: Item[] }>(`/items?limit=${limit}`, { signal }).then((r) => r.items),

  ingest: (body: IngestRequest) =>
    request<Item>("/ingest", { method: "POST", body: JSON.stringify(body) }),

  query: (question: string, topK: number, signal?: AbortSignal) =>
    request<QueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify({ question, top_k: topK }),
      signal,
    }),
};

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case "PROVIDER_RATE_LIMITED":
        return "The AI provider is rate-limiting requests. Wait a moment and try again.";
      case "PROVIDER_TIMEOUT":
        return "The AI provider took too long to respond. Try again.";
      default:
        return err.message;
    }
  }
  return err instanceof Error ? err.message : "Something went wrong";
}
