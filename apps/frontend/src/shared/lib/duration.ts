export function formatOrderDuration(totalSeconds: number): string {
  const normalizedSeconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(normalizedSeconds / 3600);
  const minutes = Math.floor((normalizedSeconds % 3600) / 60);
  const seconds = normalizedSeconds % 60;
  const parts: string[] = [];

  if (hours > 0) {
    parts.push(`${hours} ч`);
  }
  if (minutes > 0) {
    parts.push(`${minutes} мин`);
  }
  if (seconds > 0 || parts.length === 0) {
    parts.push(`${seconds} сек`);
  }

  return parts.join(" ");
}
