export function parseStandardTimeInput(value: string): number | null | undefined {
  const normalizedValue = value.trim();
  if (!normalizedValue) {
    return null;
  }

  const match = /^(\d+):([0-5]\d)$/.exec(normalizedValue);
  if (!match) {
    return undefined;
  }

  const minutes = Number(match[1]);
  const seconds = Number(match[2]);
  const totalSeconds = minutes * 60 + seconds;
  return Number.isSafeInteger(totalSeconds) && totalSeconds <= 2_147_483_647
    ? totalSeconds
    : undefined;
}

export function formatStandardTimeInput(totalSeconds: number | null): string {
  if (totalSeconds === null) {
    return "";
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
