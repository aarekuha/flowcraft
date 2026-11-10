export function getMonthDates(month: string, daysInMonth: number): string[] {
  return Array.from(
    { length: daysInMonth },
    (_, index) => `${month}-${String(index + 1).padStart(2, "0")}`,
  );
}

export function getDateRange(startDate: string, endDate: string): string[] {
  const [firstDate, lastDate] = startDate <= endDate
    ? [startDate, endDate]
    : [endDate, startDate];
  const month = firstDate.slice(0, 7);
  const firstDay = Number.parseInt(firstDate.slice(8, 10), 10);
  const lastDay = Number.parseInt(lastDate.slice(8, 10), 10);
  return Array.from(
    { length: lastDay - firstDay + 1 },
    (_, index) => `${month}-${String(firstDay + index).padStart(2, "0")}`,
  );
}

export function getScheduleSelection(
  startDate: string,
  endDate: string,
  existingDates: Set<string>,
  editExistingOnly: boolean,
  includeEmptyDates = false,
): string[] {
  const range = getDateRange(startDate, endDate);
  return editExistingOnly && !includeEmptyDates
    ? range.filter((workDate) => existingDates.has(workDate))
    : range;
}

export function isWeekendDate(workDate: string): boolean {
  const year = Number.parseInt(workDate.slice(0, 4), 10);
  const month = Number.parseInt(workDate.slice(5, 7), 10);
  const day = Number.parseInt(workDate.slice(8, 10), 10);
  const weekday = new Date(year, month - 1, day).getDay();
  return weekday === 0 || weekday === 6;
}
