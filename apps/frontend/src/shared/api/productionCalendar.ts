import { apiFetch, handleJsonResponse } from "@/shared/api/http";

export type CalendarStatus = {
  imported_at: number | null;
  years: number[];
};

export type ProductionCalendarDay = {
  calendar_date: string;
  kind: string;
  is_working: boolean;
  is_holiday: boolean;
  is_shortened: boolean;
  name: string | null;
  transferred_from: string | null;
};

export type ProductionCalendarMonth = {
  imported_at: number;
  source: string;
  week_days: number;
  week_hours: number;
  summary: {
    year: number;
    month: number;
    calendar_days: number;
    working_days: number;
    non_working_days: number;
    holiday_days: number;
    shortened_days: number;
    working_hours: number;
  };
  days: ProductionCalendarDay[];
};

export async function fetchCalendarStatus(): Promise<CalendarStatus> {
  return handleJsonResponse<CalendarStatus>(await apiFetch("/api/planning/calendar"));
}

export async function refreshProductionCalendar(): Promise<CalendarStatus> {
  return handleJsonResponse<CalendarStatus>(await apiFetch(
    "/api/planning/calendar/refresh", { method: "POST" },
  ));
}
