const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

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

  try {
    const payload = await response.json();

    if (typeof payload?.detail === "string") {
      message = payload.detail;
    } else if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
      const firstError = payload.detail[0];
      if (typeof firstError?.msg === "string") {
        message = firstError.msg;
      }
    }
  } catch {
    // Ignore non-JSON responses and keep default message.
  }

  return new Error(message);
}
