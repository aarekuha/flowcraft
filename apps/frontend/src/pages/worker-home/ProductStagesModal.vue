<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { vEscapeClose } from "./escapeClose";

import {
  fetchProduct,
  updateProductStages,
  type OperationNode,
} from "@/shared/api/products";
import {
  moveProductOperation,
  removeProductStage,
  resizeProductOperation,
  resolveProductStageFromPointer,
} from "@/shared/lib/productStages";

type StageOperation = {
  id: number;
  name: string;
  operationKind: "regular" | "cutting" | "adjacent";
  stageStart: number;
  stageEnd: number;
};

const props = defineProps<{
  productId: number;
  productLabel: string;
}>();

const emit = defineEmits<{
  close: [];
  updated: [];
}>();

const productName = ref(props.productLabel);
const stageCount = ref(1);
const operations = ref<StageOperation[]>([]);
const baseline = ref("");
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const draggedOperationId = ref<number | null>(null);
const dragPointerOffsetX = ref(0);
const resizeState = ref<{
  operationId: number;
  boundary: "start" | "end";
  rowElement: HTMLElement;
  pointerOffsetX: number;
} | null>(null);
const closeConfirmationOpen = ref(false);
const pendingRemovedStage = ref<number | null>(null);

const stages = computed(() =>
  Array.from({ length: stageCount.value }, (_, index) => index + 1),
);
const currentSignature = computed(() => JSON.stringify({
  stageCount: stageCount.value,
  operations: operations.value.map((operation) => ({
    id: operation.id,
    stageStart: operation.stageStart,
    stageEnd: operation.stageEnd,
  })),
}));
const hasChanges = computed(
  () => !loading.value && currentSignature.value !== baseline.value,
);
const stageRemovalPreview = computed(() => {
  if (pendingRemovedStage.value === null) {
    return [];
  }
  const shiftedOperations = removeProductStage(
    operations.value,
    pendingRemovedStage.value,
    stageCount.value,
  );
  return operations.value.flatMap((operation, index) => {
    const shifted = shiftedOperations[index];
    if (
      operation.stageStart === shifted.stageStart
      && operation.stageEnd === shifted.stageEnd
    ) {
      return [];
    }
    return [{
      id: operation.id,
      name: operation.name,
      before: formatStageRange(operation.stageStart, operation.stageEnd),
      after: formatStageRange(shifted.stageStart, shifted.stageEnd),
    }];
  });
});

onMounted(() => {
  void loadProduct();
});

onBeforeUnmount(() => {
  stopResize();
});

async function loadProduct() {
  loading.value = true;
  error.value = "";
  try {
    const product = await fetchProduct(props.productId);
    productName.value = `${product.name} · ${product.version}`;
    stageCount.value = product.stageCount;
    operations.value = flattenLeafOperations(product.operations);
    baseline.value = currentSignature.value;
  } catch (loadError) {
    error.value = getErrorMessage(loadError, "Не удалось загрузить схему этапов.");
  } finally {
    loading.value = false;
  }
}

function flattenLeafOperations(
  nodes: OperationNode[],
  parentNames: string[] = [],
): StageOperation[] {
  return nodes.flatMap((operation) => {
    if (operation.children.length > 0) {
      return flattenLeafOperations(
        operation.children,
        [...parentNames, operation.name],
      );
    }
    return [{
      id: operation.id,
      name: [...parentNames, operation.name].join(" / "),
      operationKind: operation.operationKind ?? "regular",
      stageStart: operation.stageStart,
      stageEnd: operation.stageEnd,
    }];
  });
}

function addStage() {
  stageCount.value += 1;
}

function requestRemoveStage(stage: number) {
  if (stageCount.value <= 1) {
    return;
  }
  pendingRemovedStage.value = stage;
}

function cancelRemoveStage() {
  pendingRemovedStage.value = null;
}

