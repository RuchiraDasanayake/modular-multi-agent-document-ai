/**
 * Compare extracted and expected field values with normalization.
 * Used by the review system to determine if an extraction is correct.
 */

function normalize(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s_\-]+/g, " ")
    .replace(/[,.:;'"!?()[\]{}]/g, "");
}

function normalizeAmount(value: string): string {
  // Strip currency symbols and whitespace, normalize separators
  const cleaned = value.replace(/[$ €£¥₹\s]/g, "");
  // Handle comma as thousands separator: "1,234.56" -> "1234.56"
  // Handle period as thousands separator: "1.234,56" -> "1234.56"
  if (/^\d{1,3}(,\d{3})*(\.\d+)?$/.test(cleaned)) {
    return cleaned.replace(/,/g, "");
  }
  if (/^\d{1,3}(\.\d{3})*(,\d+)?$/.test(cleaned)) {
    return cleaned.replace(/\./g, "").replace(",", ".");
  }
  return cleaned.replace(/,/g, "");
}

const AMOUNT_KEYS = new Set([
  "total", "total_amount", "subtotal", "sub_total", "tax", "tax_amount",
  "change", "change_amount", "cash", "cash_amount", "price", "amount",
  "unit_price", "discount", "tip", "net_amount", "gross_amount",
]);

function isAmountKey(key: string): boolean {
  const normalized = key.trim().toLowerCase().replace(/[\s\-]+/g, "_");
  return AMOUNT_KEYS.has(normalized) || /amount|price|total|cost|fee|tax/i.test(key);
}

export function compareFieldValues(
  key: string,
  extractedValue: string,
  expectedValue: string,
): boolean {
  if (extractedValue === expectedValue) {
    return true;
  }

  const normalizedExtracted = normalize(extractedValue);
  const normalizedExpected = normalize(expectedValue);

  if (normalizedExtracted === normalizedExpected) {
    return true;
  }

  if (isAmountKey(key)) {
    return normalizeAmount(extractedValue) === normalizeAmount(expectedValue);
  }

  return false;
}
