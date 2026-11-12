import type { PlanningOrderForecast } from "@/shared/api/planning";

const ISSUE_LABELS: Record<string, string> = {
  no_skilled_worker: "Нет активных исполнителей с требуемым навыком",
  no_assignment: "Нет назначения исполнителя",
  no_skilled_assignee: "У назначенных исполнителей нет требуемого навыка",
  no_schedule: "Нет графика работы исполнителя",
  outside_horizon: "Выходит за пределы периода",
  missing_standard_time: "Не указано нормативное время операции",
  insufficient_statistics: "Недостаточно статистики для расчёта времени операции",
  no_operations: "В изделии нет операций для расчёта",
  blocked_by_stage: "Операция заблокирована незавершённым предыдущим этапом",
};

export function formatPlanningDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  const parts = value.split("-");
  if (parts.length !== 3) {
    return value;
  }
  return `${parts[2]}.${parts[1]}.${parts[0]}`;
}

export function formatPlanningDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;
  const parts: string[] = [];
  if (hours > 0) {
    parts.push(`${hours} ч`);
  }
  if (minutes > 0) {
    parts.push(`${minutes} мин`);
  }
  if (remainingSeconds > 0 || parts.length === 0) {
    parts.push(`${remainingSeconds} сек`);
  }
  return parts.join(" ");
}

export function getPlanningIssueLabel(issueCode: string): string {
  return ISSUE_LABELS[issueCode] ?? `Ошибка данных: ${issueCode}`;
}

export function getPlanningForecastLabel(
  forecast: PlanningOrderForecast | undefined,
): string {
  if (!forecast) {
    return "—";
  }
  if (forecast.calculatedFinishDate) {
    return formatPlanningDate(forecast.calculatedFinishDate);
  }
  if (forecast.issueCodes.includes("outside_horizon")) {
    return ISSUE_LABELS.outside_horizon;
  }
  if (forecast.issueCodes.length > 0) {
    return getPlanningIssueLabel(forecast.issueCodes[0]);
  }
  return "Дата не рассчитана";
}
