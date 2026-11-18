import { AskPanel } from "./components/AskPanel";
import { IngestForm } from "./components/IngestForm";
import { ItemList } from "./components/ItemList";
import { useAsk } from "./hooks/useAsk";
import { useItems } from "./hooks/useItems";

export default function App() {
  const { items, loading, error, refresh, ingest } = useItems();
  const ask = useAsk();

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Knowledge Inbox</h1>
        <p className="text-sm text-stone-500">Save notes and links, then ask questions answered from what you saved.</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="space-y-6">
          <IngestForm onIngest={ingest} />
          <ItemList items={items} loading={loading} error={error} onRetry={() => void refresh()} />
        </div>
        <div className="lg:sticky lg:top-8 lg:self-start">
          <AskPanel
            onAsk={(q) => void ask.ask(q)}
            question={ask.question}
            result={ask.result}
            loading={ask.loading}
            error={ask.error}
            hasReadyItems={items.some((i) => i.status === "ready")}
          />
        </div>
      </div>
    </div>
  );
}
