import type { DiagnosticEvent } from "@/shared/lib/diagnostics";
import { diagnosticRequestPath, diagnosticUser, recordDiagnostic } from "@/shared/lib/diagnostics";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
  }
}

export function buildApiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const owner = diagnosticUser();
  const route = diagnosticRequestPath(path);
  const started = performance.now();
  const method = (init?.method ?? "GET").toUpperCase();
  try {
    const response = await fetch(buildApiUrl(path), { credentials: "include", ...init });
    if (route && ["GET", "POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      const requestId = response.headers.get("x-timer-request-id");
      recordDiagnostic({ kind: "request", path: route, method: method as DiagnosticEvent["method"], status: response.status,
        duration_ms: Math.round(performance.now() - started),
        ...(/^[a-f0-9]{32}$/.test(requestId ?? "") ? { request_id: requestId! } : {}),
      }, owner);
    }
    return response;
  } catch (error) {
    if (route) recordDiagnostic({ kind: "request", path: route, status: 0, duration_ms: Math.round(performance.now() - started) }, owner);
    throw error;
  }
}

export async function handleJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw await createRequestError(response);
  }

  return (await response.json()) as T;
}

export async function createRequestError(response: Response): Promise<Error> {
  let message = `Request failed with status ${response.status}`;
  let detail: unknown = null;

  try {
    const payload = await response.json();
    detail = payload?.detail;

    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail) && detail.length > 0) {
      const firstError = detail[0];
      if (typeof firstError?.msg === "string") {
        message = firstError.msg;
      }
    } else if (
      typeof detail === "object"
      && detail !== null
      && "message" in detail
      && typeof detail.message === "string"
    ) {
      message = detail.message;
    }
  } catch {
    // Ignore non-JSON responses and keep default message.
  }

  return new ApiRequestError(message, response.status, detail);
}
