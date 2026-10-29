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
  return fetch(buildApiUrl(path), {
    credentials: "include",
    ...init,
  });
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
