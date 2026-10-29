<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import {
  createAdminWorkTimeSession,
  deleteAdminWorkTimeSession,
  fetchAdminWorkTimeOperations,
  fetchAdminWorkTimeOverlaps,
  fetchAdminWorkTimeSessions,
  fetchAdminWorkTimeWorkers,
  searchAdminWorkTimeOrders,
  updateAdminWorkTimeSession,
  type AdminWorkTimeOperation,
  type AdminWorkTimeOrder,
  type AdminWorkTimeSession,
  type AdminWorkTimeWorker,
} from "@/shared/api/adminWorkTime";
import { ApiRequestError } from "@/shared/api/http";
import {
  buildTimelineRows,
  buildTimelineTicks,
  combineLocalDateTime,
  formatSameOrderCollisionMessage,
  formatTimelineDuration,
  getCrossOrderOverlapSessionIds,
  getEffectiveOrderLinks,
  getOperationColor,
  getTimelineBlockStyle,
  intervalsOverlap,
  isSameOrderCollisionDetail,
  toLocalDateValue,
  toLocalTimeValue,
  type TimelineRowEntry,
} from "@/shared/lib/workTimeTimeline";
import { resolveWorkerListChange } from "@/shared/lib/adminWorkTimeSelection";
import { resolveAdminWorkTimeFormPolicy } from "@/shared/lib/adminWorkTimePolicy";

type EditorMode = "create" | "edit" | null;

type WorkTimeDraft = {
  orderId: number | null;
  orderNumber: string;
  operationId: number | null;
  operationName: string;
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
};

type AdminTimelineEntry = TimelineRowEntry<AdminWorkTimeSession>;

const MAX_RANGE_MS = 7 * 24 * 60 * 60 * 1000;

const workers = ref<AdminWorkTimeWorker[]>([]);
const selectedWorkerId = ref<number | null>(null);
const includeInactiveWorkers = ref(false);
const workersLoading = ref(false);
const workersError = ref("");

const now = new Date();
now.setSeconds(0, 0);
const initialRangeEnd = now.getTime();
const initialRangeStart = initialRangeEnd - 24 * 60 * 60 * 1000;
const rangeStartDate = ref(toLocalDateValue(initialRangeStart));
const rangeStartTime = ref(toLocalTimeValue(initialRangeStart));
const rangeEndDate = ref(toLocalDateValue(initialRangeEnd));
const rangeEndTime = ref(toLocalTimeValue(initialRangeEnd));

const sessions = ref<AdminWorkTimeSession[]>([]);
const sessionsLoading = ref(false);
const sessionsError = ref("");
const loadedRangeStart = ref(initialRangeStart);
const loadedRangeEnd = ref(initialRangeEnd);

const editorMode = ref<EditorMode>(null);
const selectedSession = ref<AdminWorkTimeSession | null>(null);
const serviceConversionMode = ref(false);
const draft = ref<WorkTimeDraft>(emptyDraft());
const baseline = ref("");
const operations = ref<AdminWorkTimeOperation[]>([]);
const operationsLoading = ref(false);
const operationQuery = ref("");
const operationDropdownOpen = ref(false);
const orderQuery = ref("");
const orderResults = ref<AdminWorkTimeOrder[]>([]);
const orderSearchLoading = ref(false);
const saveLoading = ref(false);
const editorError = ref("");
const overlapCheckError = ref("");
const remoteOverlapOrderNumbers = ref<string[]>([]);
const checkedOverlapSignature = ref<string | null>(null);
let orderSearchTimeoutId: number | null = null;
let overlapCheckTimeoutId: number | null = null;
let overlapCheckRequestId = 0;
let sessionsRequestId = 0;
let orderSearchRequestId = 0;
let operationsRequestId = 0;

const rangeStart = computed(() =>
  combineLocalDateTime(rangeStartDate.value, rangeStartTime.value),
);
const rangeEnd = computed(() =>
  combineLocalDateTime(rangeEndDate.value, rangeEndTime.value),
);
const rangeError = computed(() => {
  if (rangeStart.value === null || rangeEnd.value === null) {
    return "Необходимо указать начало и окончание диапазона.";
  }
  if (rangeEnd.value <= rangeStart.value) {
    return "Окончание диапазона должно быть позже начала.";
  }
  if (rangeEnd.value - rangeStart.value > MAX_RANGE_MS) {
    return "Диапазон не должен превышать 7 суток.";
  }
  return "";
});

const timelineTicks = computed(() =>
  buildTimelineTicks(loadedRangeStart.value, loadedRangeEnd.value),
);
const timelineRows = computed(() => buildTimelineRows(sessions.value));
const warningSessionIds = computed(() =>
  getCrossOrderOverlapSessionIds(sessions.value),
);
const timelineWidth = computed(() => {
  const hours = Math.max(
    1,
    (loadedRangeEnd.value - loadedRangeStart.value) / (60 * 60 * 1000),
  );
  return `max(100%, ${Math.ceil(hours * 64) + 150}px)`;
});
const selectedWorker = computed(() =>
  workers.value.find((worker) => worker.id === selectedWorkerId.value) ?? null,
);
const canAddTimeForSelectedWorker = computed(
  () => selectedWorker.value?.canAddTime === true,
);

