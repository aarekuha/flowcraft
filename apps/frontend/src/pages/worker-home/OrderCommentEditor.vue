<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchWorkOrder, updateWorkOrderComment } from "@/shared/api/orders";

const props = defineProps<{ orderId: number }>();
const comment = ref("");
const baseline = ref("");
const loading = ref(true);
const saving = ref(false);
const loaded = ref(false);
const error = ref("");
const notice = ref("");
function canClose() {
  if (saving.value) return false;
  return comment.value === baseline.value || window.confirm("Закрыть без сохранения комментария?");
}
defineExpose({ canClose });
onMounted(async () => {
  try {
    const order = await fetchWorkOrder(props.orderId);
    comment.value = order.comment ?? "";
    baseline.value = comment.value;
    loaded.value = true;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось загрузить комментарий"; }
  finally { loading.value = false; }
});
async function save() {
  if (!loaded.value || saving.value) return;
  saving.value = true; error.value = ""; notice.value = "";
  try {
    const order = await updateWorkOrderComment(props.orderId, comment.value.trim() || null);
    comment.value = order.comment ?? "";
    baseline.value = comment.value;
    notice.value = "Комментарий сохранён";
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось сохранить комментарий"; }
  finally { saving.value = false; }
}
</script>

<template>
  <section class="order-comment-editor">
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="loading">Загрузка комментария…</p>
    <label v-else-if="loaded">Комментарий заказа<textarea v-model="comment" :disabled="saving" maxlength="4000" rows="3" @input="notice = ''" /></label>
    <small>Этот комментарий выводится при печати заказа.</small>
    <div class="actions">
      <span v-if="notice" role="status">{{ notice }}</span>
      <button class="fc-button" type="button" :disabled="!loaded || saving || comment === baseline" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить комментарий' }}</button>
    </div>
  </section>
</template>

<style scoped>
.order-comment-editor { display: grid; gap: 8px; }
label { display: grid; gap: 8px; }
textarea { width: 100%; box-sizing: border-box; font: inherit; resize: vertical; padding: 10px; border: 1px solid #ccd6e1; border-radius: 8px; }
.actions { display: flex; gap: 12px; align-items: center; justify-content: flex-end; }
button { font: inherit; padding: 8px 12px; border: 1px solid #ccd6e1; background: white; border-radius: 8px; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
.error { color: #b13030; }
</style>
