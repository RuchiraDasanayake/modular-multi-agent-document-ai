import fs from "node:fs";

export function readJsonFile<T>(filePath: string): T | null {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function readTextFile(filePath: string): string | null {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return null;
  }
}

export function readJsonLines<T>(filePath: string): T[] {
  if (!fs.existsSync(filePath)) {
    return [];
  }

  const lines = fs
    .readFileSync(filePath, "utf-8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const parsed: T[] = [];
  for (const line of lines) {
    try {
      parsed.push(JSON.parse(line) as T);
    } catch {
      // ignore malformed line
    }
  }

  return parsed;
}

export function toIsoString(value: number | Date): string {
  return new Date(value).toISOString();
}

export function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

export function average(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function percentile(values: number[], p: number): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index];
}
