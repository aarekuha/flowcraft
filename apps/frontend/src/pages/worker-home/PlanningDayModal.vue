<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { vEscapeClose } from "./escapeClose";
import { fetchPlanningDay, type PlanningDay } from "@/shared/api/planningTimeline";
import { formatPlanningDay, planningDayHeadings, planningDayRows, printPlanningDay, sortPlanningDay, type PlanningDaySortKey } from "@/shared/lib/planningDayPrint";

const props = defineProps<{ workDate: string }>();
const emit = defineEmits<{ close: [] }>();
const selectedDate = ref(props.workDate);
const data = ref<PlanningDay | null>(null);
const sortKey = ref<PlanningDaySortKey | null>(null);
const descending = ref(false);
const sortColumns: Array<PlanningDaySortKey | null> = ["order_number", "product_name", null, null, "operation_name", "worker_names"];
const displayedData = computed(() => data.value && sortKey.value ? sortPlanningDay(data.value, sortKey.value, descending.value) : data.value);
const rows = computed(() => displayedData.value ? planningDayRows(displayedData.value) : []);
function sort(column: number) {
  const key = sortColumns[column];
  if (!key) return;
  descending.value = sortKey.value === key ? !descending.value : false;
  sortKey.value = key;
}
const loading = ref(false);
const error = ref("");
let requestId = 0;
async function load() {
  const id = ++requestId;
  data.value = null;
  error.value = "";
  loading.value = false;
  if (!selectedDate.value) return;
  loading.value = true;
  try {
    const result = await fetchPlanningDay(selectedDate.value);
    if (id === requestId) data.value = result;
  } catch (cause) {
    if (id === requestId) error.value = cause instanceof Error ? cause.message : "Не удалось загрузить операции";
  } finally { if (id === requestId) loading.value = false; }
}
function print() {
  if (displayedData.value && !loading.value && displayedData.value.items.length) printPlanningDay(displayedData.value, () => { error.value = "Не удалось открыть печать"; });
}
watch(selectedDate, load, { immediate: true });
onBeforeUnmount(() => { requestId++; });
</script>

<template>
  <Teleport to="body">
    <div class="day-backdrop" @click.self="emit('close')">
      <section v-escape-close="() => emit('close')" class="day-modal card-shell" role="dialog" aria-modal="true" aria-labelledby="planning-day-title">
        <header class="day-head card-heading"><h2 id="planning-day-title">Операции на {{ selectedDate ? formatPlanningDay(selectedDate) : 'день' }}</h2><button type="button" class="fc-button fc-button--ghost" @click="emit('close')">Закрыть</button></header>
        <div class="card-scroll">
          <div class="day-controls"><label>День<input v-model="selectedDate" type="date" required></label><button type="button" class="fc-button" :disabled="loading || !selectedDate" @click="load">Обновить</button></div>
          <p class="hint">Количество — число изделий в заказе. Исполнители — назначения в заказе.</p>
          <p v-if="error" class="message error" role="alert">{{ error }}</p>
          <p v-if="loading" class="message" role="status">Загрузка операций…</p>
          <template v-else-if="data">
            <p v-if="data.calculation.is_stale && data.calculation.active_run_id !== null" class="message">Показан последний опубликованный расчёт; исходные данные изменились.</p>
            <p v-if="data.calculation.active_run_id === null" class="message">Расчёт ещё не опубликован.</p>
            <p v-else-if="!rows.length" class="message">На выбранный день операций не запланировано.</p>
            <div v-else class="day-table"><table><thead><tr><th v-for="(heading, column) in planningDayHeadings" :key="heading" :aria-sort="sortColumns[column] ? (sortKey === sortColumns[column] ? (descending ? 'descending' : 'ascending') : 'none') : undefined"><button v-if="sortColumns[column]" type="button" class="sort-heading" @click="sort(column)">{{ heading }} <span aria-hidden="true">{{ sortKey === sortColumns[column] ? (descending ? '↓' : '↑') : '↕' }}</span></button><template v-else>{{ heading }}</template></th></tr></thead><tbody><tr v-for="(row, index) in rows" :key="`${displayedData!.items[index].order_id}:${displayedData!.items[index].operation_id}`"><td v-for="(value, column) in row" :key="column">{{ value }}</td></tr></tbody></table></div>
          </template>
        </div>
        <footer class="day-actions card-actions"><span>Строк: {{ rows.length }}</span><button type="button" class="fc-button fc-button--primary" :disabled="loading || !rows.length" @click="print">Распечатать</button><button type="button" class="fc-button" @click="emit('close')">Закрыть</button></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.day-backdrop { position: fixed; inset: 0; z-index: 150; display: grid; place-items: center; padding: 20px; background: #17212b88; }
.day-modal { width: min(1200px, 100%); background: white; color: #1f2a33; border-radius: 18px; padding: 22px; }
.day-head, .day-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h2 { margin: 0; font-size: 1.3rem; }
.day-head { margin-bottom: 18px; }
.day-actions { margin-top: 18px; justify-content: flex-end; }
.day-actions span { margin-right: auto; color: #5f6b76; }
.day-controls { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }
.day-controls label { display: grid; gap: 7px; font-size: .875rem; font-weight: 600; }
input { width: 11rem; min-height: 44px; border: 1px solid #d6dee6; border-radius: 10px; padding: 9px 12px; font: inherit; }
.hint { font-size: .875rem; color: #5f6b76; }
.message { background: #e3eff8; padding: 12px; border-radius: 10px; }
.error { color: #963b3b; background: #fbeaea; }
.day-table { overflow: auto; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { padding: 12px; text-align: left; border-bottom: 1px solid #d6dee6; }
.sort-heading { border: 0; background: transparent; color: inherit; font: inherit; font-weight: inherit; padding: 0; text-align: left; cursor: pointer; }
.sort-heading:hover { text-decoration: underline; }
th { background: #e3eff8; }
tbody tr:hover { background: #f0f5fa; }
</style>
