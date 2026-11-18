import { AskPanel } from "./components/AskPanel";
import { IngestForm } from "./components/IngestForm";
import { ItemList } from "./components/ItemList";
import { useAsk } from "./hooks/useAsk";
import { useItems } from "./hooks/useItems";

export default function App() {
  const { items, loading, error, refresh, ingest } = useItems();
  const ask = useAsk();

  const ready = items.filter((i) => i.status === "ready").length;
  const processing = items.filter((i) => i.status === "pending" || i.status === "processing").length;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Knowledge Inbox</h1>
          <p className="text-sm text-stone-500">Save notes and links, then ask questions answered from what you saved.</p>
        </div>
        <p className="text-xs tabular-nums text-stone-500" aria-live="polite">
          {ready} ready · {processing} processing
        </p>
      </header>

      <main className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="space-y-6">
          <IngestForm onIngest={ingest} />
          <ItemList
            items={items}
            loading={loading}
            error={error}
            onReload={() => void refresh()}
            onRetryUrl={(url) => ingest({ source_type: "url", url })}
          />
        </div>
        <div className="lg:sticky lg:top-8 lg:self-start">
          <AskPanel
            onAsk={(q) => void ask.ask(q)}
            question={ask.question}
            result={ask.result}
            loading={ask.loading}
            error={ask.error}
          />
        </div>
      </main>
    </div>
  );
}
