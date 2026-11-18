import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api/client";
import type { QueryResponse } from "../api/types";

export function useAsk() {
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [question, setQuestion] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => () => inFlight.current?.abort(), []);

  const ask = useCallback(async (q: string, topK = 5) => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setLoading(true);
    setError(null);
    setQuestion(q);
    try {
      setResult(await api.query(q, topK, controller.signal));
    } catch (err) {
      if (controller.signal.aborted) return;
      setResult(null);
      setError(errorMessage(err));
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setLoading(false);
      }
    }
  }, []);

  return { ask, question, result, loading, error };
}
