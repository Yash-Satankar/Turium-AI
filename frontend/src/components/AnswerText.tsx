import { useMemo } from "react";
import { parseAnswer, type Segment } from "../utils/answer";
import { CitationChip } from "./Badges";

interface Props {
  answer: string;
  validSources: ReadonlySet<number>;
  onCite: (n: number) => void;
}

function Segments({ segments, onCite }: { segments: Segment[]; onCite: (n: number) => void }) {
  return (
    <>
      {segments.map((s, i) =>
        s.kind === "text" ? <span key={i}>{s.text}</span> : <CitationChip key={i} n={s.n} onClick={() => onCite(s.n)} />,
      )}
    </>
  );
}

/** Renders plain-text answers: paragraphs, "- " lists and clickable [n] citations. No innerHTML. */
export function AnswerText({ answer, validSources, onCite }: Props) {
  const blocks = useMemo(() => parseAnswer(answer, validSources), [answer, validSources]);
  return (
    <div className="space-y-2">
      {blocks.map((block, i) =>
        block.kind === "paragraph" ? (
          <p key={i} className="whitespace-pre-line">
            <Segments segments={block.segments} onCite={onCite} />
          </p>
        ) : (
          <ul key={i} className="list-disc space-y-1 pl-5">
            {block.items.map((item, j) => (
              <li key={j}>
                <Segments segments={item} onCite={onCite} />
              </li>
            ))}
          </ul>
        ),
      )}
    </div>
  );
}
