const RUSSIAN_MONTH_NAMES = [
  "Январь",
  "Февраль",
  "Март",
  "Апрель",
  "Май",
  "Июнь",
  "Июль",
  "Август",
  "Сентябрь",
  "Октябрь",
  "Ноябрь",
  "Декабрь",
] as const;

export function formatReportMonth(value: string): string {
  const [year, month] = value.split("-");
  return `${RUSSIAN_MONTH_NAMES[Number(month) - 1]} ${year?.slice(-2)}`;
}

export function formatReportDay(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year?.slice(-2)}`;
}

export function formatReportCompletionDate(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  }).format(new Date(value));
}

export function formatReportProductName(name: string, version: string): string {
  return `${name} (${version})`;
}

export function matchesReportFilter(value: string, query: string): boolean {
  return value
    .toLocaleLowerCase("ru")
    .includes(query.trim().toLocaleLowerCase("ru"));
}

export function toggleReportFilterId(values: number[], id: number): number[] {
  return values.includes(id)
    ? values.filter((value) => value !== id)
    : [...values, id];
}

export function clearReportFilterIds(): number[] {
  return [];
}
