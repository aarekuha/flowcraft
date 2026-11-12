<script setup lang="ts">
import { onMounted, ref } from "vue";
import { assignBonuses, deleteBonus, getBonuses, money, saveBonus, type Bonus } from "@/shared/api/completedWork";

const props = defineProps<{ userId?: number }>();
defineEmits<{ close: [] }>();
const entries = ref<Bonus[]>([]);
const selected = ref<number[]>([]);
const busy = ref(false);
const loaded = ref(false);
const error = ref("");
const message = ref("");
const draft = ref({ id: undefined as number | undefined, name: "", amount: "" });

async function load() {
  busy.value = true;
  error.value = "";
  try {
    const [all, assigned] = await Promise.all([getBonuses(), props.userId === undefined ? Promise.resolve([]) : getBonuses(props.userId)]);
    entries.value = all;
    selected.value = assigned.map((bonus) => bonus.id);
    loaded.value = true;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось загрузить премии"; }
  finally { busy.value = false; }
}
async function act(action: () => Promise<unknown>) {
  busy.value = true;
  error.value = "";
  message.value = "";
  try { await action(); message.value = "Сохранено"; }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось сохранить премии"; }
  finally { busy.value = false; }
}
async function submit() {
  await act(async () => {
    await saveBonus({ id: draft.value.id, name: draft.value.name, amount_cents: Math.round(Number(draft.value.amount) * 100) });
    entries.value = await getBonuses();
    draft.value = { id: undefined, name: "", amount: "" };
  });
}
function edit(entry: Bonus) {
  draft.value = { id: entry.id, name: entry.name, amount: (entry.amount_cents / 100).toFixed(2) };
}
async function remove(entry: Bonus) {
  if (!window.confirm(`Удалить премию «${entry.name}» из справочника и назначений сотрудников?`)) return;
  await act(async () => {
    await deleteBonus(entry.id);
    entries.value = entries.value.filter((item) => item.id !== entry.id);
    if (draft.value.id === entry.id) draft.value = { id: undefined, name: "", amount: "" };
  });
}
onMounted(load);
</script>

<template>
  <section class="bonuses" :class="{ 'card-frame': userId !== undefined }">
    <div class="bonus-content" :class="{ 'card-scroll': userId !== undefined }">
      <h3>{{ userId === undefined ? 'Справочник премий' : 'Премии сотрудника' }}</h3>
      <p v-if="userId !== undefined">Назначенные премии включаются в расчёт выполненной работы по текущим размерам из справочника.</p>
      <p v-if="error" role="alert">{{ error }} <button :disabled="busy" @click="load">Повторить загрузку</button></p>
      <p v-if="message" role="status">{{ message }}</p>
      <p v-if="busy">Загрузка / сохранение…</p>
      <template v-if="loaded">
        <form v-if="userId === undefined" class="bonus-form" @submit.prevent="submit">
          <label>Наименование <input v-model="draft.name" required maxlength="255" :disabled="busy" /></label>
          <label>Размер, ₽ <input v-model="draft.amount" type="number" min="0" max="9999999.99" step="0.01" required :disabled="busy" /></label>
          <button :disabled="busy || !draft.name.trim()">{{ draft.id ? 'Сохранить' : 'Добавить строку' }}</button>
          <button v-if="draft.id" type="button" :disabled="busy" @click="draft = { id: undefined, name: '', amount: '' }">Отмена</button>
        </form>
        <table>
          <thead><tr><th v-if="userId !== undefined">Назначена</th><th>Наименование</th><th>Размер, ₽</th><th v-if="userId === undefined">Действия</th></tr></thead>
          <tbody><tr v-for="entry in entries" :key="entry.id">
          <td v-if="userId !== undefined"><input v-model="selected" type="checkbox" :value="entry.id" :disabled="busy" :aria-label="`Назначить премию ${entry.name}`" /></td>
          <td>{{ entry.name }}</td><td>{{ money(entry.amount_cents) }}</td>
          <td v-if="userId === undefined"><button :disabled="busy" @click="edit(entry)">Изменить</button> <button :disabled="busy" @click="remove(entry)">Удалить</button></td>
          </tr></tbody>
        </table>
        <p v-if="!entries.length">В справочнике пока нет премий.</p>

      </template>
    </div>
    <div v-if="loaded && userId !== undefined" class="bonus-actions card-actions">
      <button :disabled="busy" @click="act(() => assignBonuses(userId!, selected))">Сохранить назначения</button>
      <button type="button" :disabled="busy" @click="$emit('close')">Закрыть</button>
    </div>
  </section>
</template>

<style scoped>
.bonuses, .bonus-content { display: grid; gap: 16px; align-content: start; }
.bonus-actions { display: flex; flex-wrap: wrap; gap: 12px; }
.bonus-form { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; }
label { display: grid; gap: 6px; }
input, button { font: inherit; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 8px; }
button { cursor: pointer; background: #f1f5f9; color: #0f172a; }
button:disabled { opacity: .5; cursor: default; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 12px 8px; border-bottom: 1px solid #e2e8f0; }
[role="alert"] { color: #b91c1c; }
</style>
