/**
 * Pure parsing for LLM answers: plain text with "- " lists and [n] citations.
 * Rendering happens in AnswerText; nothing here touches the DOM or uses innerHTML.
 */

export type Segment = { kind: "text"; text: string } | { kind: "cite"; n: number };

export type Block = { kind: "paragraph"; segments: Segment[] } | { kind: "list"; items: Segment[][] };

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
const LIST_ITEM = /^\s*[-*]\s+/;
const HEADING = /^\s*#{1,6}\s+/;

/** Removes Markdown the prompt asks the model not to use: bold markers and heading hashes. */
function cleanLine(line: string): string {
  return line.replace(/\*\*/g, "").replace(HEADING, "");
}

/** Splits a line into text and citation segments. Citations to unknown sources stay as text. */
export function parseSegments(line: string, validSources: ReadonlySet<number>): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  const pushText = (text: string) => {
    if (!text) return;
    const prev = segments[segments.length - 1];
    if (prev?.kind === "text") prev.text += text;
    else segments.push({ kind: "text", text });
  };

  for (const match of line.matchAll(CITATION)) {
    const nums = match[1].split(",").map((n) => Number(n.trim()));
    if (!nums.every((n) => validSources.has(n))) continue;
    pushText(line.slice(last, match.index));
    nums.forEach((n) => segments.push({ kind: "cite", n }));
    last = match.index + match[0].length;
  }
  pushText(line.slice(last));
  return segments;
}

/** Groups lines into paragraphs (blank-line separated) and lists ("- " or "* " lines). */
export function parseAnswer(answer: string, validSources: ReadonlySet<number>): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    const text = paragraph.join("\n").trim();
    if (text) blocks.push({ kind: "paragraph", segments: parseSegments(text, validSources) });
    paragraph = [];
  };

  for (const raw of answer.split(/\r?\n/)) {
    const line = cleanLine(raw);
    if (LIST_ITEM.test(line)) {
      flushParagraph();
      const item = parseSegments(line.replace(LIST_ITEM, "").trim(), validSources);
      const prev = blocks[blocks.length - 1];
      if (prev?.kind === "list") prev.items.push(item);
      else blocks.push({ kind: "list", items: [item] });
    } else if (line.trim() === "") {
      flushParagraph();
    } else {
      paragraph.push(line);
    }
  }
  flushParagraph();
  return blocks;
}

/** Source numbers the answer actually cites. */
export function citedSources(answer: string, validSources: ReadonlySet<number>): Set<number> {
  const cited = new Set<number>();
  for (const block of parseAnswer(answer, validSources)) {
    const lines = block.kind === "paragraph" ? [block.segments] : block.items;
    for (const segments of lines) for (const s of segments) if (s.kind === "cite") cited.add(s.n);
  }
  return cited;
}
