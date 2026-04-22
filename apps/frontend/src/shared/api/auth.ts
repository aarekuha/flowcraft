import { apiFetch, handleJsonResponse } from "@/shared/api/http";

import type { UserRole } from "@/shared/api/users";

export type AuthSession = {
  userId: number;
  userName: string;
  userRoles: UserRole[];
  expiresAtTs: number;
  idleExpiresAtTs: number;
};

export type AuthLoginResult =
  | {
      status: "authenticated";
      session: AuthSession;
      userName: string | null;
    }
  | {
      status: "password_setup_required";
      session: null;
      userName: string | null;
    };

type AuthSessionApi = {
  user_id: number;
  user_name: string;
  user_roles: UserRole[];
  expires_at: number;
  idle_expires_at: number;
};

type AuthLoginResultApi = {
  status: "authenticated" | "password_setup_required";
  session: AuthSessionApi | null;
  user_name: string | null;
};

export async function fetchCurrentSession(): Promise<AuthSession> {
  const response = await apiFetch("/api/auth/me");
  return handleJsonResponse<AuthSessionApi>(response).then(mapSession);
}

export async function login(phone: string, password: string): Promise<AuthLoginResult> {
  const response = await apiFetch("/api/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      phone,
      password,
    }),
  });

  return handleJsonResponse<AuthLoginResultApi>(response).then((result) => ({
    status: result.status,
    session: result.session ? mapSession(result.session) : null,
    userName: result.user_name,
  })) as Promise<AuthLoginResult>;
}

export async function setupPassword(phone: string, newPassword: string): Promise<AuthSession> {
  const response = await apiFetch("/api/auth/setup-password", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      phone,
      new_password: newPassword,
    }),
  });

  return handleJsonResponse<AuthSessionApi>(response).then(mapSession);
}

export async function changePassword(
  currentPassword: string | null,
  newPassword: string,
): Promise<AuthSession> {
  const response = await apiFetch("/api/auth/change-password", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });

  return handleJsonResponse<AuthSessionApi>(response).then(mapSession);
}

export async function logout(): Promise<void> {
  const response = await apiFetch("/api/auth/logout", {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
}

function mapSession(session: AuthSessionApi): AuthSession {
  return {
    userId: session.user_id,
    userName: session.user_name,
    userRoles: session.user_roles,
    expiresAtTs: session.expires_at,
    idleExpiresAtTs: session.idle_expires_at,
  };
}