function confirmRemoveStage() {
  const stage = pendingRemovedStage.value;
  if (stage === null || stageCount.value <= 1) {
    return;
  }
  operations.value = removeProductStage(
    operations.value,
    stage,
    stageCount.value,
  );
  stageCount.value -= 1;
  pendingRemovedStage.value = null;
}

function formatStageRange(stageStart: number, stageEnd: number): string {
  return stageStart === stageEnd
    ? `этап ${stageStart}`
    : `этапы ${stageStart}–${stageEnd}`;
}

function startDrag(operationId: number, event: DragEvent) {
  if (resizeState.value !== null) {
    event.preventDefault();
    return;
  }
  const operationElement = event.currentTarget;
  if (!(operationElement instanceof HTMLElement)) {
    return;
  }
  const operationBounds = operationElement.getBoundingClientRect();
  draggedOperationId.value = operationId;
  dragPointerOffsetX.value = Math.max(
    0,
    Math.min(event.clientX - operationBounds.left, operationBounds.width),
  );
  event.dataTransfer?.setData("text/plain", String(operationId));
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
  }
}

function stopDrag() {
  draggedOperationId.value = null;
  dragPointerOffsetX.value = 0;
}

function dropOperation(event: DragEvent) {
  event.preventDefault();
  const rowElement = event.currentTarget;
  if (!(rowElement instanceof HTMLElement)) {
    return;
  }
  const operationId = draggedOperationId.value;
  if (operationId === null) {
    return;
  }
  operations.value = moveProductOperation(
    operations.value,
    operationId,
    getStageFromPointer(
      rowElement,
      event.clientX,
      dragPointerOffsetX.value,
      "start",
    ),
    stageCount.value,
  );
  stopDrag();
}

function startResize(
  operation: StageOperation,
  boundary: "start" | "end",
  event: PointerEvent,
) {
  if (operation.operationKind !== "adjacent") {
    return;
  }
  const handle = event.currentTarget;
  if (!(handle instanceof HTMLElement)) {
    return;
  }
  const rowElement = handle.closest<HTMLElement>(".stages-grid__row");
  const operationElement = handle.closest<HTMLElement>(
    ".stages-grid__operation",
  );
  if (rowElement === null || operationElement === null) {
    return;
  }
  const operationBounds = operationElement.getBoundingClientRect();
  const boundaryX = boundary === "start"
    ? operationBounds.left
    : operationBounds.right;
  event.preventDefault();
  resizeState.value = {
    operationId: operation.id,
    boundary,
    rowElement,
    pointerOffsetX: event.clientX - boundaryX,
  };
  window.addEventListener("pointermove", handleResize);
  window.addEventListener("pointerup", stopResize, { once: true });
}

function handleResize(event: PointerEvent) {
  const state = resizeState.value;
  if (state === null) {
    return;
  }
  operations.value = resizeProductOperation(
    operations.value,
    state.operationId,
    state.boundary,
    getStageFromPointer(
      state.rowElement,
      event.clientX,
      state.pointerOffsetX,
      state.boundary,
    ),
  );
}

function stopResize() {
  window.removeEventListener("pointermove", handleResize);
  window.removeEventListener("pointerup", stopResize);
  resizeState.value = null;
}

function getStageFromPointer(
  rowElement: HTMLElement,
  clientX: number,
  pointerOffsetX: number,
  boundary: "start" | "end",
): number {
  const cellBounds = Array.from(
    rowElement.querySelectorAll<HTMLElement>("[data-stage-cell]"),
  ).flatMap((cell) => {
    const stage = Number(cell.dataset.stageCell);
    if (!Number.isInteger(stage)) {
      return [];
    }
    const bounds = cell.getBoundingClientRect();
    return [{ stage, left: bounds.left, right: bounds.right }];
  });
  return resolveProductStageFromPointer(
    cellBounds,
    clientX,
    pointerOffsetX,
    boundary,
  );
}

