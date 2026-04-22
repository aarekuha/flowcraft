import { apiFetch, createRequestError, handleJsonResponse } from "@/shared/api/http";

export type UserRole = "worker" | "brigadier" | "constructor" | "admin";

export type UserRecord = {
  id: number;
  name: string;
  phone: string;
  passwordHash: string | null;
  author: string | null;
  authorUserId: number | null;
  roles: UserRole[];
  isActive: boolean;
  createdAtTs: number | null;
  createdAt: string;
  updatedAtTs: number | null;
  updatedAt: string;
  deletedAtTs: number | null;
  isNew?: boolean;
};

export type UserCreatePayload = {
  name: string;
  phone: string;
  roles: UserRole[];
  is_active: boolean;
  author_user_id?: number | null;
};

export type UserUpdatePayload = UserCreatePayload;

type UserApi = {
  id: number;
  name: string;
  phone: string;
  password_hash: string | null;
  author: string | null;
  author_user_id: number | null;
  roles: UserRole[];
  is_active: boolean;
  created_at: number;
  updated_at: number;
  deleted_at: number | null;
};

export async function fetchUsers(): Promise<UserRecord[]> {
  const response = await apiFetch("/api/users");
  return handleJsonResponse<UserApi[]>(response).then((users) => users.map(mapUser));
}

export async function createUser(payload: UserCreatePayload): Promise<UserRecord> {
  const response = await apiFetch("/api/users", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<UserApi>(response).then(mapUser);
}

export async function updateUser(
  userId: number,
  payload: UserUpdatePayload,
): Promise<UserRecord> {
  const response = await apiFetch(`/api/users/${userId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<UserApi>(response).then(mapUser);
}

export async function updateUserStatus(
  userId: number,
  isActive: boolean,
): Promise<UserRecord> {
  const response = await apiFetch(`/api/users/${userId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_active: isActive }),
  });

  return handleJsonResponse<UserApi>(response).then(mapUser);
}

export async function resetUserPassword(userId: number): Promise<UserRecord> {
  const response = await apiFetch(`/api/users/${userId}/reset-password`, {
    method: "POST",
  });

  return handleJsonResponse<UserApi>(response).then(mapUser);
}

export async function deleteUser(userId: number): Promise<void> {
  const response = await apiFetch(`/api/users/${userId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw await createRequestError(response);
  }
}

function mapUser(user: UserApi): UserRecord {
  return {
    id: user.id,
    name: user.name,
    phone: user.phone,
    passwordHash: user.password_hash,
    author: user.author,
    authorUserId: user.author_user_id,
    roles: user.roles,
    isActive: user.is_active,
    createdAtTs: user.created_at,
    createdAt: formatDate(user.created_at),
    updatedAtTs: user.updated_at,
    updatedAt: formatDate(user.updated_at),
    deletedAtTs: user.deleted_at,
  };
}

function formatDate(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}
