export type PriorityPrintRow = readonly [number, string, string, string, number, string, string, string];

function escapeHtml(value: string | number): string {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]!);
}

export function buildPriorityPrintHtml(rows: readonly PriorityPrintRow[]): string {
  const headings = ["Приоритет", "Номер", "Наименование", "Вид кожи", "Количество изделий", "Стадия", "Плановая дата сдачи", "Расчётная дата готовности"];
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Приоритезация заказов</title>
<style>
@page { size: A4 landscape; margin: 10mm; }
body { margin: 0; font: 11px Arial, sans-serif; color: #000; }
h1 { font-size: 18px; margin: 0 0 12px; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th, td { border: 1px solid #777; padding: 6px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th { background: #eee; print-color-adjust: exact; }
th:nth-child(1) { width: 7%; } th:nth-child(2) { width: 9%; }
th:nth-child(3) { width: 21%; } th:nth-child(4) { width: 12%; }
th:nth-child(5) { width: 10%; } th:nth-child(6) { width: 9%; } th:nth-child(7) { width: 12%; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
</style></head><body><h1>Приоритезация заказов</h1><table><thead><tr>${headings.map(value => `<th>${escapeHtml(value)}</th>`).join("")}</tr></thead>
<tbody>${rows.map(row => `<tr>${row.map(value => `<td>${escapeHtml(value)}</td>`).join("")}</tr>`).join("")}</tbody></table></body></html>`;
}

export function printPriorityTable(rows: readonly PriorityPrintRow[], onError: () => void): void {
  const frame = document.createElement("iframe");
  frame.title = "Печать таблицы приоритетов";
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;left:-10000px;top:0;width:1100px;height:1px;border:0";
  frame.onload = () => {
    const target = frame.contentWindow;
    if (!target) { frame.remove(); onError(); return; }
    target.addEventListener("afterprint", () => frame.remove(), { once: true });
    try { target.focus(); target.print(); }
    catch { frame.remove(); onError(); }
  };
  frame.srcdoc = buildPriorityPrintHtml(rows);
  document.body.appendChild(frame);
}
