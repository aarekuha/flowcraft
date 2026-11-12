<script setup lang="ts">
import { onMounted, ref, computed } from "vue";

import {
  fetchPlanningQueue,
  reorderPlanningQueue,
  type PlanningQueueItem,
  type PlanningQueueStage,
  type PlanningOrderForecast,
} from "@/shared/api/planning";
import { ApiRequestError } from "@/shared/api/http";
import {
  getPlanningQueueNeighbors,
  movePlanningQueueItem,
} from "@/shared/lib/planningQueue";

import { getPlanningForecastLabel } from "@/shared/lib/productionPlanning";

const props = defineProps<{ forecasts: PlanningOrderForecast[] }>();
const emit = defineEmits<{ reordered: [] }>();
const forecastsByOrderId = computed(() => new Map(
  props.forecasts.map((forecast) => [forecast.orderId, forecast]),
));
function forecastLabel(orderId: number): string {
  const forecast = forecastsByOrderId.value.get(orderId);
  return forecast ? getPlanningForecastLabel(forecast) : "Не рассчитано";
}

const items = ref<PlanningQueueItem[]>([]);
const revision = ref(0);
const priorityDrafts = ref<Record<number, string>>({});
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const draggingOrderId = ref<number | null>(null);
const dragOriginalItems = ref<PlanningQueueItem[]>([]);
const dropInProgress = ref(false);

onMounted(() => {
  void loadQueue();
});

async function loadQueue() {
  loading.value = true;
  error.value = "";
  try {
    applyQueue(await fetchPlanningQueue());
  } catch (loadError) {
    error.value = getErrorMessage(loadError, "Не удалось загрузить очередь заказов.");
  } finally {
    loading.value = false;
  }
}

function applyQueue(queue: { revision: number; items: PlanningQueueItem[] }) {
  revision.value = queue.revision;
  items.value = queue.items;
  priorityDrafts.value = Object.fromEntries(
    queue.items.map((item) => [item.orderId, String(item.position)]),
  );
}

function startDrag(item: PlanningQueueItem, event: DragEvent) {
  if (saving.value) {
    event.preventDefault();
    return;
  }
  draggingOrderId.value = item.orderId;
  dragOriginalItems.value = items.value.map((queueItem) => ({ ...queueItem }));
  dropInProgress.value = false;
  notice.value = "";
  event.dataTransfer?.setData("text/plain", String(item.orderId));
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
  }
}

function dragOver(item: PlanningQueueItem, event: DragEvent) {
  const orderId = draggingOrderId.value;
  if (orderId === null || orderId === item.orderId || saving.value) {
    return;
  }
  const row = event.currentTarget;
  if (!(row instanceof HTMLElement)) {
    return;
  }
  const bounds = row.getBoundingClientRect();
  const placeAfter = event.clientY >= bounds.top + bounds.height / 2;
  items.value = movePlanningQueueItem(
    items.value,
    orderId,
    item.orderId,
    placeAfter,
  );
  syncPriorityDrafts();
}

async function dropItem() {
  const orderId = draggingOrderId.value;
  if (orderId === null || saving.value) {
    return;
  }
  dropInProgress.value = true;
  const neighbors = getPlanningQueueNeighbors(items.value, orderId);
  if (neighbors === null) {
    restoreDragSnapshot();
    return;
  }
  await saveReorder({
    order_id: orderId,
    expected_revision: revision.value,
    before_order_id: neighbors.beforeOrderId,
    after_order_id: neighbors.afterOrderId,
  });
  finishDrag();
}

function endDrag() {
  if (!dropInProgress.value) {
    restoreDragSnapshot();
  }
  finishDrag();
}

function restoreDragSnapshot() {
  if (dragOriginalItems.value.length > 0) {
    items.value = dragOriginalItems.value;
    syncPriorityDrafts();
  }
}

function finishDrag() {
  draggingOrderId.value = null;
  dragOriginalItems.value = [];
  dropInProgress.value = false;
}

async function saveManualPosition(item: PlanningQueueItem) {
  if (saving.value) {
    return;
  }
  const position = Number.parseInt(priorityDrafts.value[item.orderId] ?? "", 10);
  if (!Number.isInteger(position) || position < 1 || position > items.value.length) {
    error.value = `Приоритет должен быть числом от 1 до ${items.value.length}.`;
    priorityDrafts.value[item.orderId] = String(item.position);
    return;
  }
  if (position === item.position) {
    priorityDrafts.value[item.orderId] = String(item.position);
    return;
  }
  await saveReorder({
    order_id: item.orderId,
    expected_revision: revision.value,
    position,
  });
}

async function saveReorder(payload: {
  order_id: number;
  expected_revision: number;
  before_order_id?: number | null;
  after_order_id?: number | null;
  position?: number;
}) {
  saving.value = true;
  error.value = "";
  notice.value = "";
  try {
    applyQueue(await reorderPlanningQueue(payload));
    notice.value = "Приоритеты сохранены. Для обновления прогноза нажать «Пересчитать».";
    emit("reordered");
  } catch (saveError) {
    if (saveError instanceof ApiRequestError && saveError.status === 409) {
      notice.value =
        "Очередь была изменена другим пользователем. Показана актуальная версия.";
      await loadQueue();
      return;
    }
    const message = getErrorMessage(
      saveError,
      "Не удалось изменить приоритет заказа.",
    );
    await loadQueue();
    error.value = message;
  } finally {
    saving.value = false;
  }
}

