<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  fetchAllOperationCatalogEntries,
  type OperationCatalogEntry,
} from "@/shared/api/operationCatalog";
import {
  addUserSkill,
  copyUserSkills,
  fetchUserSkills,
  removeUserSkill,
  type UserRecord,
  type UserSkills,
} from "@/shared/api/users";
import { requiresSkillCopyConfirmation } from "@/shared/lib/userSkills";

const props = defineProps<{
  targetUser: UserRecord;
  users: UserRecord[];
}>();

const emit = defineEmits<{
  close: [];
  updated: [];
}>();

const skills = ref<UserSkills | null>(null);
const operations = ref<OperationCatalogEntry[]>([]);
const search = ref("");
const sourceUserId = ref("");
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const pendingCopySourceId = ref<number | null>(null);

const assignedOperationIds = computed(
  () => new Set(
    skills.value?.skills.map((skill) => skill.operationCatalogEntryId) ?? [],
  ),
);

const availableOperations = computed(() => {
  const query = search.value.trim().toLocaleLowerCase("ru-RU");
  return operations.value
    .filter(
      (operation) =>
        operation.isActive
        && !assignedOperationIds.value.has(operation.id)
        && (!query || operation.name.toLocaleLowerCase("ru-RU").includes(query)),
    )
    .sort((left, right) => left.name.localeCompare(right.name, "ru"));
});

const copySourceUsers = computed(() =>
  props.users
    .filter((user) => !user.isNew && user.id !== props.targetUser.id)
    .sort((left, right) => left.name.localeCompare(right.name, "ru")),
);

const pendingCopySource = computed(() =>
  copySourceUsers.value.find((user) => user.id === pendingCopySourceId.value) ?? null,
);

onMounted(() => {
  void loadData();
});

async function loadData() {
  loading.value = true;
  error.value = "";
  try {
    const [userSkills, catalog] = await Promise.all([
      fetchUserSkills(props.targetUser.id),
      fetchAllOperationCatalogEntries({
        includeInactive: false,
        sortDirection: "asc",
        pageSize: 100,
      }),
    ]);
    skills.value = userSkills;
    operations.value = catalog;
  } catch (loadError) {
    error.value = getErrorMessage(loadError, "Не удалось загрузить навыки.");
  } finally {
    loading.value = false;
  }
}

async function addSkill(operationCatalogEntryId: number) {
  if (saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    skills.value = await addUserSkill(
      props.targetUser.id,
      operationCatalogEntryId,
    );
    emit("updated");
  } catch (saveError) {
    error.value = getErrorMessage(saveError, "Не удалось добавить навык.");
  } finally {
    saving.value = false;
  }
}

async function removeSkill(operationCatalogEntryId: number) {
  if (saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    skills.value = await removeUserSkill(
      props.targetUser.id,
      operationCatalogEntryId,
    );
    emit("updated");
  } catch (saveError) {
    error.value = getErrorMessage(saveError, "Не удалось удалить навык.");
  } finally {
    saving.value = false;
  }
}

function requestCopy() {
  const parsedSourceId = Number.parseInt(sourceUserId.value, 10);
  if (Number.isNaN(parsedSourceId) || saving.value) {
    return;
  }
  if (requiresSkillCopyConfirmation(skills.value?.totalCount ?? 0)) {
    pendingCopySourceId.value = parsedSourceId;
    return;
  }
  void applyCopy(parsedSourceId);
}

function cancelCopy() {
  pendingCopySourceId.value = null;
}

async function confirmCopy() {
  if (pendingCopySourceId.value === null) {
    return;
  }
  await applyCopy(pendingCopySourceId.value);
}

async function applyCopy(copySourceUserId: number) {
  saving.value = true;
  error.value = "";
  try {
    skills.value = await copyUserSkills(
      props.targetUser.id,
      copySourceUserId,
    );
    pendingCopySourceId.value = null;
    emit("updated");
  } catch (saveError) {
    error.value = getErrorMessage(saveError, "Не удалось скопировать навыки.");
  } finally {
    saving.value = false;
  }
}

function close() {
  if (!saving.value) {
    emit("close");
  }
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error && value.message ? value.message : fallback;
}
</script>

