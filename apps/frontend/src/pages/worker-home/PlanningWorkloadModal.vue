<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

import {
  fetchPlanningWorkload,
  type PlanningWorkload,
} from "@/shared/api/planning";
import { formatPlanningDuration } from "@/shared/lib/productionPlanning";

const emit = defineEmits<{
  close: [];
}>();

const month = ref(getCurrentMonth());
const workload = ref<PlanningWorkload | null>(null);
const loading = ref(true);
const error = ref("");

onMounted(() => {
  void loadWorkload();
});

watch(month, () => {
  void loadWorkload();
});

async function loadWorkload() {
  loading.value = true;
  error.value = "";
  try {
    workload.value = await fetchPlanningWorkload(month.value);
  } catch (loadError) {
    error.value = getErrorMessage(
      loadError,
      "Не удалось загрузить загруженность операций.",
    );
  } finally {
    loading.value = false;
  }
}

function getCurrentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function close() {
  emit("close");
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error && value.message ? value.message : fallback;
}
</script>

<template>
  <div class="workload-backdrop" @click.self="close">
    <section
      class="workload-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="workload-modal-title"
    >
      <header class="workload-head">
        <div>
          <p>Планирование производства</p>
          <h2 id="workload-modal-title">Загрузка по операциям</h2>
        </div>
        <button type="button" class="workload-button" @click="close">
          Закрыть
        </button>
      </header>

      <div class="workload-toolbar">
        <label>
          <span>Месяц распределения</span>
          <input v-model="month" type="month" />
        </label>
        <button
          type="button"
          class="workload-button"
          :disabled="loading"
          @click="loadWorkload"
        >
          Обновить
        </button>
      </div>

      <p v-if="error" class="workload-message workload-message--error">
        {{ error }}
      </p>
      <p v-else-if="loading" class="workload-message">
        Загрузка распределения...
      </p>
      <p
        v-else-if="!workload || workload.activeRunId === null"
        class="workload-message"
      >
        Успешный расчёт ещё не опубликован.
      </p>
      <p
        v-else-if="workload.items.length === 0"
        class="workload-message"
      >
        В опубликованном расчёте нет операций.
      </p>

      <div v-else class="workload-table-wrap">
        <table class="workload-table">
          <thead>
            <tr>
              <th>Операция</th>
              <th>Запланировано в месяце</th>
              <th>Общий остаток</th>
              <th>Заказов</th>
              <th>Дефицит ресурса</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in workload.items" :key="`${item.operationCatalogEntryId}-${item.operationName}`">
              <td>{{ item.operationName }}</td>
              <td>{{ formatPlanningDuration(item.plannedSeconds) }}</td>
              <td>{{ formatPlanningDuration(item.remainingSeconds) }}</td>
              <td>{{ item.ordersCount }}</td>
              <td :class="{ 'workload-deficit': item.deficitSeconds > 0 }">
                {{ formatPlanningDuration(item.deficitSeconds) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="workload-note">
        Общий остаток относится ко всем текущим заказам. Запланированные часы
        показывают распределение выбранного месяца, а дефицит — объём, который
        не удалось разместить в установленном горизонте.
      </p>
    </section>
  </div>
</template>

<style scoped>
.workload-backdrop {
  position: fixed;
  inset: 0;
  z-index: 137;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(23, 31, 42, 0.58);
}

.workload-modal {
  width: min(980px, 96vw);
  max-height: calc(100dvh - 40px);
  overflow: auto;
  padding: 24px;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(15, 27, 39, 0.28);
  color: #1f2a33;
}

.workload-head,
.workload-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.workload-head p,
.workload-head h2 {
  margin: 0;
}

.workload-head p,
.workload-note {
  color: #65727d;
}

.workload-toolbar {
  justify-content: flex-start;
  margin-top: 20px;
}

.workload-toolbar label {
  display: grid;
  gap: 6px;
  font-weight: 650;
}

.workload-toolbar input,
.workload-button {
  min-height: 44px;
  padding: 9px 13px;
  border: 1px solid #c7d1da;
  border-radius: 9px;
  background: #fff;
  color: inherit;
  font: inherit;
}

.workload-button:not(:disabled) {
  cursor: pointer;
}

.workload-message {
  margin: 20px 0 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #eef3f6;
}

.workload-message--error {
  background: #fff0f0;
  color: #a12d2d;
}

.workload-table-wrap {
  margin-top: 20px;
  overflow: auto;
  border: 1px solid #dce4e9;
  border-radius: 12px;
}

.workload-table {
  width: 100%;
  border-collapse: collapse;
}

.workload-table th,
.workload-table td {
  padding: 12px 14px;
  border-bottom: 1px solid #e4eaee;
  text-align: left;
}

.workload-table th {
  background: #f2f6f8;
  white-space: nowrap;
}

.workload-deficit {
  color: #a12d2d;
  font-weight: 700;
}

.workload-note {
  margin: 16px 0 0;
  line-height: 1.45;
}

@media (max-width: 760px) {
  .workload-backdrop {
    align-items: start;
    padding: 12px;
  }

  .workload-modal {
    width: calc(100vw - 24px);
    max-height: calc(100dvh - 24px);
    padding: 18px;
  }

  .workload-head,
  .workload-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