function syncPriorityDrafts() {
  priorityDrafts.value = Object.fromEntries(
    items.value.map((item, index) => [item.orderId, String(index + 1)]),
  );
}

function getStageLabel(stage: PlanningQueueStage): string {
  const labels: Record<PlanningQueueStage, string> = {
    created: "Создан",
    cutting: "Крой",
    in_work: "В работе",
    quality_control: "ОТК",
  };
  return labels[stage];
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error && value.message ? value.message : fallback;
}
</script>

<template>
  <section class="priority-panel" aria-labelledby="planning-priority-title">
    <div class="priority-panel__head">
      <div>
        <h3 id="planning-priority-title">Приоритезация заказов</h3>
        <p>
          Перетащить заказ за маркер или указать его номер в общей очереди.
        </p>
      </div>
      <button
        type="button"
        class="priority-refresh"
        :disabled="loading || saving"
        @click="loadQueue"
      >
        Обновить
      </button>
    </div>

    <div v-if="error" class="priority-banner priority-banner--error">
      {{ error }}
    </div>
    <div v-if="notice" class="priority-banner priority-banner--notice">
      {{ notice }}
    </div>
    <div v-if="loading" class="priority-banner">Загрузка очереди...</div>
    <div v-else-if="items.length === 0" class="priority-empty">
      В очереди пока нет заказов.
    </div>
    <div v-else class="priority-table-wrap">
      <table class="priority-table">
        <thead>
          <tr>
            <th class="priority-table__drag-column" aria-label="Перемещение" />
            <th>Приоритет</th>
            <th>Номер</th>
            <th>Наименование</th>
            <th>Вид кожи</th>
            <th>Количество изделий</th>
            <th>Стадия</th>
            <th>Расчётная дата готовности</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.orderId"
            :class="{
              'priority-table__row--dragging': draggingOrderId === item.orderId,
            }"
            @dragover.prevent="dragOver(item, $event)"
            @drop.prevent="dropItem"
          >
            <td>
              <button
                type="button"
                class="priority-drag-handle"
                :disabled="saving"
                draggable="true"
                :aria-label="`Переместить заказ ${item.orderNumber}`"
                title="Потянуть для изменения приоритета"
                @dragstart="startDrag(item, $event)"
                @dragend="endDrag"
              >
                <span aria-hidden="true">☰</span>
              </button>
            </td>
            <td>
              <input
                v-model="priorityDrafts[item.orderId]"
                class="priority-input"
                type="number"
                min="1"
                :max="items.length"
                inputmode="numeric"
                :disabled="saving"
                :aria-label="`Приоритет заказа ${item.orderNumber}`"
                @change="saveManualPosition(item)"
                @keydown.enter.prevent="saveManualPosition(item)"
              />
            </td>
            <td>{{ item.orderNumber }}</td>
            <td>{{ item.productName }}</td>
            <td>{{ item.leatherTypeName ?? "—" }}</td>
            <td>{{ item.quantity }}</td>
            <td>
              <span class="priority-stage">{{ getStageLabel(item.stage) }}</span>
            </td>
            <td>{{ forecastLabel(item.orderId) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.priority-panel {
  display: grid;
  gap: 16px;
  margin-top: 18px;
}

.priority-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.priority-panel__head h3,
.priority-panel__head p {
  margin: 0;
}

.priority-panel__head p {
  margin-top: 6px;
  color: #6f6558;
}

.priority-refresh {
  min-height: 42px;
  padding: 8px 16px;
  border: 1px solid rgba(77, 57, 28, 0.2);
  border-radius: 10px;
  background: #fffaf3;
  color: #433622;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.priority-refresh:disabled,
.priority-drag-handle:disabled {
  cursor: wait;
  opacity: 0.55;
}

.priority-banner,
.priority-empty {
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(255, 250, 243, 0.92);
}

.priority-banner--error {
  color: #8f2525;
  background: #fff0f0;
}

.priority-banner--notice {
  color: #675117;
  background: #fff8d8;
}

.priority-table-wrap {
  overflow-x: auto;
  border: 1px solid rgba(77, 57, 28, 0.14);
  border-radius: 14px;
}

.priority-table {
  width: 100%;
  min-width: 920px;
  border-collapse: collapse;
  background: rgba(255, 255, 255, 0.72);
}

.priority-table th,
.priority-table td {
  padding: 12px 14px;
  border-bottom: 1px solid rgba(77, 57, 28, 0.1);
  text-align: left;
  vertical-align: middle;
}

.priority-table th {
  color: #6f6558;
  font-size: 0.82rem;
  text-transform: uppercase;
}

.priority-table tbody tr:last-child td {
  border-bottom: 0;
}

.priority-table__drag-column {
  width: 64px;
}

.priority-table__row--dragging {
  opacity: 0.45;
}

.priority-drag-handle {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border: 1px solid rgba(77, 57, 28, 0.18);
  border-radius: 12px;
  background: #fffaf3;
  color: #72582e;
  font-size: 1.45rem;
  cursor: grab;
  touch-action: none;
}

.priority-drag-handle:active {
  cursor: grabbing;
}

.priority-input {
  width: 84px;
  min-height: 42px;
  padding: 8px 10px;
  border: 1px solid rgba(77, 57, 28, 0.2);
  border-radius: 10px;
  background: #fff;
  color: inherit;
  font: inherit;
}

.priority-stage {
  display: inline-flex;
  padding: 5px 9px;
  border-radius: 999px;
  background: #efe6d8;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .priority-panel__head {
    flex-direction: column;
  }

  .priority-refresh {
    width: 100%;
  }
}
</style>
