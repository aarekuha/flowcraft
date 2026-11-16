import type { PlanningDay } from "../api/planningTimeline";

export function planningDayRows(data: PlanningDay, unassigned = "не назначен"): Array<Array<string | number>> {
  return data.items.map(item => [
    item.order_number,
    `${item.product_name} · ${item.product_version}`,
    item.leather_type_name ?? "—",
    item.quantity,
    item.operation_name,
    item.worker_names.length ? item.worker_names.join(", ") : unassigned,
  ]);
}

export type PlanningDaySortKey = "order_number" | "product_name" | "operation_name" | "worker_names";

export function sortPlanningDay(data: PlanningDay, key: PlanningDaySortKey, descending = false): PlanningDay {
  const collator = new Intl.Collator("ru", { numeric: true, sensitivity: "base" });
  const value = (item: PlanningDay["items"][number]) => key === "worker_names"
    ? item.worker_names.join(", ")
    : key === "product_name" ? `${item.product_name} · ${item.product_version}` : item[key];
  return { ...data, items: [...data.items].sort((a, b) => collator.compare(value(a), value(b)) * (descending ? -1 : 1)) };
}

export const planningDayHeadings = ["Номер заказа", "Наименование изделия", "Вид кожи", "Кол-во штук", "Операция", "Исполнитель"];

export function formatPlanningDay(value: string): string {
  return value.split("-").reverse().join(".");
}

function escapeHtml(value: string | number): string {
  return String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);
}

export function buildPlanningDayPrintHtml(data: PlanningDay): string {
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Операции на ${escapeHtml(formatPlanningDay(data.work_date))}</title><style>
@page { size: A4 landscape; margin: 10mm; }
body { font: 12px Arial, sans-serif; color: #000; margin: 0; }
h1 { font-size: 18px; margin: 0 0 12px; }
p { margin: 0 0 12px; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th, td { border: 1px solid #777; padding: 7px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th { background: #eee; print-color-adjust: exact; }
th:nth-child(1) { width: 10%; } th:nth-child(2) { width: 23%; } th:nth-child(3) { width: 13%; } th:nth-child(4) { width: 8%; } th:nth-child(5) { width: 22%; }
thead { display: table-header-group; } tr { break-inside: avoid; }
</style></head><body><h1>Операции на ${escapeHtml(formatPlanningDay(data.work_date))}</h1>
<p>Количество — число изделий в заказе. Исполнители — назначения в заказе.</p>
${data.calculation.is_stale ? "<p>Показан последний опубликованный расчёт; исходные данные изменились.</p>" : ""}
<table><thead><tr>${planningDayHeadings.map(value => `<th>${escapeHtml(value)}</th>`).join("")}</tr></thead><tbody>${planningDayRows(data, "").map(row => `<tr>${row.map(value => `<td>${escapeHtml(value)}</td>`).join("")}</tr>`).join("")}</tbody></table></body></html>`;
}

export function printPlanningDay(data: PlanningDay, onError: () => void): void {
  const frame = document.createElement("iframe");
  frame.title = "Печать операций на день";
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;left:-10000px;top:0;width:1100px;height:1px;border:0";
  frame.onload = () => {
    const target = frame.contentWindow;
    if (!target) { frame.remove(); onError(); return; }
    target.addEventListener("afterprint", () => frame.remove(), { once: true });
    try { target.focus(); target.print(); }
    catch { frame.remove(); onError(); }
  };
  frame.srcdoc = buildPlanningDayPrintHtml(data);
  document.body.appendChild(frame);
}
