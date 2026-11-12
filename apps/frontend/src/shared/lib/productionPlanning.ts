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

const ISSUE_HINTS: Record<string, string> = {
  no_skilled_worker: "Нет активного, неудалённого сотрудника с ролью «Исполнитель» и навыком этой операции. Проверить активность, роль и навыки сотрудников. Назначение на конкретный заказ для прогноза не требуется.",
  no_assignment: "Сообщение прежнего алгоритма: на операцию не назначен исполнитель. В версии 0.21 прогноз не зависит от назначений на заказ. Выполнить новый расчёт.",
  no_skilled_assignee: "Сообщение прежнего алгоритма: у назначенных сотрудников нет навыка операции. В версии 0.21 учитываются все активные исполнители с подходящим навыком независимо от назначений. Выполнить новый расчёт.",
  no_schedule: "У подходящих исполнителей нет доступных рабочих часов от возможного начала операции до конца периода расчёта. Проверить графики на нужные даты. Больничные, отпуска и прогулы не дают рабочих часов; уже использованное сегодня время вычитается.",
  outside_horizon: "Рабочие часы есть, но операция целиком не помещается в период расчёта с учётом загрузки другими заказами и времени подготовки. Проверить загрузку, приоритеты и длительность операций; при необходимости увеличить горизонт расчёта.",
  missing_standard_time: "Для операции не определено время выполнения. Указать нормативное время вручную либо проверить статистику. Текущий алгоритм при отсутствии ручной нормы и статистики выводит «Недостаточно статистики для расчёта времени операции».",
  insufficient_statistics: "Ручная норма не задана, а статистического времени нет. Для статистики нужны данные минимум по 5 изделиям из выполненных заказов с учтённым временем этой операции. Указать нормативное время вручную либо проверить выполненные заказы и списанное время.",
  no_operations: "После отбора не осталось операций для расчёта. Проверить дерево изделия: учитываются конечные операции, а для заказа «В работе» операции кроя исключаются.",
  blocked_by_stage: "Не удалось определить завершение предыдущего этапа, поэтому следующую операцию нельзя поставить в план. Это не требование сначала выполнить предыдущий этап фактически: планировщик рассчитывает и будущие этапы. Найти первичную проблему у операций предыдущего этапа — время, навыки, график или нехватку периода расчёта.",
};

export function getPlanningIssueHint(issueCode: string): string {
  return ISSUE_HINTS[issueCode]
    ?? `Получен неизвестный интерфейсу код причины «${issueCode}». Требуется техническая проверка результата расчёта.`;
}

export function getPlanningForecastHint(
  forecast: PlanningOrderForecast | undefined,
): string | undefined {
  if (!forecast) {
    return "Результат планирования для этого заказа отсутствует. Выполнить расчёт по кнопке «Пересчитать».";
  }
  if (forecast.calculatedFinishDate) {
    return undefined;
  }
  const issueCode = forecast.issueCodes.includes("outside_horizon")
    ? "outside_horizon" : forecast.issueCodes[0];
  return issueCode
    ? getPlanningIssueHint(issueCode)
    : "Дата готовности отсутствует, но конкретная причина в результате не указана. Выполнить повторный расчёт; если дата не появилась, требуется техническая проверка.";
}

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