function getGridStyle(): Record<string, string> {
  return {
    gridTemplateColumns: `220px repeat(${stageCount.value}, minmax(150px, 1fr))`,
    minWidth: `${220 + stageCount.value * 150}px`,
  };
}

function getOperationStyle(operation: StageOperation): Record<string, string> {
  const hue = Math.round((operation.id * 137.508) % 360);
  return {
    gridColumn: `${operation.stageStart + 1} / ${operation.stageEnd + 2}`,
    backgroundColor: `hsl(${hue} 58% 78%)`,
    borderColor: `hsl(${hue} 42% 48%)`,
  };
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

function discardChanges() {
  closeConfirmationOpen.value = false;
  emit("close");
}

async function save() {
  if (!hasChanges.value || saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await updateProductStages(props.productId, {
      stage_count: stageCount.value,
      operations: operations.value.map((operation) => ({
        operation_id: operation.id,
        stage_start: operation.stageStart,
        stage_end: operation.stageEnd,
      })),
    });
    baseline.value = currentSignature.value;
    emit("updated");
  } catch (saveError) {
    error.value = getErrorMessage(saveError, "Не удалось сохранить схему этапов.");
  } finally {
    saving.value = false;
  }
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error && value.message ? value.message : fallback;
}
</script>

<template>
  <div class="stages-backdrop" @click.self="requestClose">
    <section v-escape-close="requestClose" class="stages-modal card-shell" role="dialog" aria-modal="true">
      <header class="stages-modal__head card-heading">
        <div>
          <p class="stages-modal__eyebrow">Технологическая схема</p>
          <h2>Этапы · {{ productName }}</h2>
        </div>
        <button type="button" class="stages-button fc-button" @click="requestClose">
          Закрыть
        </button>
      </header>
      <div class="card-scroll">

        <p v-if="error" class="stages-message stages-message--error">{{ error }}</p>
        <p v-if="loading" class="stages-message">Загрузка схемы этапов...</p>

        <template v-else>
          <div class="stages-toolbar">
            <p>
            Перетаскивание перемещает операцию между этапами. Боковые маркеры
            растягивают смежную операцию на несколько этапов.
            </p>
            <button
              type="button"
              class="stages-button stages-button--primary fc-button fc-button--primary"
              @click="addStage"
            >
            + Добавить этап
            </button>
          </div>

          <div class="stages-grid-wrap">
            <div class="stages-grid__head" :style="getGridStyle()">
              <strong class="stages-grid__operation-title" style="grid-column: 1">
              Операция
              </strong>
              <div
                v-for="stage in stages"
                :key="stage"
                class="stages-grid__stage-title"
                :style="{ gridColumn: String(stage + 1) }"
              >
                <strong>Этап {{ stage }}</strong>
                <button
                  type="button"
                  class="stages-grid__delete-stage"
                  :disabled="stageCount === 1"
                  :aria-label="`Удалить этап ${stage}`"
                  @click="requestRemoveStage(stage)"
                >
                ×
                </button>
              </div>
            </div>

            <div
              v-for="operation in operations"
              :key="operation.id"
              class="stages-grid__row"
              :style="getGridStyle()"
              :data-operation-id="operation.id"
              @dragover.prevent
              @drop="dropOperation"
            >
              <div
                class="stages-grid__operation-name"
                style="grid-column: 1"
                :title="operation.name"
              >
              {{ operation.name }}
              </div>
              <div
                v-for="stage in stages"
                :key="stage"
                class="stages-grid__cell"
                :data-stage-cell="stage"
                :style="{ gridColumn: String(stage + 1) }"
              />
              <div
                class="stages-grid__operation"
                :class="{
                  'stages-grid__operation--adjacent': operation.operationKind === 'adjacent',
                  'stages-grid__operation--dragged': draggedOperationId === operation.id,
                }"
                :style="getOperationStyle(operation)"
                :draggable="resizeState === null"
                @dragstart="startDrag(operation.id, $event)"
                @dragend="stopDrag"
              >
                <button
                  v-if="operation.operationKind === 'adjacent'"
                  type="button"
                  class="stages-grid__resize stages-grid__resize--start"
                  aria-label="Изменить начало смежной операции"
                  @pointerdown="startResize(operation, 'start', $event)"
                />
                <span>{{ operation.name.split(" / ").at(-1) }}</span>
                <button
                  v-if="operation.operationKind === 'adjacent'"
                  type="button"
                  class="stages-grid__resize stages-grid__resize--end"
                  aria-label="Изменить окончание смежной операции"
                  @pointerdown="startResize(operation, 'end', $event)"
                />
              </div>
            </div>

            <p v-if="operations.length === 0" class="stages-message">
            В изделии нет конечных операций.
            </p>
          </div>

        </template>

      </div>
      <footer class="stages-modal__actions card-actions" v-if="!loading">
        <span v-if="hasChanges">Есть несохранённые изменения</span>
        <button
          type="button"
          class="stages-button stages-button--primary fc-button fc-button--primary"
          :disabled="!hasChanges || saving"
          @click="save"
        >
            {{ saving ? "Сохранение..." : "Сохранить изменения" }}
        </button>
      </footer>
      <div v-if="closeConfirmationOpen" class="stages-confirm-backdrop">
        <section v-escape-close="() => { closeConfirmationOpen = false }" class="stages-confirm card-shell" role="alertdialog" aria-modal="true">
          <h3 class="card-heading">Закрыть без сохранения?</h3>
          <div class="card-scroll">
            <p>Изменения технологических этапов будут потеряны.</p>

          </div>

          <div class="stages-confirm__actions card-actions">
            <button
              type="button"
              class="stages-button stages-button--danger fc-button fc-button--danger"
              @click="discardChanges"
            >
              Закрыть без сохранения
            </button>
            <button
              type="button"
              class="stages-button fc-button"
              @click="closeConfirmationOpen = false"
            >
              Продолжить редактирование
            </button>
          </div>
        </section>
      </div>

      <div v-if="pendingRemovedStage !== null" class="stages-confirm-backdrop">
        <section v-escape-close="cancelRemoveStage" class="stages-confirm card-shell" role="alertdialog" aria-modal="true">
          <h3 class="card-heading">Удалить этап {{ pendingRemovedStage }}?</h3>
          <div class="card-scroll">
            <p>
            После удаления останется {{ stageCount - 1 }} этапов. Операции справа
            и пересекающие удаляемый этап будут сдвинуты влево.
            </p>
            <ul v-if="stageRemovalPreview.length" class="stages-confirm__preview">
              <li v-for="item in stageRemovalPreview" :key="item.id">
                <strong>{{ item.name }}</strong>
                <span>{{ item.before }} → {{ item.after }}</span>
              </li>
            </ul>
            <p v-else>Расположение операций не изменится.</p>

          </div>

          <div class="stages-confirm__actions card-actions">
            <button
              type="button"
              class="stages-button stages-button--danger fc-button fc-button--danger"
              @click="confirmRemoveStage"
            >
              Удалить этап
            </button>
            <button
              type="button"
              class="stages-button fc-button"
              @click="cancelRemoveStage"
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
.stages-backdrop,
.stages-confirm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 130;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(23, 31, 42, 0.58);
}