<template>
  <div class="skills-backdrop" @click.self="close">
    <section class="skills-modal" role="dialog" aria-modal="true">
      <header class="skills-modal__head">
        <div>
          <p class="skills-modal__eyebrow">Пользователь</p>
          <h2>Навыки · {{ targetUser.name }}</h2>
        </div>
        <button type="button" class="skills-button skills-button--ghost" @click="close">
          Закрыть
        </button>
      </header>

      <p v-if="error" class="skills-message skills-message--error">{{ error }}</p>
      <p v-if="loading" class="skills-message">Загрузка навыков...</p>

      <template v-else-if="skills">
        <section class="skills-section">
          <div class="skills-section__head">
            <div>
              <h3>Назначенные навыки</h3>
              <p v-if="skills.hiddenInactiveCount > 0">
                Скрыто деактивированных навыков: {{ skills.hiddenInactiveCount }}
              </p>
            </div>
            <strong>{{ skills.totalCount }}</strong>
          </div>

          <div v-if="skills.skills.length" class="skills-list">
            <div
              v-for="skill in skills.skills"
              :key="skill.operationCatalogEntryId"
              class="skills-list__item"
            >
              <span>{{ skill.operationName }}</span>
              <button
                type="button"
                class="skills-button skills-button--danger"
                :disabled="saving"
                @click="removeSkill(skill.operationCatalogEntryId)"
              >
                Удалить
              </button>
            </div>
          </div>
          <p v-else class="skills-empty">Активные навыки не назначены.</p>
        </section>

        <section class="skills-section">
          <h3>Добавить навык</h3>
          <input
            v-model="search"
            type="search"
            class="skills-input"
            placeholder="Поиск операции"
          />
          <div v-if="availableOperations.length" class="skills-options">
            <button
              v-for="operation in availableOperations"
              :key="operation.id"
              type="button"
              class="skills-option"
              :disabled="saving"
              @click="addSkill(operation.id)"
            >
              <span>{{ operation.name }}</span>
              <span aria-hidden="true">+</span>
            </button>
          </div>
          <p v-else class="skills-empty">Подходящие активные операции не найдены.</p>
        </section>

        <section class="skills-section">
          <h3>Скопировать из другого пользователя</h3>
          <div class="skills-copy-row">
            <select v-model="sourceUserId" class="skills-input">
              <option value="">Выбрать пользователя</option>
              <option
                v-for="user in copySourceUsers"
                :key="user.id"
                :value="String(user.id)"
              >
                {{ user.name }}
              </option>
            </select>
            <button
              type="button"
              class="skills-button skills-button--primary"
              :disabled="!sourceUserId || saving"
              @click="requestCopy"
            >
              Скопировать
            </button>
          </div>
        </section>
      </template>

      <div v-if="pendingCopySource" class="skills-confirm-backdrop">
        <section class="skills-confirm" role="alertdialog" aria-modal="true">
          <h3>Заменить все навыки?</h3>
          <p>
            Текущие навыки пользователя будут удалены и заменены навыками
            пользователя «{{ pendingCopySource.name }}».
          </p>
          <div class="skills-confirm__actions">
            <button
              type="button"
              class="skills-button skills-button--primary"
              :disabled="saving"
              @click="confirmCopy"
            >
              Подтвердить замену
            </button>
            <button
              type="button"
              class="skills-button skills-button--ghost"
              :disabled="saving"
              @click="cancelCopy"
            >
              Отменить
            </button>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
.skills-backdrop,
.skills-confirm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(23, 31, 42, 0.54);
}

.skills-modal {
  position: relative;
  width: min(900px, 100%);
  max-height: min(880px, calc(100vh - 48px));
  overflow: auto;
  padding: 24px;
  border-radius: 22px;
  background: #fff;
  box-shadow: 0 24px 80px rgba(17, 28, 41, 0.24);
}

.skills-modal__head,
.skills-section__head,
.skills-copy-row,
.skills-confirm__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.skills-modal__head h2,
.skills-section h3,
.skills-confirm h3 {
  margin: 0;
}

.skills-modal__eyebrow,
.skills-section__head p {
  margin: 0 0 4px;
  color: #6b7580;
}

.skills-section {
  display: grid;
  gap: 14px;
  margin-top: 22px;
  padding-top: 22px;
  border-top: 1px solid #e5e9ed;
}

.skills-list,
.skills-options {
  display: grid;
  gap: 8px;
}

.skills-list__item,
.skills-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 48px;
  padding: 10px 14px;
  border: 1px solid #dce2e8;
  border-radius: 12px;
  background: #f8fafb;
}

.skills-option {
  width: 100%;
  color: #263542;
  cursor: pointer;
}

.skills-input {
  width: 100%;
  min-height: 46px;
  padding: 10px 12px;
  border: 1px solid #cfd7de;
  border-radius: 12px;
  background: #fff;
  font: inherit;
}

.skills-copy-row .skills-input {
  flex: 1;
}

.skills-button {
  min-height: 44px;
  padding: 9px 14px;
  border: 1px solid transparent;
  border-radius: 12px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.skills-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.skills-button--primary {
  background: #2f6ea3;
  color: #fff;
}

.skills-button--ghost {
  border-color: #cfd7de;
  background: #fff;
  color: #32414f;
}

.skills-button--danger {
  border-color: #e5b9b5;
  background: #fff5f4;
  color: #a33b34;
}

.skills-message,
.skills-empty {
  color: #687580;
}

.skills-message--error {
  padding: 12px 14px;
  border-radius: 12px;
  background: #fff0ee;
  color: #9a322d;
}

.skills-confirm-backdrop {
  position: absolute;
  z-index: 2;
  padding: 18px;
  border-radius: 22px;
}

.skills-confirm {
  width: min(520px, 100%);
  padding: 22px;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 18px 50px rgba(17, 28, 41, 0.26);
}

@media (max-width: 680px) {
  .skills-backdrop {
    padding: 8px;
  }

  .skills-modal {
    max-height: calc(100vh - 16px);
    padding: 18px;
    border-radius: 16px;
  }

  .skills-copy-row,
  .skills-confirm__actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
