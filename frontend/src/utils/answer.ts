/**
 * Pure parsing for LLM answers: plain text with "- " lists and [n] citations.
 * Rendering happens in AnswerText; nothing here touches the DOM or uses innerHTML.
 */

/**
 * A citation group renders as one unbreakable unit: the word before it (no space before the chip),
 * one or more chips, and any punctuation right after, so a chip never starts a line on its own.
 */
export type CiteGroup = { kind: "cite"; lead: string; ns: number[]; trail: string };
export type Segment = { kind: "text"; text: string } | CiteGroup;

export type Block = { kind: "paragraph"; segments: Segment[] } | { kind: "list"; items: Segment[][] };

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
const LIST_ITEM = /^\s*[-*]\s+/;
const HEADING = /^\s*#{1,6}\s+/;
const TRAILING_PUNCT = /^[.,;:]+/;
const LAST_WORD = /\S+$/;

/** Removes Markdown the prompt asks the model not to use: bold markers and heading hashes. */
function cleanLine(line: string): string {
  return line.replace(/\*\*/g, "").replace(HEADING, "");
}

/** Splits a line into text and citation groups. Citations to unknown sources stay as text. */
export function parseSegments(line: string, validSources: ReadonlySet<number>): Segment[] {
  const segments: Segment[] = [];
  const pushText = (text: string) => {
    if (!text) return;
    const prev = segments[segments.length - 1];
    if (prev?.kind === "text") prev.text += text;
    else segments.push({ kind: "text", text });
  };

  let pos = 0;
  for (const match of line.matchAll(CITATION)) {
    const nums = match[1].split(",").map((n) => Number(n.trim()));
    if (!nums.every((n) => validSources.has(n))) continue;

    const before = line.slice(pos, match.index);
    const prev = segments[segments.length - 1];
    if (prev?.kind === "cite" && prev.trail === "" && before.trim() === "") {
      prev.ns.push(...nums); // "[1][2]" or "[1] [2]" -> one group
    } else {
      const trimmed = before.replace(/\s+$/, ""); // no space before the chip
      const lead = trimmed.match(LAST_WORD)?.[0] ?? "";
      pushText(trimmed.slice(0, trimmed.length - lead.length));
      segments.push({ kind: "cite", lead, ns: [...nums], trail: "" });
    }
    pos = match.index + match[0].length;

    const trail = line.slice(pos).match(TRAILING_PUNCT)?.[0];
    if (trail) {
      (segments[segments.length - 1] as CiteGroup).trail = trail;
      pos += trail.length;
    }
  }
  pushText(line.slice(pos));
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
    for (const segments of lines) for (const s of segments) if (s.kind === "cite") s.ns.forEach((n) => cited.add(n));
  }
  return cited;
}