.stages-modal {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(1480px, 96vw);
  max-height: 94vh;
  padding: 24px;
  overflow: hidden;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(15, 27, 39, 0.28);
  color: #1f2a33;
}

.stages-modal__head,
.stages-toolbar,
.stages-modal__actions,
.stages-confirm__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.stages-modal__head h2,
.stages-confirm h3 {
  margin: 0;
}

.stages-modal__eyebrow {
  margin: 0 0 4px;
  color: #5f6b76;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.stages-toolbar {
  margin: 18px 0 12px;
}

.stages-toolbar p,
.stages-modal__actions span,
.stages-message {
  margin: 0;
  color: #5f6b76;
}

.stages-message {
  padding: 18px;
  border-radius: 10px;
  background: #eef3f7;
}

.stages-message--error {
  margin-top: 16px;
  color: #8e2f2f;
  background: #fbeaea;
}

.stages-button {
  min-height: 42px;
  padding: 9px 16px;
  border: 1px solid #c7d1da;
  border-radius: 10px;
  background: #fff;
  color: #263746;
  cursor: pointer;
}

.stages-button--primary {
  border-color: #2f6ea3;
  background: #2f6ea3;
  color: #fff;
}

.stages-button--danger {
  border-color: #a94444;
  color: #8e2f2f;
}

