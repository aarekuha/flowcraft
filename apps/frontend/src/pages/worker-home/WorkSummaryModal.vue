<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { downloadWorkSummary, getWorkSummary, money, type WorkSummary } from "@/shared/api/completedWork";

defineEmits<{ close: [] }>();
const today = new Date();
const year = ref(today.getFullYear());
const month = ref(today.getMonth() + 1);
const months = Array.from({ length: 12 }, (_, index) => new Date(2026, index, 1).toLocaleString("ru-RU", { month: "long" }));
const report = ref<WorkSummary | null>(null);
const loading = ref(false);
const printing = ref(false);
const error = ref("");
let requestId = 0;
const incomplete = computed(() => report.value?.items.some((item) => item.incomplete) ?? false);
async function load() {
  const current = ++requestId;
  report.value = null;
  error.value = "";
  if (!Number.isInteger(year.value) || year.value < 2000 || year.value > 9998) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const result = await getWorkSummary(year.value, month.value);
    if (current === requestId) report.value = result;
  } catch (cause) {
    if (current === requestId) error.value = cause instanceof Error ? cause.message : "Не удалось загрузить общий расчёт";
  } finally { if (current === requestId) loading.value = false; }
}
async function print() {
  if (!report.value || printing.value) return;
  printing.value = true;
  error.value = "";
  try { await downloadWorkSummary(report.value.year, report.value.month); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось скачать XLSX"; }
  finally { printing.value = false; }
}
watch([year, month], load, { immediate: true });
onUnmounted(() => { requestId += 1; });
</script>

<template>
  <div class="summary-overlay" @click.self="$emit('close')" @keydown.esc="$emit('close')">
    <section class="summary-dialog" role="dialog" aria-modal="true" aria-label="Общий расчёт выполненной работы" tabindex="-1">
      <header>
        <h2>Общий расчёт выполненной работы</h2>
        <button type="button" @click="$emit('close')">Закрыть</button>
      </header>
      <div class="controls">
        <label>Месяц <select v-model="month" :disabled="printing"><option v-for="(name, index) in months" :key="index" :value="index + 1">{{ name }}</option></select></label>
        <label>Год <input v-model.number="year" type="number" min="2000" max="9998" :disabled="printing" /></label>
        <button :disabled="loading || printing" @click="load">Пересчитать</button>
        <button :disabled="!report || loading || printing" @click="print">{{ printing ? 'Подготовка…' : 'Печать · XLSX' }}</button>
      </div>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="loading">Расчёт…</p>
      <p v-if="incomplete" role="alert">Расчёт неполный: требуется указать недостающие расценки операций.</p>
      <div v-if="report" class="table-scroll">
        <table>
          <thead><tr><th>ФИО</th><th>Сделка, ₽</th><th>Премии, ₽</th></tr></thead>
          <tbody>
            <tr v-for="item in report.items" :key="item.user_id">
              <td>{{ item.user_name }}</td><td>{{ money(item.piecework_cents) }}</td><td>{{ money(item.bonuses_cents) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!report.items.length">Нет текущих сотрудников.</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.summary-overlay { position: fixed; inset: 0; z-index: 120; display: grid; place-items: center; padding: 20px; background: #0f172a88; }
.summary-dialog { width: min(1000px, 100%); max-height: 92vh; overflow: auto; padding: 24px; box-sizing: border-box; border-radius: 18px; background: white; color: #0f172a; }
header, .controls { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
header { justify-content: space-between; }
input, select, button { padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font: inherit; }
input { width: 100px; } button { cursor: pointer; } button:disabled { opacity: .5; cursor: default; }
.table-scroll { overflow-x: auto; margin-top: 20px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px 8px; text-align: left; border-bottom: 1px solid #e2e8f0; }
[role="alert"] { color: #b91c1c; }
</style>
