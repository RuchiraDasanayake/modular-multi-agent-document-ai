/**
 * Compare extracted and expected field values with normalization.
 * Used by the review system to determine if an extraction is correct.
 *
 * Must stay in sync with `_case_metrics` in `scripts/run_idpo_benchmark.py`
 * so operator review scores and benchmark exact F1 use the same rule.
 */

const NUMERIC_FIELD_HINTS = ["amount", "price", "total", "subtotal", "tax", "cash", "change", "cost", "fee"];

const FUZZY_MATCH_THRESHOLD = 0.75;

const MONTH_ALIASES: Record<string, string> = {
  janry: "january", janury: "january", janaury: "january",
  febray: "february", feburary: "february", februray: "february",
  marck: "march", mrach: "march",
  apirl: "april", aprl: "april",
  juen: "june", jne: "june",
  jully: "july", jluy: "july",
  agust: "august", augst: "august",
  septmber: "september", septembar: "september", sepember: "september",
  ocober: "october", octber: "october",
  novmber: "november", novamber: "november", novembar: "november",
  decmber: "december", decamber: "december", decembar: "december",
};

function norm(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .join(" ")
    .replace(/\s*([/\-,.])\s*/g, "$1");
}

function normText(value: string): string {
  let text = norm(value);
  text = text.replace(/(\d)[,.](\d)/g, "$1,$2");
  text = text.replace(/([a-z])(\d)/g, "$1 $2");
  text = text.replace(/(\d)([a-z])/g, "$1 $2");
  text = text.split(/\s+/).filter(Boolean).join(" ");
  for (const [bad, good] of Object.entries(MONTH_ALIASES)) {
    text = text.replace(new RegExp(`\\b${bad}\\b`, "g"), good);
  }
  return text.replace(/(?<=[a-z])\.(?=[a-z])/g, "");
}

function isNumericKey(key: string): boolean {
  const lowered = key.trim().toLowerCase();
  return NUMERIC_FIELD_HINTS.some((hint) => lowered.includes(hint));
}

function normalizeExactValue(key: string, value: string): string {
  const normalized = norm(value);
  if (!isNumericKey(key)) {
    return normalized;
  }
  const withoutPrefix = normalized.replace(/^[^\d-]+/, "").trim() || normalized;
  let compact = withoutPrefix.replace(/ /g, "").replace(/,/g, "");
  const parts = compact.split(".");
  if (parts.length === 2) {
    const [integerPart, fracPart] = parts;
    if (fracPart.length === 3) {
      compact = integerPart + fracPart;
    } else {
      const fracStripped = fracPart.replace(/0+$/, "");
      compact = fracStripped ? `${integerPart}.${fracStripped}` : integerPart;
    }
  }
  return compact;
}

function longestMatch(a: string, b: string, aLo: number, aHi: number, bLo: number, bHi: number): [number, number, number] {
  let bestI = aLo;
  let bestJ = bLo;
  let bestSize = 0;
  let prev = new Map<number, number>();
  for (let i = aLo; i < aHi; i += 1) {
    const next = new Map<number, number>();
    for (let j = bLo; j < bHi; j += 1) {
      if (a[i] !== b[j]) {
        continue;
      }
      const size = (prev.get(j - 1) ?? 0) + 1;
      next.set(j, size);
      if (size > bestSize) {
        bestI = i - size + 1;
        bestJ = j - size + 1;
        bestSize = size;
      }
    }
    prev = next;
  }
  return [bestI, bestJ, bestSize];
}

function matchingCharacters(a: string, b: string, aLo: number, aHi: number, bLo: number, bHi: number): number {
  const [i, j, size] = longestMatch(a, b, aLo, aHi, bLo, bHi);
  if (size === 0) {
    return 0;
  }
  return (
    size +
    matchingCharacters(a, b, aLo, i, bLo, j) +
    matchingCharacters(a, b, i + size, aHi, j + size, bHi)
  );
}

/** Ratcliff/Obershelp ratio, equivalent to Python's difflib.SequenceMatcher.ratio() for short strings. */
export function textSimilarity(a: string, b: string): number {
  if (!a || !b) {
    return 0;
  }
  return (2 * matchingCharacters(a, b, 0, a.length, 0, b.length)) / (a.length + b.length);
}

export function compareFieldValues(
  key: string,
  extractedValue: string,
  expectedValue: string,
): boolean {
  const got = normalizeExactValue(key, extractedValue);
  const expected = normalizeExactValue(key, expectedValue);
  if (!got) {
    return false;
  }
  if (got === expected) {
    return true;
  }
  if (isNumericKey(key)) {
    return false;
  }
  return textSimilarity(normText(extractedValue), normText(expectedValue)) >= FUZZY_MATCH_THRESHOLD;
}