.stages-button:disabled,
.stages-grid__delete-stage:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.stages-grid-wrap {
  flex: 1;
  overflow: auto;
  border: 1px solid #d6dee6;
  border-radius: 12px;
  background: #f7f9fb;
}

.stages-grid__head,
.stages-grid__row {
  display: grid;
}

.stages-grid__head {
  position: sticky;
  top: 0;
  z-index: 5;
  min-height: 58px;
  background: #e9eef3;
}

.stages-grid__row {
  position: relative;
  min-height: 58px;
  border-top: 1px solid #d6dee6;
}

.stages-grid__operation-title,
.stages-grid__operation-name {
  position: sticky;
  left: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  padding: 10px 14px;
  border-right: 1px solid #c7d1da;
  background: #fff;
}

.stages-grid__operation-title {
  z-index: 7;
  background: #e9eef3;
}

.stages-grid__operation-name {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stages-grid__stage-title {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px;
  border-right: 1px solid #c7d1da;
}

.stages-grid__delete-stage {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.76);
  color: #8e2f2f;
  font-size: 20px;
  cursor: pointer;
}

.stages-grid__cell {
  grid-row: 1;
  min-width: 0;
  border-right: 1px dashed #c7d1da;
  background: #f7f9fb;
}

.stages-grid__operation {
  grid-row: 1;
  z-index: 2;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  margin: 8px 7px;
  padding: 7px 18px;
  overflow: hidden;
  border: 1px solid;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(31, 42, 51, 0.16);
  font-size: 13px;
  font-weight: 650;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: grab;
  user-select: none;
}

.stages-grid__operation--dragged {
  opacity: 0.5;
}

.stages-grid__operation--adjacent {
  border-width: 2px;
}

.stages-grid__resize {
  position: absolute;
  top: 5px;
  bottom: 5px;
  width: 10px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: rgba(31, 42, 51, 0.34);
  cursor: ew-resize;
  touch-action: none;
}

.stages-grid__resize--start {
  left: 4px;
}

.stages-grid__resize--end {
  right: 4px;
}

.stages-modal__actions {
  min-height: 58px;
  padding-top: 14px;
}

.stages-confirm-backdrop {
  z-index: 140;
  border-radius: 18px;
}

.stages-confirm {
  width: min(480px, 90vw);
  padding: 24px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 55px rgba(15, 27, 39, 0.3);
}

.stages-confirm p {
  margin: 12px 0 20px;
  color: #5f6b76;
}

.stages-confirm__preview {
  display: grid;
  gap: 8px;
  max-height: 260px;
  margin: 0 0 20px;
  padding: 0;
  overflow: auto;
  list-style: none;
}

.stages-confirm__preview li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 10px;
  border-radius: 8px;
  background: #eef3f7;
  font-size: 13px;
}

@media (max-width: 760px) {
  .stages-backdrop {
    padding: 8px;
  }

  .stages-modal {
    width: 100%;
    max-height: 98vh;
    padding: 14px;
  }

  .stages-modal__head,
  .stages-toolbar,
  .stages-modal__actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
