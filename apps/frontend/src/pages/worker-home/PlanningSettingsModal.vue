<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  fetchPlanningSettings,
  updatePlanningSettings,
} from "@/shared/api/planning";

const emit = defineEmits<{
  close: [];
}>();

const displayOffsetDays = ref(2);
const preparationHours = ref(1);
const horizonMonths = ref<1 | 3 | 6 | 12>(3);
const baseline = ref("");
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const closeConfirmationOpen = ref(false);

const signature = computed(() => JSON.stringify({
  displayOffsetDays: displayOffsetDays.value,
  preparationHours: preparationHours.value,
  horizonMonths: horizonMonths.value,
}));
const hasChanges = computed(
  () => !loading.value && signature.value !== baseline.value,
);
const formError = computed(() => {
  if (!Number.isInteger(displayOffsetDays.value) || displayOffsetDays.value < 0) {
    return "Смещение должно быть целым неотрицательным числом дней.";
  }
  if (
    !Number.isFinite(preparationHours.value)
    || preparationHours.value < 0
    || !Number.isInteger(preparationHours.value * 3600)
  ) {
    return "Время подготовки должно быть неотрицательным и задаваться с точностью до секунды.";
  }
  return "";
});

onMounted(() => {
  void loadSettings();
});

async function loadSettings() {
  loading.value = true;
  error.value = "";
  try {
    const settings = await fetchPlanningSettings();
    displayOffsetDays.value = settings.displayOffsetDays;
    preparationHours.value = settings.preparationSeconds / 3600;
    horizonMonths.value = settings.horizonMonths;
    baseline.value = signature.value;
  } catch (loadError) {
    error.value = getErrorMessage(loadError, "Не удалось загрузить настройки.");
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!hasChanges.value || formError.value || saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    const settings = await updatePlanningSettings({
      display_offset_days: displayOffsetDays.value,
      preparation_seconds: Math.round(preparationHours.value * 3600),
      horizon_months: horizonMonths.value,
    });
    displayOffsetDays.value = settings.displayOffsetDays;
    preparationHours.value = settings.preparationSeconds / 3600;
    horizonMonths.value = settings.horizonMonths;
    baseline.value = signature.value;
  } catch (saveError) {
    error.value = getErrorMessage(saveError, "Не удалось сохранить настройки.");
  } finally {
    saving.value = false;
  }
}

function requestClose() {
  if (saving.value) {
    return;
  }
  if (hasChanges.value) {
    closeConfirmationOpen.value = true;
    return;
  }
  emit("close");
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error && value.message ? value.message : fallback;
}
</script>

<template>
  <div class="planning-backdrop" @click.self="requestClose">
    <section class="planning-modal" role="dialog" aria-modal="true">
      <header class="planning-modal__head">
        <div>
          <p>Планирование производства</p>
          <h2>Настройки расчёта</h2>
        </div>
        <button type="button" class="planning-button" @click="requestClose">
          Закрыть
        </button>
      </header>

      <p v-if="error" class="planning-message planning-message--error">{{ error }}</p>
      <p v-if="loading" class="planning-message">Загрузка настроек...</p>

      <div v-else class="planning-fields">
        <label>
          <span>Смещение отображаемой даты, дней</span>
          <input
            v-model.number="displayOffsetDays"
            type="number"
            min="0"
            step="1"
          />
          <small>Прибавляется только к показываемой расчётной дате.</small>
        </label>
        <label>
          <span>Подготовка каждой новой операции, часов</span>
          <input
            v-model.number="preparationHours"
            type="number"
            min="0"
            step="0.25"
          />
          <small>Начисляется один раз до начала операции.</small>
        </label>
        <label>
          <span>Горизонт расчёта</span>
          <select v-model.number="horizonMonths">
            <option :value="1">1 месяц</option>
            <option :value="3">3 месяца</option>
            <option :value="6">6 месяцев</option>
            <option :value="12">12 месяцев</option>
          </select>
        </label>
        <p v-if="formError" class="planning-message planning-message--error">
          {{ formError }}
        </p>
      </div>

      <footer class="planning-modal__actions">
        <span v-if="hasChanges">Есть несохранённые изменения</span>
        <button
          type="button"
          class="planning-button planning-button--primary"
          :disabled="!hasChanges || Boolean(formError) || saving"
          @click="save"
        >
          {{ saving ? "Сохранение..." : "Сохранить изменения" }}
        </button>
      </footer>

      <div v-if="closeConfirmationOpen" class="planning-confirm-backdrop">
        <section class="planning-confirm" role="alertdialog" aria-modal="true">
          <h3>Закрыть без сохранения?</h3>
          <p>Изменённые настройки будут потеряны.</p>
          <div>
            <button
              type="button"
              class="planning-button planning-button--danger"
              @click="emit('close')"
            >
              Закрыть без сохранения
            </button>
            <button
              type="button"
              class="planning-button"
              @click="closeConfirmationOpen = false"
            >
              Продолжить редактирование
            </button>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
.planning-backdrop,
.planning-confirm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 135;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(23, 31, 42, 0.58);
}

.planning-modal {
  position: relative;
  width: min(640px, 94vw);
  padding: 24px;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(15, 27, 39, 0.28);
  color: #1f2a33;
}

.planning-modal__head,
.planning-modal__actions,
.planning-confirm > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.planning-modal__head p,
.planning-modal__head h2,
.planning-confirm h3,
.planning-confirm p {
  margin: 0;
}

.planning-modal__head p,
.planning-modal__actions span,
.planning-fields small {
  color: #65727d;
}

.planning-fields {
  display: grid;
  gap: 16px;
  margin: 22px 0;
}

.planning-fields label {
  display: grid;
  gap: 7px;
  font-weight: 650;
}

.planning-fields input,
.planning-fields select {
  min-height: 44px;
  padding: 9px 11px;
  border: 1px solid #c7d1da;
  border-radius: 9px;
  background: #fff;
  font: inherit;
}

.planning-button {
  min-height: 44px;
  padding: 9px 15px;
  border: 1px solid #c7d1da;
  border-radius: 9px;
  background: #fff;
  color: #263746;
  cursor: pointer;
}

.planning-button--primary {
  border-color: #2f6ea3;
  background: #2f6ea3;
  color: #fff;
}

.planning-button--danger {
  color: #8e2f2f;
  border-color: #a94444;
}

.planning-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.planning-message {
  padding: 12px;
  border-radius: 9px;
  background: #eef3f7;
  color: #5f6b76;
}

.planning-message--error {
  background: #fbeaea;
  color: #8e2f2f;
}

.planning-confirm-backdrop {
  z-index: 140;
  border-radius: 18px;
}

.planning-confirm {
  width: min(480px, 90vw);
  padding: 22px;
  border-radius: 14px;
  background: #fff;
}

.planning-confirm p {
  margin: 10px 0 18px;
  color: #65727d;
}

@media (max-width: 600px) {
  .planning-modal__head,
  .planning-modal__actions,
  .planning-confirm > div {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