const filteredOperations = computed(() => {
  const query = operationQuery.value.trim().toLocaleLowerCase();
  if (!query) {
    return operations.value;
  }
  return operations.value.filter((operation) =>
    operation.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
});

const draftStartedAt = computed(() =>
  combineLocalDateTime(
    draft.value.startDate,
    draft.value.startTime,
    editorMode.value === "edit" ? selectedSession.value?.startedAt : undefined,
  ),
);
const draftEndedAt = computed(() =>
  combineLocalDateTime(
    draft.value.endDate,
    draft.value.endTime,
    editorMode.value === "edit" ? selectedSession.value?.endedAt ?? undefined : undefined,
  ),
);
const draftDuration = computed(() => {
  if (draftStartedAt.value === null || draftEndedAt.value === null) {
    return "—";
  }
  return formatTimelineDuration(draftEndedAt.value - draftStartedAt.value);
});
const isEditableServiceSession = computed(
  () =>
    editorMode.value === "edit"
    && ["preparation", "break", "idle"].includes(
      selectedSession.value?.timerType ?? "",
    ),
);
const replacesServiceWithOperation = computed(
  () => isEditableServiceSession.value && serviceConversionMode.value,
);
const draftOverlapRequest = computed(() => {
  if (
    selectedWorkerId.value === null
    || draft.value.orderId === null
    || draftStartedAt.value === null
    || draftEndedAt.value === null
    || draftEndedAt.value <= draftStartedAt.value
    || draftEndedAt.value > Date.now()
    || (isEditableServiceSession.value && !replacesServiceWithOperation.value)
  ) {
    return null;
  }
  return {
    workerUserId: selectedWorkerId.value,
    orderId: draft.value.orderId,
    startedAt: draftStartedAt.value,
    endedAt: draftEndedAt.value,
    excludeSessionId: selectedSession.value?.id,
  };
});
const draftOverlapSignature = computed(() =>
  draftOverlapRequest.value === null
    ? null
    : JSON.stringify(draftOverlapRequest.value),
);
const isOverlapCheckPending = computed(
  () =>
    draftOverlapSignature.value !== null
    && checkedOverlapSignature.value !== draftOverlapSignature.value,
);
const sameOrderCollision = computed(() => {
  if (
    (isEditableServiceSession.value && !replacesServiceWithOperation.value)
    || draftStartedAt.value === null
    || draftEndedAt.value === null
  ) {
    return null;
  }
  return sessions.value.find((item) => {
    if (item.id === selectedSession.value?.id) {
      return false;
    }
    return (
      item.timerType === "operation"
      && getEffectiveOrderLinks(item).some(
        (orderLink) => orderLink.orderId === draft.value.orderId,
      )
      && intervalsOverlap(
        item.startedAt,
        item.endedAt,
        draftStartedAt.value!,
        draftEndedAt.value!,
      )
    );
  }) ?? null;
});
const localCrossOrderNumbers = computed(() => {
  if (
    draft.value.orderId === null
    || draftStartedAt.value === null
    || draftEndedAt.value === null
  ) {
    return [];
  }
  const orderNumbers = new Set<string>();
  for (const item of sessions.value) {
    if (
      item.id === selectedSession.value?.id
      || item.timerType !== "operation"
      || !intervalsOverlap(
        item.startedAt,
        item.endedAt,
        draftStartedAt.value!,
        draftEndedAt.value!,
      )
    ) {
      continue;
    }
    for (const orderLink of getEffectiveOrderLinks(item)) {
      if (orderLink.orderId !== draft.value.orderId) {
        orderNumbers.add(orderLink.orderNumber ?? "без номера");
      }
    }
  }
  return [...orderNumbers];
});
const overlapWarning = computed(() => {
  const orderNumbers = new Set(remoteOverlapOrderNumbers.value);
  for (const orderNumber of localCrossOrderNumbers.value) {
    orderNumbers.add(orderNumber);
  }
  if (orderNumbers.size === 0) {
    return "";
  }
  return `Время пересекается с заказами: ${[...orderNumbers].join(", ")}. Сохранение разрешено.`;
});
const draftError = computed(() => {
  if (
    (!isEditableServiceSession.value || replacesServiceWithOperation.value)
    && draft.value.orderId === null
  ) {
    return "Необходимо выбрать заказ.";
  }
  if (
    (!isEditableServiceSession.value || replacesServiceWithOperation.value)
    && draft.value.operationId === null
  ) {
    return "Необходимо выбрать операцию.";
  }
  if (draftStartedAt.value === null || draftEndedAt.value === null) {
    return "Необходимо указать дату и время начала и окончания.";
  }
  if (draftEndedAt.value <= draftStartedAt.value) {
    return "Окончание интервала должно быть позже начала.";
  }
  if (draftEndedAt.value > Date.now()) {
    return "Нельзя учитывать интервал из будущего.";
  }
  if (sameOrderCollision.value) {
    return `В заказе уже есть пересекающийся интервал «${sameOrderCollision.value.label}».`;
  }
  return "";
});
const isDirty = computed(() => {
  if (editorMode.value === null) {
    return false;
  }
  return draftSignature() !== baseline.value;
});
const formPolicy = computed(() =>
  resolveAdminWorkTimeFormPolicy({
    editorActive: editorMode.value !== null,
    editable:
      editorMode.value === "create" || selectedSession.value?.editable === true,
    dirty: isDirty.value,
    hasBlockingError: Boolean(draftError.value),
    saving: saveLoading.value,
    advisoryOverlapCheckPending: isOverlapCheckPending.value,
  }),
);
const canSave = computed(() => formPolicy.value.canSave);

watch(draftOverlapSignature, scheduleOverlapCheck, { immediate: true });

onMounted(() => {
  void loadWorkers();
});

onBeforeUnmount(() => {
  invalidateOrderSearchRequest();
  invalidateOperationsRequest();
  clearOverlapCheckTimeout();
  overlapCheckRequestId += 1;
  sessionsRequestId += 1;
});

async function loadWorkers(
  includeInactive = includeInactiveWorkers.value,
): Promise<boolean> {
  workersLoading.value = true;
  workersError.value = "";
  try {
    const loadedWorkers = await fetchAdminWorkTimeWorkers(includeInactive);
    const change = resolveWorkerListChange(
      selectedWorkerId.value,
      loadedWorkers,
      confirmDiscardChanges,
    );
    if (!change.canApply) {
      return false;
    }
    workers.value = loadedWorkers;
    includeInactiveWorkers.value = includeInactive;
    if (change.selectedWorkerMissing) {
      invalidateSessionsRequest();
      selectedWorkerId.value = null;
      sessions.value = [];
      resetEditor();
    }
    return true;
  } catch (error) {
    workersError.value = errorMessage(error);
    return false;
  } finally {
    workersLoading.value = false;
  }
}

async function handleIncludeInactiveWorkersChange(event: Event) {
  const checkbox = event.currentTarget;
  if (!(checkbox instanceof HTMLInputElement)) {
    return;
  }
  const includeInactive = checkbox.checked;
  checkbox.checked = includeInactiveWorkers.value;
  await loadWorkers(includeInactive);
  checkbox.checked = includeInactiveWorkers.value;
}

async function applyRange() {
  if (selectedWorkerId.value === null || rangeError.value) {
    return;
  }
  if (!confirmDiscardChanges()) {
    return;
  }
  const workerUserId = selectedWorkerId.value;
  const periodStart = rangeStart.value!;
  const periodEnd = rangeEnd.value!;
  const requestId = sessionsRequestId + 1;
  sessionsRequestId = requestId;
  sessionsLoading.value = true;
  sessionsError.value = "";
  resetEditor();
  try {
    const loadedSessions = await fetchAdminWorkTimeSessions({
      workerUserId,
      fromTs: periodStart,
      toTs: periodEnd,
    });
    if (
      requestId !== sessionsRequestId
      || selectedWorkerId.value !== workerUserId
    ) {
      return;
    }
    loadedRangeStart.value = periodStart;
    loadedRangeEnd.value = periodEnd;
    sessions.value = loadedSessions;
  } catch (error) {
    if (requestId === sessionsRequestId) {
      sessionsError.value = errorMessage(error);
    }
  } finally {
    if (requestId === sessionsRequestId) {
      sessionsLoading.value = false;
    }
  }
}

async function handleWorkerChange(event: Event) {
  const select = event.currentTarget;
  if (!(select instanceof HTMLSelectElement)) {
    return;
  }
  const nextWorkerId = select.value === ""
    ? null
    : Number.parseInt(select.value, 10);
  if (nextWorkerId === selectedWorkerId.value) {
    return;
  }
  if (!confirmDiscardChanges()) {
    select.value = selectedWorkerId.value === null
      ? ""
      : String(selectedWorkerId.value);
    return;
  }
  invalidateSessionsRequest();
  selectedWorkerId.value = nextWorkerId;
  sessions.value = [];
  resetEditor();
  if (selectedWorkerId.value !== null) {
    await applyRange();
  }
}

async function selectTimelineSession(
  item: AdminWorkTimeSession,
  forceRefresh = false,
) {
  if (!forceRefresh && selectedSession.value?.id === item.id) {
    return;
  }
  if (!forceRefresh && !confirmDiscardChanges()) {
    return;
  }
  invalidateOrderSearchRequest();
  invalidateOperationsRequest();
  selectedSession.value = item;
  editorMode.value = "edit";
  serviceConversionMode.value = false;
  editorError.value = "";
  draft.value = {
    orderId: item.orderId,
    orderNumber: item.orderNumber ?? "—",
    operationId: item.operationId,
    operationName: item.operationName ?? item.label,
    startDate: toLocalDateValue(item.startedAt),
    startTime: toLocalTimeValue(item.startedAt),
    endDate: toLocalDateValue(item.endedAt ?? Date.now()),
    endTime: toLocalTimeValue(item.endedAt ?? Date.now()),
  };
  operationQuery.value = draft.value.operationName;
  baseline.value = draftSignature();
  operations.value = [];
  if (item.orderId !== null) {
    await loadOperations(item.orderId);
  }
}

function startCreate() {
  if (!canAddTimeForSelectedWorker.value || !confirmDiscardChanges()) {
    return;
  }
  invalidateOrderSearchRequest();
  invalidateOperationsRequest();
  const end = Math.min(Date.now(), loadedRangeEnd.value);
  const start = end - 60 * 60 * 1000;
  selectedSession.value = null;
  editorMode.value = "create";
  serviceConversionMode.value = false;
  editorError.value = "";
  operations.value = [];
  operationQuery.value = "";
  orderQuery.value = "";
  orderResults.value = [];
  draft.value = {
    ...emptyDraft(),
    startDate: toLocalDateValue(start),
    startTime: toLocalTimeValue(start),
    endDate: toLocalDateValue(end),
    endTime: toLocalTimeValue(end),
  };
  baseline.value = draftSignature();
}

function resetEditor() {
  invalidateOrderSearchRequest();
  invalidateOperationsRequest();
  editorMode.value = null;
  selectedSession.value = null;
  serviceConversionMode.value = false;
  draft.value = emptyDraft();
  baseline.value = "";
  operations.value = [];
  operationQuery.value = "";
  orderQuery.value = "";
  orderResults.value = [];
  editorError.value = "";
  overlapCheckError.value = "";
  remoteOverlapOrderNumbers.value = [];
  checkedOverlapSignature.value = null;
}

function scheduleOverlapCheck(signature: string | null) {
  clearOverlapCheckTimeout();
  overlapCheckRequestId += 1;
  overlapCheckError.value = "";
  remoteOverlapOrderNumbers.value = [];
  checkedOverlapSignature.value = null;
  if (signature === null) {
    return;
  }
  overlapCheckTimeoutId = window.setTimeout(() => {
    overlapCheckTimeoutId = null;
    void runOverlapCheck(signature);
  }, 250);
}

async function runOverlapCheck(signature: string) {
  const request = draftOverlapRequest.value;
  if (request === null || draftOverlapSignature.value !== signature) {
    return;
  }
  const requestId = overlapCheckRequestId + 1;
  overlapCheckRequestId = requestId;
  try {
    const overlaps = await fetchAdminWorkTimeOverlaps(request);
    if (
      requestId !== overlapCheckRequestId
      || draftOverlapSignature.value !== signature
    ) {
      return;
    }
    remoteOverlapOrderNumbers.value = overlaps.map((item) => item.orderNumber);
    checkedOverlapSignature.value = signature;
  } catch {
    if (
      requestId === overlapCheckRequestId
      && draftOverlapSignature.value === signature
    ) {
      overlapCheckError.value = (
        "Не удалось проверить пересечения между разными заказами. "
        + "Сохранение разрешено."
      );
      checkedOverlapSignature.value = signature;
    }
  }
}

function clearOverlapCheckTimeout() {
  if (overlapCheckTimeoutId !== null) {
    window.clearTimeout(overlapCheckTimeoutId);
    overlapCheckTimeoutId = null;
  }
}

function scheduleOrderSearch() {
  invalidateOrderSearchRequest();
  const requestId = orderSearchRequestId;
  const query = orderQuery.value.trim();
  orderResults.value = [];
  if (!query) {
    return;
  }
  orderSearchTimeoutId = window.setTimeout(() => {
    orderSearchTimeoutId = null;
    void runOrderSearch(query, requestId);
  }, 250);
}

async function runOrderSearch(query: string, requestId: number) {
  if (
    requestId !== orderSearchRequestId
    || orderQuery.value.trim() !== query
  ) {
    return;
  }
  orderSearchLoading.value = true;
  try {
    const results = await searchAdminWorkTimeOrders(query);
    if (
      requestId !== orderSearchRequestId
      || orderQuery.value.trim() !== query
    ) {
      return;
    }
    orderResults.value = results;
  } catch (error) {
    if (requestId === orderSearchRequestId) {
      editorError.value = errorMessage(error);
    }
  } finally {
    if (requestId === orderSearchRequestId) {
      orderSearchLoading.value = false;
    }
  }
}

async function selectOrder(order: AdminWorkTimeOrder) {
  invalidateOrderSearchRequest();
  invalidateOperationsRequest();
  draft.value.orderId = order.id;
  draft.value.orderNumber = order.orderNumber;
  draft.value.operationId = null;
  draft.value.operationName = "";
  operationQuery.value = "";
  orderQuery.value = "";
  orderResults.value = [];
  await loadOperations(order.id);
}

async function loadOperations(orderId: number) {
  const requestId = operationsRequestId + 1;
  operationsRequestId = requestId;
  operationsLoading.value = true;
  try {
    const loadedOperations = await fetchAdminWorkTimeOperations(orderId);
    if (
      requestId !== operationsRequestId
      || draft.value.orderId !== orderId
    ) {
      return;
    }
    operations.value = loadedOperations;
  } catch (error) {
    if (requestId === operationsRequestId) {
      editorError.value = errorMessage(error);
    }
  } finally {
    if (requestId === operationsRequestId) {
      operationsLoading.value = false;
    }
  }
}

function invalidateOrderSearchRequest() {
  if (orderSearchTimeoutId !== null) {
    window.clearTimeout(orderSearchTimeoutId);
    orderSearchTimeoutId = null;
  }
  orderSearchRequestId += 1;
  orderSearchLoading.value = false;
}

function invalidateOperationsRequest() {
  operationsRequestId += 1;
  operationsLoading.value = false;
}

function selectOperation(operation: AdminWorkTimeOperation) {
  draft.value.operationId = operation.id;
  draft.value.operationName = operation.name;
  operationQuery.value = operation.name;
  operationDropdownOpen.value = false;
}

function startServiceConversion() {
  if (!isEditableServiceSession.value || !selectedSession.value?.editable) {
    return;
  }
  invalidateOrderSearchRequest();
  invalidateOperationsRequest();
  serviceConversionMode.value = true;
  draft.value.orderId = null;
  draft.value.orderNumber = "";
  draft.value.operationId = null;
  draft.value.operationName = "";
  orderQuery.value = "";
  orderResults.value = [];
  operationQuery.value = "";
  operations.value = [];
}

function cancelServiceConversion() {
  invalidateOrderSearchRequest();
  invalidateOperationsRequest();
  serviceConversionMode.value = false;
  draft.value.orderId = null;
  draft.value.orderNumber = "—";
  draft.value.operationId = null;
  draft.value.operationName = selectedSession.value?.label ?? "Служебный интервал";
  orderQuery.value = "";
  orderResults.value = [];
  operationQuery.value = draft.value.operationName;
  operations.value = [];
}

async function saveChanges() {
  if (!canSave.value || selectedWorkerId.value === null) {
    return;
  }
  saveLoading.value = true;
  editorError.value = "";
  try {
    let saved: AdminWorkTimeSession;
    if (editorMode.value === "create") {
      saved = await createAdminWorkTimeSession({
        worker_user_id: selectedWorkerId.value,
        order_id: draft.value.orderId!,
        operation_id: draft.value.operationId!,
        started_at: draftStartedAt.value!,
        ended_at: draftEndedAt.value!,
      });
    } else {
      saved = await updateAdminWorkTimeSession(selectedSession.value!.id, {
        order_id: replacesServiceWithOperation.value ? draft.value.orderId : undefined,
        operation_id: replacesServiceWithOperation.value || !isEditableServiceSession.value
          ? draft.value.operationId
          : null,
        started_at: draftStartedAt.value!,
        ended_at: draftEndedAt.value!,
        expected_updated_at: selectedSession.value!.updatedAt,
      });
    }
    await reloadAfterMutation(saved.id);
  } catch (error) {
    editorError.value = errorMessage(error);
  } finally {
    saveLoading.value = false;
  }
}

async function removeSession() {
  const item = selectedSession.value;
  if (!item?.editable || saveLoading.value) {
    return;
  }
  const target = ["preparation", "break", "idle"].includes(item.timerType)
    ? `интервал «${item.label}»`
    : `«${item.label}» для заказа ${item.orderNumber ?? "—"}`;
  if (!window.confirm(`Удалить ${target}?`)) {
    return;
  }
  saveLoading.value = true;
  editorError.value = "";
  try {
    await deleteAdminWorkTimeSession(item.id, item.updatedAt);
    resetEditor();
    await applyRange();
  } catch (error) {
    editorError.value = errorMessage(error);
  } finally {
    saveLoading.value = false;
  }
}

async function reloadAfterMutation(sessionId: number) {
  if (selectedWorkerId.value === null) {
    return;
  }
  const workerUserId = selectedWorkerId.value;
  const requestId = sessionsRequestId + 1;
  sessionsRequestId = requestId;
  sessionsLoading.value = true;
  sessionsError.value = "";
  try {
    const loadedSessions = await fetchAdminWorkTimeSessions({
      workerUserId,
      fromTs: loadedRangeStart.value,
      toTs: loadedRangeEnd.value,
    });
    if (
      requestId !== sessionsRequestId
      || selectedWorkerId.value !== workerUserId
    ) {
      return;
    }
    sessions.value = loadedSessions;
    const saved = loadedSessions.find((item) => item.id === sessionId);
    if (saved) {
      await selectTimelineSession(saved, true);
    } else {
      resetEditor();
    }
  } catch (error) {
    if (requestId === sessionsRequestId) {
      throw error;
    }
  } finally {
    if (requestId === sessionsRequestId) {
      sessionsLoading.value = false;
    }
  }
}

function invalidateSessionsRequest() {
  sessionsRequestId += 1;
  sessionsLoading.value = false;
}

function getBlockStyle(item: AdminWorkTimeSession): Record<string, string> {
  const style = getTimelineBlockStyle(
    item.startedAt,
    item.endedAt,
    loadedRangeStart.value,
    loadedRangeEnd.value,
  );
  return {
    ...style,
    backgroundColor:
      item.timerType === "operation"
        ? getOperationColor(item.operationId)
        : getServiceTimerColor(item.timerType),
  };
}

function getTimelineBlockLabel(entry: AdminTimelineEntry): string {
  if (entry.allocatedSeconds === null) {
    return entry.session.label;
  }
  return (
    `${entry.session.label} · `
    + formatTimelineDuration(entry.allocatedSeconds * 1000)
  );
}

function getTimelineBlockTitle(entry: AdminTimelineEntry): string {
  const item = entry.session;
  const allocationLabel = entry.allocatedSeconds === null
    ? ""
    : ` · распределено ${formatTimelineDuration(entry.allocatedSeconds * 1000)}`;
  const warningLabel = warningSessionIds.value.has(item.id)
    ? " · пересечение с другим заказом"
    : "";
  return (
    `${item.label}: ${formatDateTime(item.startedAt)}–${formatDateTime(item.endedAt)}`
    + allocationLabel
    + warningLabel
  );
}

function getServiceTimerColor(timerType: AdminWorkTimeSession["timerType"]): string {
  if (timerType === "break") {
    return "#64748b";
  }
  if (timerType === "idle") {
    return "#b91c1c";
  }
  return "#475569";
}

function draftSignature(): string {
  return JSON.stringify(draft.value);
}

function confirmDiscardChanges(): boolean {
  return !isDirty.value || window.confirm("Отменить несохранённые изменения?");
}

function emptyDraft(): WorkTimeDraft {
  return {
    orderId: null,
    orderNumber: "",
    operationId: null,
    operationName: "",
    startDate: "",
    startTime: "",
    endDate: "",
    endTime: "",
  };
}

function formatDateTime(timestamp: number | null): string {
  if (timestamp === null) {
    return "сейчас";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

function errorMessage(error: unknown): string {
  if (
    error instanceof ApiRequestError
    && isSameOrderCollisionDetail(error.detail)
  ) {
    return formatSameOrderCollisionMessage(error.detail);
  }
  return error instanceof Error ? error.message : "Не удалось выполнить запрос.";
}
</script>

<template>
  <article class="work-time-panel">
    <header class="panel-head">
      <div>
        <h2>Редактирование рабочего времени</h2>
        <p>Ручное исправление завершённых интервалов исполнителя</p>
        <p v-if="selectedWorkerId !== null && !canAddTimeForSelectedWorker">
          Для выбранного пользователя доступно только редактирование истории
        </p>
      </div>
      <button
        type="button"
        class="button button--primary"
        :disabled="!canAddTimeForSelectedWorker"
        @click="startCreate"
      >
        + Добавить запись
      </button>
    </header>

    <form class="filters" @submit.prevent="void applyRange()">
      <label class="field field--worker">
        <span>Исполнитель</span>
        <select
          :value="selectedWorkerId ?? ''"
          :disabled="workersLoading"
          @change="void handleWorkerChange($event)"
        >
          <option value="">Выбрать исполнителя</option>
          <option v-for="worker in workers" :key="worker.id" :value="worker.id">
            {{ worker.name }}{{ worker.canAddTime ? "" : " (только история)" }}
          </option>
        </select>
      </label>

      <label class="field field--checkbox">
        <input
          :checked="includeInactiveWorkers"
          :disabled="workersLoading"
          type="checkbox"
          @change="void handleIncludeInactiveWorkersChange($event)"
        />
        <span>Показывать неактивных</span>
      </label>

      <fieldset class="date-range">
        <legend>Начало диапазона</legend>
        <input v-model="rangeStartDate" type="date" />
        <input v-model="rangeStartTime" type="time" />
      </fieldset>
      <fieldset class="date-range">
        <legend>Окончание диапазона</legend>
        <input v-model="rangeEndDate" type="date" />
        <input v-model="rangeEndTime" type="time" />
      </fieldset>

      <button
        type="submit"
        class="button button--secondary"
        :disabled="selectedWorkerId === null || Boolean(rangeError) || sessionsLoading"
      >
        {{ sessionsLoading ? "Загрузка..." : "Показать" }}
      </button>
    </form>

    <p v-if="rangeError" class="message message--error">{{ rangeError }}</p>
    <p v-if="workersError || sessionsError" class="message message--error">
      {{ workersError || sessionsError }}
    </p>

    <section class="timeline-card" aria-label="Операции по времени">
      <div v-if="selectedWorkerId === null" class="empty-state">
        Выбрать исполнителя для просмотра операций
      </div>
      <div v-else-if="sessionsLoading" class="empty-state">Загрузка операций...</div>
      <div v-else class="timeline-scroll">
        <div class="timeline" :style="{ width: timelineWidth }">
          <div class="timeline__rows">
            <div v-for="row in timelineRows" :key="row.key" class="timeline__row">
              <strong class="timeline__row-label">{{ row.label }}</strong>
              <div class="timeline__track">
                <span
                  v-for="tick in timelineTicks"
                  :key="tick.timestamp"
                  class="timeline__grid-line"
                  :style="{ left: `${tick.leftPercent}%` }"
                />
                <button
                  v-for="entry in row.entries"
                  :key="entry.key"
                  type="button"
                  class="timeline__block"
                  :class="{
                    'timeline__block--selected': selectedSession?.id === entry.session.id,
                    'timeline__block--readonly': !entry.session.editable,
                    'timeline__block--warning': warningSessionIds.has(entry.session.id),
                  }"
                  :style="getBlockStyle(entry.session)"
                  :title="getTimelineBlockTitle(entry)"
                  @click="void selectTimelineSession(entry.session)"
                >
                  {{ getTimelineBlockLabel(entry) }}
                </button>
              </div>
            </div>
          </div>
          <div class="timeline__axis-row">
            <span class="timeline__axis-spacer" />
            <div class="timeline__axis">
              <span
                v-for="tick in timelineTicks"
                :key="`axis-${tick.timestamp}`"
                class="timeline__tick"
                :style="{ left: `${tick.leftPercent}%` }"
              >
                <small v-if="tick.dateLabel">{{ tick.dateLabel }}</small>
                {{ tick.timeLabel }}
              </span>
            </div>
          </div>
        </div>
      </div>
      <p v-if="warningSessionIds.size" class="message message--warning timeline-warning">
        Пересечения между разными заказами выделены предупреждением и не блокируют сохранение
      </p>
      <p v-if="selectedWorkerId !== null && !sessionsLoading && sessions.length === 0" class="timeline-empty">
        В выбранном диапазоне записи отсутствуют
      </p>
    </section>

    <section v-if="editorMode" class="editor-card">
      <header class="editor-head">
        <div>
          <h3>
            {{ editorMode === "create"
              ? "Новая запись"
              : isEditableServiceSession
                ? selectedSession?.label
                : "Данные операции" }}
          </h3>
          <p v-if="selectedSession?.blockedReason" class="message message--warning">
            {{ selectedSession.blockedReason }}
          </p>
          <p v-if="selectedSession?.allocatedOrderNumbers.length">
            Распределено по заказам: {{ selectedSession.allocatedOrderNumbers.join(", ") }}
          </p>
        </div>
        <button type="button" class="button button--ghost" @click="resetEditor">
          Отмена
        </button>
      </header>

      <div v-if="editorMode === 'create' && draft.orderId === null" class="order-search">
        <label class="field">
          <span>Номер заказа</span>
          <input
            v-model="orderQuery"
            type="search"
            placeholder="Начать ввод номера"
            @input="scheduleOrderSearch"
          />
        </label>
        <div v-if="orderSearchLoading" class="search-results">Поиск...</div>
        <div v-else-if="orderResults.length" class="search-results">
          <button
            v-for="order in orderResults"
            :key="order.id"
            type="button"
            @click="void selectOrder(order)"
          >
            <strong>
              {{ order.orderNumber }}{{ order.isDeleted ? " · удалён" : "" }}
            </strong>
            <span>{{ order.productName }} {{ order.productVersion }}</span>
          </button>
        </div>
      </div>

      <div v-else class="editor-grid" :class="{ 'editor-grid--service': isEditableServiceSession }">
        <template v-if="!isEditableServiceSession">
          <label class="field">
            <span>Номер заказа</span>
            <input :value="draft.orderNumber" type="text" readonly />
          </label>

          <div class="field operation-picker">
            <span>Операция</span>
            <input
              v-model="operationQuery"
              type="search"
              :disabled="selectedSession !== null && !selectedSession.editable"
              placeholder="Поиск по наименованию"
              @focus="operationDropdownOpen = true"
              @input="operationDropdownOpen = true; draft.operationId = null"
            />
            <div v-if="operationDropdownOpen" class="operation-options">
              <button
                v-for="operation in filteredOperations"
                :key="operation.id"
                type="button"
                @click="selectOperation(operation)"
              >
                {{ operation.name }}
              </button>
              <span v-if="operationsLoading">Загрузка...</span>
              <span v-else-if="filteredOperations.length === 0">Операции не найдены</span>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="service-summary">
            <span v-if="replacesServiceWithOperation">
              После сохранения интервал станет производственной операцией выбранного заказа
            </span>
            <span v-else>
              Интервал «{{ selectedSession?.label }}» не привязан к заказу или производственной операции
            </span>
            <button
              v-if="!replacesServiceWithOperation"
              type="button"
              class="button button--secondary"
              :disabled="!selectedSession?.editable"
              @click="startServiceConversion"
            >
              Заменить на операцию
            </button>
            <button
              v-else
              type="button"
              class="button button--ghost"
              @click="cancelServiceConversion"
            >
              Оставить «{{ selectedSession?.label }}»
            </button>
          </div>

          <div
            v-if="replacesServiceWithOperation && draft.orderId === null"
            class="order-search editor-grid__wide"
          >
            <label class="field">
              <span>Номер заказа</span>
              <input
                v-model="orderQuery"
                type="search"
                placeholder="Начать ввод номера"
                @input="scheduleOrderSearch"
              />
            </label>
            <div v-if="orderSearchLoading" class="search-results">Поиск...</div>
            <div v-else-if="orderResults.length" class="search-results">
              <button
                v-for="order in orderResults"
                :key="order.id"
                type="button"
                @click="void selectOrder(order)"
              >
                <strong>
                  {{ order.orderNumber }}{{ order.isDeleted ? " · удалён" : "" }}
                </strong>
                <span>{{ order.productName }} {{ order.productVersion }}</span>
              </button>
            </div>
          </div>

          <template v-else-if="replacesServiceWithOperation">
            <label class="field">
              <span>Номер заказа</span>
              <input :value="draft.orderNumber" type="text" readonly />
            </label>

            <div class="field operation-picker">
              <span>Операция</span>
              <input
                v-model="operationQuery"
                type="search"
                placeholder="Поиск по наименованию"
                @focus="operationDropdownOpen = true"
                @input="operationDropdownOpen = true; draft.operationId = null"
              />
              <div v-if="operationDropdownOpen" class="operation-options">
                <button
                  v-for="operation in filteredOperations"
                  :key="operation.id"
                  type="button"
                  @click="selectOperation(operation)"
                >
                  {{ operation.name }}
                </button>
                <span v-if="operationsLoading">Загрузка...</span>
                <span v-else-if="filteredOperations.length === 0">Операции не найдены</span>
              </div>
            </div>
          </template>
        </template>

        <fieldset class="date-range date-range--editor">
          <legend>{{ isEditableServiceSession ? "Начало интервала" : "Начало операции" }}</legend>
          <input
            v-model="draft.startDate"
            type="date"
            :disabled="selectedSession !== null && !selectedSession.editable"
          />
          <input
            v-model="draft.startTime"
            type="time"
            :disabled="selectedSession !== null && !selectedSession.editable"
          />
        </fieldset>

        <fieldset class="date-range date-range--editor">
          <legend>{{ isEditableServiceSession ? "Окончание интервала" : "Окончание операции" }}</legend>
          <input
            v-model="draft.endDate"
            type="date"
            :disabled="selectedSession !== null && !selectedSession.editable"
          />
          <input
            v-model="draft.endTime"
            type="time"
            :disabled="selectedSession !== null && !selectedSession.editable"
          />
        </fieldset>
      </div>

      <p v-if="draft.orderId !== null || isEditableServiceSession" class="duration">
        Длительность: {{ draftDuration }}
      </p>
      <p v-if="(draft.orderId !== null || isEditableServiceSession) && draftError" class="message message--error">
        {{ draftError }}
      </p>
      <p v-if="draft.orderId !== null && overlapWarning" class="message message--warning">
        {{ overlapWarning }}
      </p>
      <p
        v-if="formPolicy.advisoryOverlapCheckPending && !overlapCheckError"
        class="message"
      >
        Проверка пересечений...
      </p>
      <p v-if="overlapCheckError" class="message message--warning">
        {{ overlapCheckError }}
      </p>
      <p v-if="editorError" class="message message--error">{{ editorError }}</p>

      <footer v-if="draft.orderId !== null || isEditableServiceSession" class="editor-actions">
        <button
          v-if="editorMode === 'edit' && selectedSession?.editable"
          type="button"
          class="button button--danger"
          :disabled="saveLoading"
          @click="void removeSession()"
        >
          Удалить
        </button>
        <button
          type="button"
          class="button button--primary"
          :disabled="!canSave"
          @click="void saveChanges()"
        >
          {{ saveLoading ? "Сохранение..." : "Сохранить изменения" }}
        </button>
      </footer>
    </section>
  </article>
</template>

<style scoped>
.work-time-panel {
  display: grid;
  gap: 20px;
  padding: 24px;
  border: 1px solid #dbe3ee;
  border-radius: 20px;
  background: #fff;
}

.panel-head,
.editor-head,
.editor-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.panel-head h2,
.editor-head h3 {
  margin: 0 0 6px;
}

.panel-head p,
.editor-head p {
  margin: 0;
  color: #64748b;
}

.filters,
.editor-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1.4fr) repeat(2, minmax(220px, 1fr)) auto;
  align-items: end;
  gap: 14px;
}

