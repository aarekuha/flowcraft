import { apiFetch, handleJsonResponse, createRequestError } from "@/shared/api/http";

export type Bonus = { id: number; name: string; amount_cents: number };
export type WorkReport = {
  user_id: number; user_name: string; year: number; month: number;
  work_days: number; work_hours: string; sick_days: number;
  vacation_days: number; absence_days: number;
  items: Array<{
    order_id: number; order_number: string; completed_at: number;
    product_name: string; product_version: string; operation_id: number | null;
    operation_name: string; quantity: string; price_cents: number | null;
    amount_cents: number | null;
  }>;
  total_quantity: string; piecework_cents: number;
  manual_piecework_cents: number | null; payable_piecework_cents: number;
  bonuses: Array<Bonus & { selected: boolean }>; bonuses_cents: number; payout_cents: number;
};

export async function getBonuses(userId?: number): Promise<Bonus[]> {
  return handleJsonResponse(await apiFetch(userId === undefined
    ? "/api/admin/bonuses" : `/api/admin/users/${userId}/bonuses`));
}
export async function saveBonus(bonus: { id?: number; name: string; amount_cents: number }): Promise<Bonus> {
  return handleJsonResponse(await apiFetch(`/api/admin/bonuses${bonus.id ? `/${bonus.id}` : ""}`, {
    method: bonus.id ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: bonus.name, amount_cents: bonus.amount_cents }),
  }));
}
export async function deleteBonus(id: number): Promise<void> {
  const response = await apiFetch(`/api/admin/bonuses/${id}`, { method: "DELETE" });
  if (!response.ok) throw await createRequestError(response);
}
export async function assignBonuses(userId: number, bonusIds: number[]): Promise<Bonus[]> {
  return handleJsonResponse(await apiFetch(`/api/admin/users/${userId}/bonuses`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bonus_ids: bonusIds }),
  }));
}
export async function getWorkReport(userId: number, year: number, month: number): Promise<WorkReport> {
  return handleJsonResponse(await apiFetch(`/api/admin/users/${userId}/completed-work?year=${year}&month=${month}`));
}
export async function downloadWorkReport(userId: number, year: number, month: number): Promise<void> {
  const response = await apiFetch(`/api/admin/users/${userId}/completed-work.xlsx?year=${year}&month=${month}`);
  if (!response.ok) throw await createRequestError(response);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `completed-work-${userId}-${year}-${String(month).padStart(2, "0")}.xlsx`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function money(cents: number | null): string {
  return cents === null ? "Не рассчитано" : (cents / 100).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export async function setMonthlyBonusSelection(
  userId: number, year: number, month: number, bonusId: number, selected: boolean,
): Promise<WorkReport> {
  return handleJsonResponse(await apiFetch(
    `/api/admin/users/${userId}/completed-work/bonuses/${bonusId}?year=${year}&month=${month}`,
    {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected }),
    },
  ));
}

export type PersonalWorkReport = Omit<WorkReport, "bonuses" | "bonuses_cents" | "payout_cents">;

export async function unlockPersonalWorkReport(password: string): Promise<{ token: string; expires_at: number }> {
  return handleJsonResponse(await apiFetch("/api/worker/completed-work/unlock", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  }));
}
export async function getPersonalWorkReport(token: string, year: number, month: number): Promise<PersonalWorkReport> {
  return handleJsonResponse(await apiFetch(`/api/worker/completed-work?year=${year}&month=${month}`, {
    headers: { "X-Work-Report-Token": token }, cache: "no-store",
  }));
}

export type WorkSummary = {
  year: number; month: number;
  items: Array<{
    user_id: number; user_name: string; sick_days: number; vacation_days: number;
    piecework_cents: number; bonuses_cents: number; incomplete: boolean;
  }>;
};
export async function getWorkSummary(year: number, month: number): Promise<WorkSummary> {
  return handleJsonResponse(await apiFetch(`/api/admin/completed-work-summary?year=${year}&month=${month}`));
}
export async function downloadWorkSummary(year: number, month: number): Promise<void> {
  const response = await apiFetch(`/api/admin/completed-work-summary.xlsx?year=${year}&month=${month}`);
  if (!response.ok) throw await createRequestError(response);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `completed-work-summary-${year}-${String(month).padStart(2, "0")}.xlsx`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function setMonthlyPiecework(
  userId: number, year: number, month: number, amountCents: number | null,
): Promise<WorkReport> {
  return handleJsonResponse(await apiFetch(
    `/api/admin/users/${userId}/completed-work/piecework?year=${year}&month=${month}`,
    { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount_cents: amountCents }) },
  ));
}
