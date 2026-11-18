import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api/client";
import type { IngestRequest, Item } from "../api/types";

const POLL_MS = 2000;

const isActive = (item: Item) => item.status === "pending" || item.status === "processing";

export function useItems(limit = 50) {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    try {
      const next = await api.listItems(limit, controller.signal);
      setItems(next);
      setError(null);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(errorMessage(err));
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setLoading(false);
      }
    }
  }, [limit]);

  useEffect(() => {
    void refresh();
    return () => inFlight.current?.abort();
  }, [refresh]);

  // Poll only while something is still being processed.
  const hasActive = items.some(isActive);
  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [hasActive, refresh]);

  const ingest = useCallback(async (body: IngestRequest) => {
    const item = await api.ingest(body); // throws ApiError on 422 etc.; caller shows it
    setItems((prev) => [item, ...prev.filter((i) => i.id !== item.id)]);
    return item;
  }, []);

  return { items, loading, error, refresh, ingest };
}