.field {
  position: relative;
  display: grid;
  gap: 7px;
  color: #334155;
  font-size: 14px;
  font-weight: 700;
}

.field input,
.field select,
.date-range input {
  min-height: 44px;
  box-sizing: border-box;
  padding: 9px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #fff;
  color: #0f172a;
  font: inherit;
}

.field input[readonly] {
  background: #f1f5f9;
}

.field--checkbox {
  display: flex;
  align-items: center;
  min-height: 44px;
  font-weight: 500;
}

.field--checkbox input {
  min-height: auto;
}

.date-range {
  display: grid;
  grid-template-columns: minmax(130px, 1fr) 100px;
  gap: 8px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.date-range legend {
  grid-column: 1 / -1;
  margin-bottom: 7px;
  color: #334155;
  font-size: 14px;
  font-weight: 700;
}

.button {
  min-height: 44px;
  padding: 10px 16px;
  border: 1px solid transparent;
  border-radius: 11px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.button--primary {
  background: #2563eb;
  color: #fff;
}

.button--secondary,
.button--ghost {
  border-color: #cbd5e1;
  background: #fff;
  color: #1e293b;
}

.button--danger {
  background: #b91c1c;
  color: #fff;
}

.message {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
}

.message--error {
  background: #fef2f2;
  color: #b91c1c;
}

.message--warning {
  background: #fffbeb;
  color: #92400e !important;
}

.timeline-card,
.editor-card {
  position: relative;
  padding: 16px;
  border: 1px solid #dbe3ee;
  border-radius: 16px;
  background: #f8fafc;
}

.timeline-scroll {
  overflow-x: auto;
  padding-bottom: 4px;
}

.timeline {
  position: relative;
  min-width: 100%;
}

.timeline__track {
  position: relative;
  height: 72px;
  overflow: hidden;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  background: #fff;
}

.timeline__grid-line {
  position: absolute;
  inset-block: 0;
  width: 1px;
  background: #e2e8f0;
}

.timeline__block {
  position: absolute;
  top: 13px;
  z-index: 2;
  min-width: 44px;
  height: 46px;
  overflow: hidden;
  padding: 0 10px;
  border: 2px solid transparent;
  border-radius: 9px;
  color: #fff;
  font-weight: 700;
  line-height: 42px;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.timeline__block--selected {
  border-color: #0f172a;
  box-shadow: 0 0 0 2px #fff;
}

.timeline__block--readonly {
  background-image: repeating-linear-gradient(
    135deg,
    transparent,
    transparent 8px,
    rgb(255 255 255 / 20%) 8px,
    rgb(255 255 255 / 20%) 16px
  );
}

.timeline__block--warning {
  border-color: #f59e0b;
  box-shadow: 0 0 0 2px #fef3c7;
}

.timeline__rows {
  display: grid;
  gap: 8px;
}

.timeline__row,
.timeline__axis-row {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.timeline__row-label {
  position: sticky;
  left: 0;
  z-index: 4;
  display: flex;
  align-self: stretch;
  align-items: center;
  box-sizing: border-box;
  overflow: hidden;
  padding: 0 10px;
  background: #f8fafc;
  box-shadow: 10px 0 0 #f8fafc;
  color: #334155;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline__axis-spacer {
  display: block;
}

.timeline__axis {
  position: relative;
  height: 42px;
}

.timeline-warning {
  margin-top: 12px;
}

.timeline__tick {
  position: absolute;
  top: 6px;
  display: grid;
  min-width: 58px;
  color: #475569;
  font-size: 12px;
  transform: translateX(-1px);
}

.timeline__tick small {
  color: #0f172a;
  font-weight: 700;
}

.empty-state,
.timeline-empty {
  margin: 0;
  padding: 26px;
  color: #64748b;
  text-align: center;
}

.timeline-empty {
  position: absolute;
  inset: 16px;
  display: grid;
  place-items: center;
  pointer-events: none;
}

.editor-card {
  display: grid;
  gap: 16px;
}

.editor-grid {
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  align-items: start;
}

.editor-grid--service .service-summary {
  grid-column: 1 / -1;
}

.service-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #f1f5f9;
  color: #475569;
}

.editor-grid__wide {
  grid-column: 1 / -1;
}

.operation-picker {
  z-index: 4;
}

.operation-options,
.search-results {
  display: grid;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 30px rgb(15 23 42 / 12%);
}

.operation-options {
  position: absolute;
  top: calc(100% + 5px);
  right: 0;
  left: 0;
}

.operation-options button,
.search-results button {
  display: grid;
  gap: 3px;
  padding: 11px 12px;
  border: 0;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
}

.operation-options button:hover,
.search-results button:hover {
  background: #eff6ff;
}

.operation-options span,
.search-results span {
  padding: 10px 12px;
  color: #64748b;
}

.order-search {
  display: grid;
  gap: 8px;
  max-width: 520px;
}

.date-range--editor {
  align-self: end;
}

.duration {
  margin: 0;
  color: #334155;
  font-weight: 700;
}

.editor-actions {
  justify-content: flex-end;
}

.editor-actions .button--danger {
  margin-right: auto;
}

@media (max-width: 1100px) {
  .filters,
  .editor-grid {
    grid-template-columns: repeat(2, minmax(220px, 1fr));
  }
}

@media (max-width: 720px) {
  .work-time-panel {
    padding: 16px;
  }

  .panel-head,
  .editor-head,
  .editor-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .filters,
  .editor-grid {
    grid-template-columns: 1fr;
  }

  .editor-actions .button--danger {
    margin-right: 0;
  }
}
</style>
