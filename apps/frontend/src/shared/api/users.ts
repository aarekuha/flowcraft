import { apiFetch, createRequestError, handleJsonResponse } from "@/shared/api/http";

export type UserRole =
  | "worker"
  | "brigadier"
  | "constructor"
  | "quality_control"
  | "reports"
  | "admin";

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
  skillOperationCatalogEntryIds: number[];
  isNew?: boolean;
};

export type UserSkill = {
  operationCatalogEntryId: number;
  operationName: string;
  operationKind: "regular" | "cutting" | "adjacent";
  createdAt: number;
};

export type UserSkills = {
  userId: number;
  userName: string;
  skills: UserSkill[];
  totalCount: number;
  hiddenInactiveCount: number;
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
  skill_operation_catalog_entry_ids: number[];
};

type UserSkillApi = {
  operation_catalog_entry_id: number;
  operation_name: string;
  operation_kind: "regular" | "cutting" | "adjacent";
  created_at: number;
};

type UserSkillsApi = {
  user_id: number;
  user_name: string;
  skills: UserSkillApi[];
  total_count: number;
  hidden_inactive_count: number;
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

export async function fetchUserSkills(userId: number): Promise<UserSkills> {
  const response = await apiFetch(`/api/users/${userId}/skills`);
  return handleJsonResponse<UserSkillsApi>(response).then(mapUserSkills);
}

export async function addUserSkill(
  userId: number,
  operationCatalogEntryId: number,
): Promise<UserSkills> {
  const response = await apiFetch(`/api/users/${userId}/skills`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      operation_catalog_entry_id: operationCatalogEntryId,
    }),
  });
  return handleJsonResponse<UserSkillsApi>(response).then(mapUserSkills);
}

export async function removeUserSkill(
  userId: number,
  operationCatalogEntryId: number,
): Promise<UserSkills> {
  const response = await apiFetch(
    `/api/users/${userId}/skills/${operationCatalogEntryId}`,
    { method: "DELETE" },
  );
  return handleJsonResponse<UserSkillsApi>(response).then(mapUserSkills);
}

export async function copyUserSkills(
  targetUserId: number,
  sourceUserId: number,
): Promise<UserSkills> {
  const response = await apiFetch(`/api/users/${targetUserId}/skills/copy`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ source_user_id: sourceUserId }),
  });
  return handleJsonResponse<UserSkillsApi>(response).then(mapUserSkills);
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
    skillOperationCatalogEntryIds: [
      ...user.skill_operation_catalog_entry_ids,
    ],
  };
}

function mapUserSkills(value: UserSkillsApi): UserSkills {
  return {
    userId: value.user_id,
    userName: value.user_name,
    skills: value.skills.map((skill) => ({
      operationCatalogEntryId: skill.operation_catalog_entry_id,
      operationName: skill.operation_name,
      operationKind: skill.operation_kind,
      createdAt: skill.created_at,
    })),
    totalCount: value.total_count,
    hiddenInactiveCount: value.hidden_inactive_count,
  };
}

function formatDate(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}
