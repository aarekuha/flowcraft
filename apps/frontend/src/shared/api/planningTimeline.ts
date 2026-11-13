import { apiFetch, handleJsonResponse } from "./http";

export type PlanningTimelineItem = {
  order_id: number;
  order_number: string;
  product_name: string;
  product_version: string;
  operation_id: number;
  operation_catalog_entry_id: number | null;
  operation_name: string;
  first_planned_date: string | null;
  last_planned_date: string | null;
  status: string;
  issue_codes: string[];
};

export type PlanningTimeline = {
  calculation: {
    active_run_id: number | null;
    active_completed_at: number | null;
    is_stale: boolean;
    calculation_status: string;
  };
  items: PlanningTimelineItem[];
};

export async function fetchPlanningTimeline(): Promise<PlanningTimeline> {
  return handleJsonResponse(await apiFetch("/api/planning/timeline"));
}
