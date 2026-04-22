<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import flowcraftLogoUrl from "@/shared/assets/flowcraft_logo.png";

import {
  changePassword,
  fetchCurrentSession,
  login,
  logout,
  setupPassword,
  type AuthSession,
} from "@/shared/api/auth";
import {
  createWorkOrder,
  fetchWorkOrder,
  fetchWorkOrders,
  updateWorkOrderAssignments,
  type WorkOrderDetail,
  type WorkOrderSummary,
} from "@/shared/api/orders";
import {
  createProduct,
  deleteProduct,
  fetchProduct,
  fetchProducts,
  updateProductStatus,
  type OperationNode,
  type ProductCreatePayload,
  type ProductDetail,
  type ProductSummary,
} from "@/shared/api/products";
import {
  fetchStatisticsOverview,
  type StatisticsDailyItem,
  type StatisticsOperationItem,
  type StatisticsOrderItem,
  type StatisticsOverview,
  type StatisticsWorkerItem,
} from "@/shared/api/statistics";
import {
  endWorkerDay as endWorkerDayApi,
  fetchWorkerTimerState,
  startWorkerDay as startWorkerDayApi,
  switchWorkerTimer,
  type TimerType,
  type WorkerTimerApiState,
} from "@/shared/api/timers";
import {
  createUser as createUserApi,
  deleteUser as deleteUserApi,
  fetchUsers,
  resetUserPassword as resetUserPasswordApi,
  updateUser as updateUserApi,
  type UserRecord,
  type UserRole,
} from "@/shared/api/users";

type TabId = "worker" | "brigadier" | "constructor" | "stats" | "users";
type ModalMode = "create" | "copy" | "view" | null;
type BrigadierTabId = "active" | "orders";
type ProductVisibilityFilter = "all" | "active" | "inactive";
type ProductSort =
  | "created-desc"
  | "created-asc"
  | "name-asc"
  | "name-desc"
  | "version-asc"
  | "version-desc";
type UserSort = "created-desc" | "created-asc" | "name-asc" | "name-desc";

type FlatOperationNodeRow = {
  id: number;
  name: string;
  level: number;
  isGroup: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  canIndent: boolean;
  canOutdent: boolean;
};

type BrigadierOrderAssignment = {
  operationId: number;
  operationLabel: string;
  workerUserId: number | null;
  workerName: string;
};

type WorkerTimerKind = "preparation" | "break" | "idle" | "operation";

type WorkerTimerDefinition = {
  id: string;
  label: string;
  kind: WorkerTimerKind;
  productKey?: string;
  productLabel?: string;
  orderNumber?: string;
};

type WorkerTimerState = WorkerTimerDefinition & {
  elapsedMs: number;
  startedAtMs: number | null;
};

type WorkerTimerGroup = {
  productKey: string;
  orderNumbers: string[];
  productLabel: string;
  quantity: number;
  timers: WorkerTimerDefinition[];
};

const tabs: Array<{ id: TabId; label: string; icon: string }> = [
  { id: "worker", label: "Исполнитель", icon: "worker" },
  { id: "brigadier", label: "Бригадир", icon: "brigadier" },
  { id: "constructor", label: "Конструктор", icon: "constructor" },
  { id: "stats", label: "Статистика", icon: "stats" },
  { id: "users", label: "Пользователи", icon: "users" },
];

const tabRoles: Record<TabId, UserRole[]> = {
  worker: ["worker"],
  brigadier: ["brigadier"],
  constructor: ["constructor"],
  stats: ["brigadier", "admin"],
  users: ["admin"],
};

const visibilityOptions: Array<{
  value: ProductVisibilityFilter;
  label: string;
  icon: string;
}> = [
  { value: "all", label: "Все изделия", icon: "all" },
  { value: "active", label: "Только активные", icon: "active" },
  { value: "inactive", label: "Только деактивированные", icon: "inactive" },
];

const sortOptions: Array<{
  field: "name" | "version" | "created";
  label: string;
  icon: string;
}> = [
  { field: "name", label: "Сортировка по имени", icon: "name" },
  { field: "version", label: "Сортировка по версии", icon: "version" },
  { field: "created", label: "Сортировка по дате создания", icon: "created" },
];

const userRoleOptions: Array<{
  value: UserRole;
  label: string;
  icon: string;
}> = [
  { value: "worker", label: "Исполнитель", icon: "worker" },
  { value: "brigadier", label: "Бригадир", icon: "brigadier" },
  { value: "constructor", label: "Конструктор", icon: "constructor" },
  { value: "admin", label: "Администратор", icon: "admin" },
];

const userSortOptions: Array<{
  field: "name" | "created";
  label: string;
  icon: string;
}> = [
  { field: "name", label: "Сортировка пользователей по имени", icon: "name" },
  { field: "created", label: "Сортировка пользователей по дате создания", icon: "created" },
];

const statisticsPeriodOptions = [7, 14, 30] as const;

const ACTIVE_TAB_STORAGE_KEY = "flowcraft.active-tab";
const BRIGADIER_TAB_STORAGE_KEY = "flowcraft.brigadier-tab";
const PREPARATION_TIMER_ID = "worker:preparation";
const BREAK_TIMER_ID = "worker:break";
const IDLE_TIMER_ID = "worker:idle";

const activeTab = ref<TabId>(readStoredTab<TabId>(ACTIVE_TAB_STORAGE_KEY, tabs.map((tab) => tab.id), "constructor"));
const brigadierTab = ref<BrigadierTabId>(
  readStoredTab<BrigadierTabId>(BRIGADIER_TAB_STORAGE_KEY, ["active", "orders"], "active"),
);
const modalMode = ref<ModalMode>(null);
const currentSession = ref<AuthSession | null>(null);
const products = ref<ProductSummary[]>([]);
const busyProductIds = ref<number[]>([]);
const users = ref<UserRecord[]>([]);
const workOrders = ref<WorkOrderSummary[]>([]);

const productFilter = ref("");
const productVisibility = ref<ProductVisibilityFilter>("all");
const productSort = ref<ProductSort>("name-asc");
const brigadierProductFilter = ref("");
const brigadierProductSort = ref<ProductSort>("name-asc");
const userFilter = ref("");
const userVisibility = ref<ProductVisibilityFilter>("all");
const userSort = ref<UserSort>("name-asc");
const productName = ref("");
const productVersion = ref("");
const operationTree = ref<OperationNode[]>([]);
const productPendingDelete = ref<ProductSummary | null>(null);
const userPendingDelete = ref<UserRecord | null>(null);
const editingUserId = ref<number | null>(null);
const editingUserDraft = ref<UserRecord | null>(null);
const brigadierModalMode = ref<"create" | "manage" | null>(null);
const brigadierModalProduct = ref<ProductDetail | null>(null);
const brigadierModalOrderId = ref<number | null>(null);
const brigadierModalAssignments = ref<BrigadierOrderAssignment[]>([]);
const brigadierModalQuantity = ref("1");
const brigadierModalOrderNumber = ref("");
const brigadierModalLoading = ref(false);
const brigadierModalError = ref("");
const brigadierOrdersLoading = ref(false);
const brigadierOrdersError = ref("");
const brigadierSaveLoading = ref(false);
const workOrderDetails = ref<WorkOrderDetail[]>([]);
const workerAssignmentsLoading = ref(false);
const workerAssignmentsError = ref("");
const workerTimerSubmitting = ref(false);
const workerDayStartedAt = ref<number | null>(null);
const isWorkerDayEndConfirmOpen = ref(false);
const activeWorkerTimerId = ref<string | null>(null);
const workerTimers = ref<Record<string, WorkerTimerState>>({});
const workerTimerNow = ref(Date.now());
const workerGroupExpanded = ref<Record<string, boolean>>({});
const statisticsPeriodDays = ref<(typeof statisticsPeriodOptions)[number]>(14);
const statisticsLoading = ref(false);
const statisticsError = ref("");
const statisticsOverview = ref<StatisticsOverview | null>(null);

const listLoading = ref(false);
const listError = ref("");
const authInitializing = ref(true);
const authSubmitting = ref(false);
const authError = ref("");
const authPhone = ref("");
const authPassword = ref("");
const authRequiresPasswordSetup = ref(false);
const authSetupUserName = ref("");
const authNewPassword = ref("");
const authConfirmPassword = ref("");
const usersLoading = ref(false);
const usersError = ref("");
const changePasswordModalOpen = ref(false);
const changePasswordCurrent = ref("");
const changePasswordNext = ref("");
const changePasswordConfirm = ref("");
const changePasswordError = ref("");
const changePasswordSaving = ref(false);
const modalLoading = ref(false);
const modalError = ref("");
const saveLoading = ref(false);
const hasAttemptedSubmit = ref(false);

let nextOperationId = 1;
let nextUserId = 100;
let workerClockIntervalId: number | null = null;
const isModalOpen = computed(() => modalMode.value !== null);
const isBrigadierOrderModalOpen = computed(() => brigadierModalMode.value !== null);
const isDeleteModalOpen = computed(() => productPendingDelete.value !== null);
const isUserDeleteModalOpen = computed(() => userPendingDelete.value !== null);
const isViewMode = computed(() => modalMode.value === "view");
const availableTabs = computed(() => {
  if (!currentSession.value) {
    return [] as Array<{ id: TabId; label: string; icon: string }>;
  }

  return tabs.filter((tab) =>
    tabRoles[tab.id].some((role) => currentSession.value?.userRoles.includes(role)),
  );
});

const canViewStatistics = computed(
  () =>
    currentSession.value?.userRoles.includes("brigadier") ||
    currentSession.value?.userRoles.includes("admin") ||
    false,
);

const shouldShowValidation = computed(
  () => modalMode.value === "create" || modalMode.value === "copy",
);
const operationErrors = computed(() => validateOperationTree(operationTree.value));
const hasOperationErrors = computed(
  () => Object.keys(operationErrors.value).length > 0,
);
const firstOperationErrorRow = computed(() =>
  flatOperationRows.value.find((row) => Boolean(operationErrors.value[row.id])),
);

const productNameError = computed(() =>
  productName.value.trim() ? "" : "Укажите наименование изделия.",
);

const productVersionError = computed(() =>
  productVersion.value.trim() ? "" : "Укажите версию изделия.",
);

const productIdentityError = computed(() => {
  const normalizedName = normalizeName(productName.value);
  const normalizedVersion = normalizeName(productVersion.value);

  if (!normalizedName || !normalizedVersion || modalMode.value === "view") {
    return "";
  }

  const duplicate = products.value.some(
    (product) =>
      normalizeName(product.name) === normalizedName &&
      normalizeName(product.version) === normalizedVersion,
  );

  return duplicate ? "Изделие с таким именем и версией уже существует." : "";
});

const operationTreeError = computed(() =>
  operationTree.value.length > 0 ? "" : "Добавьте хотя бы одну операцию.",
);

const canSaveProduct = computed(
  () =>
    !isViewMode.value &&
    !productNameError.value &&
    !productVersionError.value &&
    !productIdentityError.value &&
    !operationTreeError.value &&
    !hasOperationErrors.value,
);

const saveBlockIssue = computed<{
  message: string;
  selector: string;
} | null>(() => {
  if (productIdentityError.value) {
    return {
      message: productIdentityError.value,
      selector: '[data-field="product-version"]',
    };
  }

  if (shouldShowValidation.value && productNameError.value) {
    return {
      message: productNameError.value,
      selector: '[data-field="product-name"]',
    };
  }

  if (shouldShowValidation.value && productVersionError.value) {
    return {
      message: productVersionError.value,
      selector: '[data-field="product-version"]',
    };
  }

  if (hasOperationErrors.value && firstOperationErrorRow.value) {
    return {
      message: operationErrors.value[firstOperationErrorRow.value.id],
      selector: `[data-operation-id="${firstOperationErrorRow.value.id}"]`,
    };
  }

  if (shouldShowValidation.value && operationTreeError.value) {
    return {
      message: operationTreeError.value,
      selector: '[data-field="add-root-operation"]',
    };
  }

  return null;
});

const modalTitle = computed(() => {
  if (modalMode.value === "copy") {
    return "Копия изделия";
  }

  if (modalMode.value === "view") {
    return "Просмотр изделия";
  }

  return "Новое изделие";
});

const modalDescription = computed(() => {
  if (modalMode.value === "copy") {
    return "Форма предзаполнена текущим изделием и его деревом операций.";
  }

  if (modalMode.value === "view") {
    return "Просмотр состава операций без возможности редактирования.";
  }

  return "Заполните карточку изделия и задайте дерево производственных операций.";
});

const flatOperationRows = computed<FlatOperationNodeRow[]>(() =>
  flattenOperations(operationTree.value),
);

const filteredProducts = computed(() => {
  const normalizedFilter = productFilter.value.trim().toLowerCase();

  const filtered = products.value.filter((product) => {
    const matchesName = product.name.toLowerCase().includes(normalizedFilter);
    const matchesVisibility =
      productVisibility.value === "all" ||
      (productVisibility.value === "active" && product.isActive) ||
      (productVisibility.value === "inactive" && !product.isActive);

    return matchesName && matchesVisibility;
  });

  return [...filtered].sort((left, right) =>
    compareProducts(left, right, productSort.value),
  );
});

const filteredUsers = computed(() => {
  const normalizedFilter = userFilter.value.trim().toLowerCase();

  const filtered = users.value.filter((user) => {
    const matchesName = user.name.toLowerCase().includes(normalizedFilter);
    const matchesVisibility =
      userVisibility.value === "all" ||
      (userVisibility.value === "active" && user.isActive) ||
      (userVisibility.value === "inactive" && !user.isActive);

    return matchesName && matchesVisibility;
  });

  return [...filtered].sort((left, right) => compareUsers(left, right, userSort.value));
});

const brigadierWorkerUsers = computed(() =>
  [...users.value]
    .filter((user) => user.roles.includes("worker") && user.isActive)
    .sort((left, right) => left.name.localeCompare(right.name, "ru")),
);

const filteredBrigadierProducts = computed(() => {
  const normalizedFilter = brigadierProductFilter.value.trim().toLowerCase();
  const filtered = products.value.filter(
    (product) =>
      product.isActive &&
      product.name.toLowerCase().includes(normalizedFilter),
  );

  return [...filtered].sort((left, right) =>
    compareProducts(left, right, brigadierProductSort.value),
  );
});

const brigadierCurrentOrder = computed(() =>
  workOrders.value.find((order) => order.id === brigadierModalOrderId.value) ?? null,
);

const brigadierModalTitle = computed(() =>
  brigadierModalMode.value === "manage" ? "Заказ в работе" : "Новый заказ",
);

const brigadierModalDescription = computed(() =>
  brigadierModalMode.value === "manage"
    ? "Просмотр текущего заказа с возможностью изменить назначенных исполнителей."
    : "Укажите количество изделий и распределите исполнителей по операциям.",
);

const brigadierModalSaveLabel = computed(() =>
  brigadierModalMode.value === "manage" ? "Сохранить изменения" : "Сохранить заказ",
);

const brigadierOrderNumberError = computed(() => {
  const normalizedOrderNumber = brigadierModalOrderNumber.value.trim();

  if (!normalizedOrderNumber) {
    return "Укажите номер заказа.";
  }

  const duplicate = workOrders.value.some(
    (order) =>
      order.id !== brigadierModalOrderId.value &&
      normalizeName(order.orderNumber) === normalizeName(normalizedOrderNumber),
  );

  return duplicate ? "Заказ с таким номером уже существует." : "";
});

const brigadierQuantityError = computed(() => {
  const quantity = Number.parseInt(brigadierModalQuantity.value, 10);

  return Number.isInteger(quantity) && quantity > 0
    ? ""
    : "Укажите количество изделий больше нуля.";
});

const firstBrigadierAssignmentError = computed(() =>
  brigadierModalAssignments.value.find((assignment) => assignment.workerUserId === null) ?? null,
);

const brigadierSaveIssue = computed<{
  message: string;
  selector: string;
} | null>(() => {
  if (brigadierOrderNumberError.value) {
    return {
      message: brigadierOrderNumberError.value,
      selector: '[data-field="brigadier-order-number"]',
    };
  }

  if (brigadierQuantityError.value) {
    return {
      message: brigadierQuantityError.value,
      selector: '[data-field="brigadier-quantity"]',
    };
  }

  if (firstBrigadierAssignmentError.value) {
    return {
      message: getBrigadierAssignmentError(firstBrigadierAssignmentError.value),
      selector: `[data-brigadier-operation-id="${firstBrigadierAssignmentError.value.operationId}"]`,
    };
  }

  return null;
});

const brigadierModalCanSave = computed(() => {
  return (
    Boolean(brigadierModalProduct.value) &&
    !brigadierOrderNumberError.value &&
    !brigadierQuantityError.value &&
    brigadierModalAssignments.value.length > 0 &&
    brigadierModalAssignments.value.every((assignment) => assignment.workerUserId !== null)
  );
});

const currentWorker = computed(() => {
  if (!currentSession.value || !currentSession.value.userRoles.includes("worker")) {
    return null;
  }

  return users.value.find((user) => user.id === currentSession.value?.userId && user.isActive) ?? null;
});

const staticWorkerTimerDefinitions = computed<WorkerTimerDefinition[]>(() => [
  {
    id: PREPARATION_TIMER_ID,
    label: "Подготовка",
    kind: "preparation",
  },
  {
    id: BREAK_TIMER_ID,
    label: "Перерыв",
    kind: "break",
  },
  {
    id: IDLE_TIMER_ID,
    label: "Простой",
    kind: "idle",
  },
]);

const assignedWorkerTimerDefinitions = computed<WorkerTimerDefinition[]>(() => {
  if (!currentWorker.value) {
    return [];
  }

  return workOrderDetails.value.flatMap((order) =>
    order.assignments
      .filter((assignment) => assignment.workerUserId === currentWorker.value?.id)
      .map((assignment) => ({
        id: `worker:operation:${order.id}:${assignment.operationId}`,
        label: assignment.operationName,
        kind: "operation" as const,
        productKey: `${order.productName}:::${order.productVersion}`,
        productLabel: `${order.productName} · ${order.productVersion}`,
        orderNumber: order.orderNumber,
      })),
  );
});

const workerTimerDefinitions = computed<WorkerTimerDefinition[]>(() => [
  ...staticWorkerTimerDefinitions.value,
  ...assignedWorkerTimerDefinitions.value,
]);

const workerTimerGroups = computed<WorkerTimerGroup[]>(() => {
  const groups = new Map<string, WorkerTimerGroup>();
  const quantitiesByGroup = new Map<string, number>();
  const orderNumbersByGroup = new Map<string, string[]>();

  for (const order of workOrderDetails.value) {
    if (
      !currentWorker.value ||
      !order.assignments.some(
        (assignment) => assignment.workerUserId === currentWorker.value?.id,
      )
    ) {
      continue;
    }

    const productKey = `${order.productName}:::${order.productVersion}`;
    quantitiesByGroup.set(
      productKey,
      (quantitiesByGroup.get(productKey) ?? 0) + order.quantity,
    );
    orderNumbersByGroup.set(productKey, [
      ...(orderNumbersByGroup.get(productKey) ?? []),
      order.orderNumber,
    ]);
  }

  for (const timer of assignedWorkerTimerDefinitions.value) {
    if (!timer.productKey || !timer.productLabel) {
      continue;
    }

    const existingGroup = groups.get(timer.productKey);
    if (existingGroup) {
      existingGroup.timers.push(timer);
      continue;
    }

    groups.set(timer.productKey, {
      productKey: timer.productKey,
      orderNumbers: [...new Set(orderNumbersByGroup.get(timer.productKey) ?? [])],
      productLabel: timer.productLabel,
      quantity: quantitiesByGroup.get(timer.productKey) ?? 0,
      timers: [timer],
    });
  }

  return [...groups.values()];
});

const workerPrimaryTimers = computed(() =>
  staticWorkerTimerDefinitions.value.filter((timer) => timer.kind !== "idle"),
);

const workerIdleTimer = computed(
  () => staticWorkerTimerDefinitions.value.find((timer) => timer.kind === "idle") ?? null,
);

const isWorkerDayActive = computed(() => workerDayStartedAt.value !== null);

const workerDayElapsedMs = computed(() => {
  if (workerDayStartedAt.value === null) {
    return 0;
  }

  return workerTimerNow.value - workerDayStartedAt.value;
});

const workerActiveTimer = computed(() =>
  activeWorkerTimerId.value ? workerTimers.value[activeWorkerTimerId.value] ?? null : null,
);

const statisticsDailyMax = computed(() =>
  Math.max(...(statisticsOverview.value?.dailyBreakdown.map((item) => item.totalMs) ?? [0]), 1),
);

const statisticsOperationMax = computed(() =>
  Math.max(...(statisticsOverview.value?.topOperations.map((item) => item.totalMs) ?? [0]), 1),
);

const statisticsOrderMax = computed(() =>
  Math.max(...(statisticsOverview.value?.topOrders.map((item) => item.totalMs) ?? [0]), 1),
);

const statisticsWorkerMax = computed(() =>
  Math.max(...(statisticsOverview.value?.workers.map((item) => item.totalMs) ?? [0]), 1),
);

const statisticsIdleMax = computed(() =>
  Math.max(...(statisticsOverview.value?.idleByDay.map((item) => item.idleMs) ?? [0]), 1),
);

onMounted(async () => {
  await initializePage();
  window.addEventListener("keydown", handleWindowKeydown);
  const intervalId = window.setInterval(() => {
    workerTimerNow.value = Date.now();
  }, 1000);
  workerClockIntervalId = intervalId;
});

watch(activeTab, (value) => {
  storeTab(ACTIVE_TAB_STORAGE_KEY, value);
});

watch(availableTabs, (nextTabs) => {
  if (!nextTabs.length) {
    return;
  }

  if (!nextTabs.some((tab) => tab.id === activeTab.value)) {
    activeTab.value = nextTabs[0].id;
  }
}, { immediate: true });

watch(brigadierTab, (value) => {
  storeTab(BRIGADIER_TAB_STORAGE_KEY, value);
});

watch(
  workerTimerDefinitions,
  (definitions) => {
    syncWorkerTimers(definitions);
  },
  { immediate: true },
);

watch(
  workerTimerGroups,
  (groups) => {
    const nextExpanded: Record<string, boolean> = {};

    for (const group of groups) {
      nextExpanded[group.productKey] = workerGroupExpanded.value[group.productKey] ?? false;
    }

    workerGroupExpanded.value = nextExpanded;
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleWindowKeydown);
  if (workerClockIntervalId !== null) {
    window.clearInterval(workerClockIntervalId);
  }
});

function setActiveTab(tabId: TabId) {
  activeTab.value = tabId;
}

function isSortFieldActive(field: "name" | "version" | "created"): boolean {
  return productSort.value.startsWith(field);
}

function getSortDirection(field: "name" | "version" | "created"): "asc" | "desc" {
  if (!isSortFieldActive(field)) {
    return field === "created" ? "desc" : "asc";
  }

  return productSort.value.endsWith("asc") ? "asc" : "desc";
}

function toggleProductSort(field: "name" | "version" | "created") {
  const nextDirection = isSortFieldActive(field)
    ? getSortDirection(field) === "asc"
      ? "desc"
      : "asc"
    : field === "created"
      ? "desc"
      : "asc";

  productSort.value = `${field}-${nextDirection}` as ProductSort;
}

function isUserSortFieldActive(field: "name" | "created"): boolean {
  return userSort.value.startsWith(field);
}

function getUserSortDirection(field: "name" | "created"): "asc" | "desc" {
  if (!isUserSortFieldActive(field)) {
    return field === "created" ? "desc" : "asc";
  }

  return userSort.value.endsWith("asc") ? "asc" : "desc";
}

function toggleUserSort(field: "name" | "created") {
  const nextDirection = isUserSortFieldActive(field)
    ? getUserSortDirection(field) === "asc"
      ? "desc"
      : "asc"
    : field === "created"
      ? "desc"
      : "asc";

  userSort.value = `${field}-${nextDirection}` as UserSort;
}

function isBrigadierSortFieldActive(field: "name" | "version" | "created"): boolean {
  return brigadierProductSort.value.startsWith(field);
}

function getBrigadierSortDirection(
  field: "name" | "version" | "created",
): "asc" | "desc" {
  if (!isBrigadierSortFieldActive(field)) {
    return field === "created" ? "desc" : "asc";
  }

  return brigadierProductSort.value.endsWith("asc") ? "asc" : "desc";
}

function toggleBrigadierSort(field: "name" | "version" | "created") {
  const nextDirection = isBrigadierSortFieldActive(field)
    ? getBrigadierSortDirection(field) === "asc"
      ? "desc"
      : "asc"
    : field === "created"
      ? "desc"
      : "asc";

  brigadierProductSort.value = `${field}-${nextDirection}` as ProductSort;
}

async function initializePage() {
  authInitializing.value = true;

  try {
    currentSession.value = await fetchCurrentSession();
    await loadProtectedData();
  } catch {
    currentSession.value = null;
  } finally {
    authInitializing.value = false;
  }
}

async function loadProtectedData() {
  await Promise.all([loadProducts(), loadUsers(), loadWorkOrders()]);

  if (currentSession.value?.userRoles.includes("worker")) {
    await loadWorkerTimerState();
  } else {
    resetWorkerTimerState();
  }

  if (canViewStatistics.value) {
    await loadStatistics();
  } else {
    statisticsOverview.value = null;
    statisticsError.value = "";
  }
}

function isUnauthorizedError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  return (
    error.message.includes("Требуется аутентификация") ||
    error.message.includes("Сессия истекла")
  );
}

function redirectToAuth(message = "Требуется аутентификация.") {
  currentSession.value = null;
  authInitializing.value = false;
  authSubmitting.value = false;
  authRequiresPasswordSetup.value = false;
  authPassword.value = "";
  authNewPassword.value = "";
  authConfirmPassword.value = "";
  authError.value = message;
  closeChangePasswordModal();
  closeBrigadierOrderModal();
  closeProductModal();
  closeDeleteConfirmation();
  closeUserDeleteConfirmation();
}

async function submitAuthentication() {
  authSubmitting.value = true;
  authError.value = "";

  try {
    if (authRequiresPasswordSetup.value) {
      if (authNewPassword.value.length < 8) {
        authError.value = "Новый пароль должен содержать не менее 8 символов.";
        return;
      }

      if (authNewPassword.value !== authConfirmPassword.value) {
        authError.value = "Подтверждение пароля не совпадает.";
        return;
      }

      currentSession.value = await setupPassword(
        authPhone.value.trim(),
        authNewPassword.value,
      );
    } else {
      const loginResult = await login(authPhone.value.trim(), authPassword.value);

      if (loginResult.status === "password_setup_required") {
        authRequiresPasswordSetup.value = true;
        authSetupUserName.value = loginResult.userName ?? "";
        authPassword.value = "";
        return;
      }

      currentSession.value = loginResult.session;
    }

    authRequiresPasswordSetup.value = false;
    authSetupUserName.value = "";
    authPassword.value = "";
    authNewPassword.value = "";
    authConfirmPassword.value = "";
    authError.value = "";
    await loadProtectedData();
  } catch (error) {
    authError.value = getErrorMessage(error, "Не удалось пройти аутентификацию.");
  } finally {
    authSubmitting.value = false;
  }
}

async function handleLogout() {
  try {
    await logout();
  } finally {
    redirectToAuth("Сессия завершена.");
  }
}

function openChangePasswordModal() {
  changePasswordModalOpen.value = true;
  changePasswordCurrent.value = "";
  changePasswordNext.value = "";
  changePasswordConfirm.value = "";
  changePasswordError.value = "";
  changePasswordSaving.value = false;
}

function closeChangePasswordModal() {
  changePasswordModalOpen.value = false;
  changePasswordCurrent.value = "";
  changePasswordNext.value = "";
  changePasswordConfirm.value = "";
  changePasswordError.value = "";
  changePasswordSaving.value = false;
}

async function submitPasswordChange() {
  if (!currentSession.value) {
    redirectToAuth();
    return;
  }

  if (changePasswordNext.value.length < 8) {
    changePasswordError.value = "Новый пароль должен содержать не менее 8 символов.";
    return;
  }

  if (changePasswordNext.value !== changePasswordConfirm.value) {
    changePasswordError.value = "Подтверждение пароля не совпадает.";
    return;
  }

  changePasswordSaving.value = true;
  changePasswordError.value = "";

  try {
    currentSession.value = await changePassword(
      changePasswordCurrent.value === "" ? null : changePasswordCurrent.value,
      changePasswordNext.value,
    );
    closeChangePasswordModal();
  } catch (error) {
    changePasswordError.value = getErrorMessage(error, "Не удалось изменить пароль.");
  } finally {
    changePasswordSaving.value = false;
  }
}

async function loadProducts() {
  listLoading.value = true;
  listError.value = "";

  try {
    products.value = await fetchProducts();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    listError.value = getErrorMessage(error, "Не удалось загрузить изделия.");
  } finally {
    listLoading.value = false;
  }
}

async function loadUsers() {
  usersLoading.value = true;
  usersError.value = "";

  try {
    users.value = await fetchUsers();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    usersError.value = getErrorMessage(error, "Не удалось загрузить пользователей.");
  } finally {
    usersLoading.value = false;
  }
}

async function loadWorkOrders() {
  brigadierOrdersLoading.value = true;
  brigadierOrdersError.value = "";
  workerAssignmentsError.value = "";

  try {
    const orders = await fetchWorkOrders();
    workOrders.value = orders;
    await loadWorkOrderDetails(orders);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierOrdersError.value = getErrorMessage(error, "Не удалось загрузить заказы.");
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось загрузить назначения исполнителя.",
    );
  } finally {
    brigadierOrdersLoading.value = false;
  }
}

async function loadWorkOrderDetails(orders: WorkOrderSummary[]) {
  workerAssignmentsLoading.value = true;

  try {
    workOrderDetails.value = await Promise.all(
      orders.map((order) => fetchWorkOrder(order.id)),
    );
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workOrderDetails.value = [];
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось загрузить назначения исполнителя.",
    );
  } finally {
    workerAssignmentsLoading.value = false;
  }
}

async function loadWorkerTimerState() {
  workerTimerSubmitting.value = true;

  try {
    applyWorkerTimerApiState(await fetchWorkerTimerState());
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось загрузить состояние таймеров.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

async function loadStatistics() {
  statisticsLoading.value = true;
  statisticsError.value = "";

  try {
    statisticsOverview.value = await fetchStatisticsOverview(statisticsPeriodDays.value);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    statisticsError.value = getErrorMessage(error, "Не удалось загрузить статистику.");
  } finally {
    statisticsLoading.value = false;
  }
}

function resetForm() {
  hasAttemptedSubmit.value = false;
  modalError.value = "";
  productName.value = "";
  productVersion.value = "";
  operationTree.value = [];
  nextOperationId = 1;
}

function startCreateProduct() {
  modalMode.value = "create";
  modalLoading.value = false;
  saveLoading.value = false;
  resetForm();
}

async function startCopyProduct(productId: number) {
  await openProductModal(productId, "copy");
}

async function startViewProduct(productId: number) {
  await openProductModal(productId, "view");
}

async function openProductModal(productId: number, mode: Exclude<ModalMode, "create" | null>) {
  modalMode.value = mode;
  modalLoading.value = true;
  saveLoading.value = false;
  resetForm();

  try {
    const product = await fetchProduct(productId);
    fillFormFromProduct(product);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    modalError.value = getErrorMessage(error, "Не удалось загрузить изделие.");
  } finally {
    modalLoading.value = false;
  }
}

function closeProductModal() {
  modalMode.value = null;
  modalLoading.value = false;
  saveLoading.value = false;
  hasAttemptedSubmit.value = false;
  modalError.value = "";
}

function openDeleteConfirmation(product: ProductSummary) {
  productPendingDelete.value = product;
}

function closeDeleteConfirmation() {
  productPendingDelete.value = null;
}

function openUserDeleteConfirmation(user: UserRecord) {
  if (editingUserId.value !== null && editingUserId.value !== user.id) {
    return;
  }

  userPendingDelete.value = user;
}

function closeUserDeleteConfirmation() {
  userPendingDelete.value = null;
}

function setBrigadierTab(tabId: BrigadierTabId) {
  brigadierTab.value = tabId;
}

function syncWorkerTimers(definitions: WorkerTimerDefinition[]) {
  const nextTimers: Record<string, WorkerTimerState> = {};

  for (const definition of definitions) {
    const existingTimer = workerTimers.value[definition.id];
    nextTimers[definition.id] = existingTimer
      ? {
          ...existingTimer,
          ...definition,
        }
      : {
          ...definition,
          elapsedMs: 0,
          startedAtMs: null,
        };
  }

  if (activeWorkerTimerId.value && !nextTimers[activeWorkerTimerId.value]) {
    activeWorkerTimerId.value = null;
  }

  workerTimers.value = nextTimers;
}

function resetWorkerTimerState() {
  workerDayStartedAt.value = null;
  activeWorkerTimerId.value = null;
  workerTimers.value = {};
  workerTimerNow.value = Date.now();
}

function getTimerIdForApiTarget(target: {
  timerType: TimerType;
  orderId?: number | null;
  operationId?: number | null;
}): string | null {
  switch (target.timerType) {
    case "preparation":
      return PREPARATION_TIMER_ID;
    case "break":
      return BREAK_TIMER_ID;
    case "idle":
      return IDLE_TIMER_ID;
    case "operation":
      return target.orderId != null && target.operationId != null
        ? `worker:operation:${target.orderId}:${target.operationId}`
        : null;
  }
}

function applyWorkerTimerApiState(state: WorkerTimerApiState) {
  const now = Date.now();
  const nextTimers: Record<string, WorkerTimerState> = {};

  for (const definition of workerTimerDefinitions.value) {
    nextTimers[definition.id] = {
      ...definition,
      elapsedMs: 0,
      startedAtMs: null,
    };
  }

  for (const aggregate of state.timerTotals) {
    const timerId = getTimerIdForApiTarget(aggregate);
    if (!timerId || !nextTimers[timerId]) {
      continue;
    }

    nextTimers[timerId].elapsedMs = aggregate.elapsedMs;
  }

  let activeTimerId: string | null = null;
  if (state.activeTimer) {
    const nextActiveTimerId = getTimerIdForApiTarget(state.activeTimer);
    if (nextActiveTimerId && nextTimers[nextActiveTimerId]) {
      const activeElapsedMs = Math.max(0, now - state.activeTimer.startedAtTs);
      nextTimers[nextActiveTimerId].elapsedMs = Math.max(
        0,
        nextTimers[nextActiveTimerId].elapsedMs - activeElapsedMs,
      );
      nextTimers[nextActiveTimerId].startedAtMs = state.activeTimer.startedAtTs;
      activeTimerId = nextActiveTimerId;
    }
  }

  workerTimers.value = nextTimers;
  workerDayStartedAt.value = state.shift?.startedAtTs ?? null;
  activeWorkerTimerId.value = activeTimerId;
  workerTimerNow.value = now;
}

function handleWindowKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") {
    return;
  }

  if (changePasswordModalOpen.value) {
    closeChangePasswordModal();
    return;
  }

  if (isWorkerDayEndConfirmOpen.value) {
    closeWorkerDayEndConfirm();
    return;
  }

  if (editingUserId.value !== null) {
    cancelUserEdit();
    return;
  }

  if (isUserDeleteModalOpen.value) {
    closeUserDeleteConfirmation();
    return;
  }

  if (isDeleteModalOpen.value) {
    closeDeleteConfirmation();
    return;
  }

  if (isBrigadierOrderModalOpen.value) {
    closeBrigadierOrderModal();
    return;
  }

  if (isModalOpen.value) {
    closeProductModal();
  }
}

function fillFormFromProduct(product: ProductDetail) {
  hasAttemptedSubmit.value = false;
  productName.value = product.name;
  productVersion.value = product.version;
  operationTree.value = cloneOperations(product.operations);
  nextOperationId = getMaxOperationId(operationTree.value) + 1;
}

async function startWorkerDay() {
  if (!currentWorker.value) {
    return;
  }

  workerTimerSubmitting.value = true;
  workerAssignmentsError.value = "";

  try {
    applyWorkerTimerApiState(await startWorkerDayApi());
    await loadWorkOrders();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось начать рабочий день.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

function requestEndWorkerDay() {
  if (workerDayStartedAt.value === null) {
    return;
  }

  isWorkerDayEndConfirmOpen.value = true;
}

function closeWorkerDayEndConfirm() {
  isWorkerDayEndConfirmOpen.value = false;
}

async function endWorkerDay() {
  if (workerDayStartedAt.value === null) {
    return;
  }

  workerTimerSubmitting.value = true;
  workerAssignmentsError.value = "";

  try {
    applyWorkerTimerApiState(await endWorkerDayApi());
    await loadWorkOrders();
    closeWorkerDayEndConfirm();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось завершить рабочий день.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

async function activateWorkerTimer(timerId: string) {
  if (workerDayStartedAt.value === null) {
    return;
  }

  const timer = workerTimers.value[timerId];

  if (!timer || activeWorkerTimerId.value === timerId) {
    return;
  }

  workerTimerSubmitting.value = true;
  workerAssignmentsError.value = "";

  try {
    applyWorkerTimerApiState(
      await switchWorkerTimer(timer.kind, {
        orderId: parseOrderIdFromTimerId(timerId),
        operationId: parseOperationIdFromTimerId(timerId),
      }),
    );
    await loadWorkOrders();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось переключить таймер.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

function getWorkerTimerElapsedMs(timerId: string): number {
  const timer = workerTimers.value[timerId];

  if (!timer) {
    return 0;
  }

  if (timer.startedAtMs === null) {
    return timer.elapsedMs;
  }

  return timer.elapsedMs + (workerTimerNow.value - timer.startedAtMs);
}

function isWorkerTimerActive(timerId: string): boolean {
  return activeWorkerTimerId.value === timerId;
}

function toggleWorkerGroup(productKey: string) {
  workerGroupExpanded.value = {
    ...workerGroupExpanded.value,
    [productKey]: !workerGroupExpanded.value[productKey],
  };
}

async function toggleProductStatus(product: ProductSummary) {
  setProductBusy(product.id, true);

  try {
    const updatedProduct = await updateProductStatus(product.id, !product.isActive);
    replaceProductSummary(updatedProduct);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    listError.value = getErrorMessage(error, "Не удалось обновить статус изделия.");
  } finally {
    setProductBusy(product.id, false);
  }
}

async function handleDeleteProduct(product: ProductSummary) {
  if (productPendingDelete.value?.id !== product.id) {
    return;
  }

  setProductBusy(product.id, true);

  try {
    await deleteProduct(product.id);
    products.value = products.value.filter((item) => item.id !== product.id);
    closeDeleteConfirmation();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    listError.value = getErrorMessage(error, "Не удалось удалить изделие.");
  } finally {
    setProductBusy(product.id, false);
  }
}

function startCreateUser() {
  if (editingUserId.value !== null) {
    return;
  }

  const user = createUserRecord({
    id: nextUserId,
    name: "",
    phone: "",
    passwordHash: null,
    author: getDefaultAuthorName(),
    authorUserId: getDefaultAuthorUserId(),
    roles: [],
    isActive: true,
    createdAtTs: null,
    updatedAtTs: null,
    deletedAtTs: null,
    isNew: true,
  });

  nextUserId += 1;
  users.value = [user, ...users.value];
  userFilter.value = "";
  userVisibility.value = "all";
  userPendingDelete.value = null;
  startEditUser(user);
}

function startEditUser(user: UserRecord) {
  if (editingUserId.value !== null && editingUserId.value !== user.id) {
    return;
  }

  editingUserId.value = user.id;
  editingUserDraft.value = cloneUser(user);
}

function cancelUserEdit() {
  if (editingUserId.value === null) {
    return;
  }

  const currentUser = users.value.find((user) => user.id === editingUserId.value);

  if (currentUser?.isNew) {
    users.value = users.value.filter((user) => user.id !== currentUser.id);
  }

  editingUserId.value = null;
  editingUserDraft.value = null;
}

function isEditingUser(userId: number): boolean {
  return editingUserId.value === userId && editingUserDraft.value !== null;
}

function isUserLocked(userId: number): boolean {
  return editingUserId.value !== null && editingUserId.value !== userId;
}

function getDisplayedUser(user: UserRecord): UserRecord {
  return isEditingUser(user.id) && editingUserDraft.value ? editingUserDraft.value : user;
}

function toggleUserRole(userId: number, role: UserRole) {
  if (!isEditingUser(userId) || !editingUserDraft.value) {
    return;
  }

  const hasRole = editingUserDraft.value.roles.includes(role);

  editingUserDraft.value = {
    ...editingUserDraft.value,
    roles: hasRole
      ? editingUserDraft.value.roles.filter((item) => item !== role)
      : [...editingUserDraft.value.roles, role],
  };
}

function handleUserRoleAction(user: UserRecord, role: UserRole) {
  if (isUserLocked(user.id)) {
    return;
  }

  if (!isEditingUser(user.id)) {
    startEditUser(user);
  }

  toggleUserRole(user.id, role);
}

function toggleUserStatus(userId: number) {
  if (!isEditingUser(userId) || !editingUserDraft.value) {
    return;
  }

  editingUserDraft.value = {
    ...editingUserDraft.value,
    isActive: !editingUserDraft.value.isActive,
  };
}

function handleUserStatusAction(user: UserRecord) {
  if (isUserLocked(user.id)) {
    return;
  }

  if (!isEditingUser(user.id)) {
    startEditUser(user);
  }

  toggleUserStatus(user.id);
}

function handleUserNameInput(userId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement) || !isEditingUser(userId) || !editingUserDraft.value) {
    return;
  }

  editingUserDraft.value = {
    ...editingUserDraft.value,
    name: target.value,
  };
}

function handleUserPhoneInput(userId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement) || !isEditingUser(userId) || !editingUserDraft.value) {
    return;
  }

  editingUserDraft.value = {
    ...editingUserDraft.value,
    phone: target.value,
  };
}

function hasUserDraftChanges(user: UserRecord): boolean {
  if (!isEditingUser(user.id) || !editingUserDraft.value) {
    return false;
  }

  return (
    editingUserDraft.value.name !== user.name ||
    editingUserDraft.value.phone !== user.phone ||
    editingUserDraft.value.isActive !== user.isActive ||
    !areRolesEqual(editingUserDraft.value.roles, user.roles)
  );
}

function canSaveUser(user: UserRecord): boolean {
  if (!isEditingUser(user.id) || !editingUserDraft.value) {
    return false;
  }

  return (
    Boolean(editingUserDraft.value.name.trim()) &&
    Boolean(editingUserDraft.value.phone.trim()) &&
    editingUserDraft.value.roles.length > 0 &&
    hasUserDraftChanges(user)
  );
}

function saveUserChanges(user: UserRecord) {
  if (!isEditingUser(user.id) || !editingUserDraft.value || !canSaveUser(user)) {
    return;
  }

  void persistUserChanges(user);
}

function deleteUser(user: UserRecord) {
  if (userPendingDelete.value?.id !== user.id) {
    return;
  }

  void removeUser(user);
}

function getUserNameError(user: UserRecord): string {
  if (!isEditingUser(user.id) || !editingUserDraft.value || editingUserDraft.value.name.trim()) {
    return "";
  }

  return "Укажите имя пользователя.";
}

function getUserRolesError(user: UserRecord): string {
  if (!isEditingUser(user.id) || !editingUserDraft.value || editingUserDraft.value.roles.length > 0) {
    return "";
  }

  return "Выберите хотя бы одну роль.";
}

function getUserPhoneError(user: UserRecord): string {
  if (!isEditingUser(user.id) || !editingUserDraft.value || editingUserDraft.value.phone.trim()) {
    return "";
  }

  return "Укажите номер телефона.";
}

async function saveProductToApi() {
  hasAttemptedSubmit.value = true;

  if (!canSaveProduct.value) {
    scrollToSaveBlockIssue();
    return;
  }

  saveLoading.value = true;
  modalError.value = "";

  try {
    const payload: ProductCreatePayload = {
      name: productName.value.trim(),
      version: productVersion.value.trim(),
      author_user_id: currentSession.value?.userId ?? null,
      operations: serializeOperations(operationTree.value),
    };

    await createProduct(payload);
    await loadProducts();
    closeProductModal();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    modalError.value = getErrorMessage(error, "Не удалось сохранить изделие.");
  } finally {
    saveLoading.value = false;
  }
}

function addRootOperation() {
  operationTree.value = [...operationTree.value, createOperationNode()];
}

function addChildOperation(parentId: number) {
  operationTree.value = appendChildOperation(operationTree.value, parentId);
}

function addSiblingOperation(operationId: number) {
  operationTree.value = appendSiblingOperation(operationTree.value, operationId);
}

function moveOperationUp(operationId: number) {
  operationTree.value = reorderOperationInParent(operationTree.value, operationId, -1);
}

function moveOperationDown(operationId: number) {
  operationTree.value = reorderOperationInParent(operationTree.value, operationId, 1);
}

function indentOperation(operationId: number) {
  operationTree.value = indentOperationNode(operationTree.value, operationId);
}

function outdentOperation(operationId: number) {
  operationTree.value = outdentOperationNode(operationTree.value, operationId);
}

function removeOperation(operationId: number) {
  operationTree.value = deleteOperation(operationTree.value, operationId);
}

function handleOperationNameInput(operationId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  operationTree.value = renameOperation(operationTree.value, operationId, target.value);
}

function shouldShowFieldError(value: string, error: string): boolean {
  return Boolean(error) && (shouldShowValidation.value || value.length > 0);
}

function shouldShowOperationError(row: FlatOperationNodeRow): boolean {
  return (
    Boolean(operationErrors.value[row.id]) &&
    (
      shouldShowValidation.value ||
      row.name.length > 0 ||
      saveBlockIssue.value?.selector === `[data-operation-id="${row.id}"]`
    )
  );
}

function scrollToSaveBlockIssue() {
  const selector = saveBlockIssue.value?.selector;

  if (!selector) {
    return;
  }

  const target = document.querySelector<HTMLElement>(selector);

  if (!target) {
    return;
  }

  target.scrollIntoView({
    behavior: "smooth",
    block: "center",
    inline: "nearest",
  });

  if (target instanceof HTMLInputElement || target instanceof HTMLButtonElement) {
    target.focus({ preventScroll: true });
  }
}

function isProductBusy(productId: number): boolean {
  return busyProductIds.value.includes(productId);
}

function setProductBusy(productId: number, isBusy: boolean) {
  if (isBusy) {
    if (!busyProductIds.value.includes(productId)) {
      busyProductIds.value = [...busyProductIds.value, productId];
    }
    return;
  }

  busyProductIds.value = busyProductIds.value.filter((id) => id !== productId);
}

function replaceProductSummary(updatedProduct: ProductSummary) {
  products.value = products.value.map((product) =>
    product.id === updatedProduct.id ? updatedProduct : product,
  );
}

function createOperationNode(): OperationNode {
  const operationId = nextOperationId;
  nextOperationId += 1;

  return {
    id: operationId,
    name: "",
    children: [],
  };
}

function appendChildOperation(
  operations: OperationNode[],
  parentId: number,
): OperationNode[] {
  return operations.map((operation) => {
    if (operation.id === parentId) {
      return {
        ...operation,
        children: [...operation.children, createOperationNode()],
      };
    }

    return {
      ...operation,
      children: appendChildOperation(operation.children, parentId),
    };
  });
}

function appendSiblingOperation(
  operations: OperationNode[],
  operationId: number,
): OperationNode[] {
  const siblingIndex = operations.findIndex((operation) => operation.id === operationId);

  if (siblingIndex >= 0) {
    const nextOperations = [...operations];
    nextOperations.splice(siblingIndex + 1, 0, createOperationNode());
    return nextOperations;
  }

  return operations.map((operation) => ({
    ...operation,
    children: appendSiblingOperation(operation.children, operationId),
  }));
}

function reorderOperationInParent(
  operations: OperationNode[],
  operationId: number,
  direction: -1 | 1,
): OperationNode[] {
  const nextOperations = cloneOperations(operations);
  const path = findOperationPath(nextOperations, operationId);

  if (!path) {
    return operations;
  }

  const siblings = getOperationsAtPath(nextOperations, path.slice(0, -1));
  const currentIndex = path[path.length - 1];
  const targetIndex = currentIndex + direction;

  if (targetIndex < 0 || targetIndex >= siblings.length) {
    return operations;
  }

  const [movedOperation] = siblings.splice(currentIndex, 1);
  siblings.splice(targetIndex, 0, movedOperation);
  return nextOperations;
}

function indentOperationNode(
  operations: OperationNode[],
  operationId: number,
): OperationNode[] {
  const nextOperations = cloneOperations(operations);
  const path = findOperationPath(nextOperations, operationId);

  if (!path) {
    return operations;
  }

  const siblings = getOperationsAtPath(nextOperations, path.slice(0, -1));
  const currentIndex = path[path.length - 1];

  if (currentIndex === 0) {
    return operations;
  }

  const [movedOperation] = siblings.splice(currentIndex, 1);
  siblings[currentIndex - 1].children = [
    ...siblings[currentIndex - 1].children,
    movedOperation,
  ];
  return nextOperations;
}

function outdentOperationNode(
  operations: OperationNode[],
  operationId: number,
): OperationNode[] {
  const nextOperations = cloneOperations(operations);
  const path = findOperationPath(nextOperations, operationId);

  if (!path || path.length < 2) {
    return operations;
  }

  const parentPath = path.slice(0, -1);
  const grandParentPath = parentPath.slice(0, -1);
  const siblings = getOperationsAtPath(nextOperations, parentPath);
  const currentIndex = path[path.length - 1];
  const parentIndex = parentPath[parentPath.length - 1];
  const grandSiblings = getOperationsAtPath(nextOperations, grandParentPath);
  const [movedOperation] = siblings.splice(currentIndex, 1);

  grandSiblings.splice(parentIndex + 1, 0, movedOperation);
  return nextOperations;
}

function deleteOperation(
  operations: OperationNode[],
  operationId: number,
): OperationNode[] {
  return operations
    .filter((operation) => operation.id !== operationId)
    .map((operation) => ({
      ...operation,
      children: deleteOperation(operation.children, operationId),
    }));
}

function renameOperation(
  operations: OperationNode[],
  operationId: number,
  name: string,
): OperationNode[] {
  return operations.map((operation) => {
    if (operation.id === operationId) {
      return {
        ...operation,
        name,
      };
    }

    return {
      ...operation,
      children: renameOperation(operation.children, operationId, name),
    };
  });
}

function flattenOperations(
  operations: OperationNode[],
  level = 0,
): FlatOperationNodeRow[] {
  return operations.flatMap((operation, index, siblings) => {
    const rows: FlatOperationNodeRow[] = [
      {
        id: operation.id,
        name: operation.name,
        level,
        isGroup: operation.children.length > 0,
        canMoveUp: index > 0,
        canMoveDown: index < siblings.length - 1,
        canIndent: index > 0,
        canOutdent: level > 0,
      },
      ...flattenOperations(operation.children, level + 1),
    ];

    return rows;
  });
}

function findOperationPath(
  operations: OperationNode[],
  operationId: number,
  path: number[] = [],
): number[] | null {
  for (const [index, operation] of operations.entries()) {
    const nextPath = [...path, index];

    if (operation.id === operationId) {
      return nextPath;
    }

    const childPath = findOperationPath(operation.children, operationId, nextPath);

    if (childPath) {
      return childPath;
    }
  }

  return null;
}

function getOperationsAtPath(
  operations: OperationNode[],
  path: number[],
): OperationNode[] {
  let currentOperations = operations;

  for (const index of path) {
    currentOperations = currentOperations[index].children;
  }

  return currentOperations;
}

function validateOperationTree(
  operations: OperationNode[],
): Record<number, string> {
  const errors: Record<number, string> = {};

  function walk(nodes: OperationNode[]) {
    const counts = new Map<string, number>();

    for (const node of nodes) {
      const normalizedName = normalizeName(node.name);

      if (normalizedName) {
        counts.set(normalizedName, (counts.get(normalizedName) ?? 0) + 1);
      }
    }

    for (const node of nodes) {
      const normalizedName = normalizeName(node.name);

      if (!normalizedName) {
        errors[node.id] = "Имя операции не должно быть пустым.";
      } else if ((counts.get(normalizedName) ?? 0) > 1) {
        errors[node.id] =
          "Имя операции должно быть уникальным на текущем уровне.";
      }

      walk(node.children);
    }
  }

  walk(operations);
  return errors;
}

function cloneOperations(operations: OperationNode[]): OperationNode[] {
  return operations.map((operation) => ({
    id: operation.id,
    name: operation.name,
    children: cloneOperations(operation.children),
  }));
}

function getMaxOperationId(operations: OperationNode[]): number {
  return operations.reduce(
    (maxId, operation) =>
      Math.max(maxId, operation.id, getMaxOperationId(operation.children)),
    0,
  );
}

function serializeOperations(
  operations: OperationNode[],
): ProductCreatePayload["operations"] {
  return operations.map((operation) => ({
    name: operation.name.trim(),
    children: serializeOperations(operation.children),
  }));
}

function compareProducts(
  left: ProductSummary,
  right: ProductSummary,
  sort: ProductSort,
): number {
  const compareByVersion = () =>
    left.version.localeCompare(right.version, "ru", { numeric: true });

  switch (sort) {
    case "created-asc":
      return left.createdAtTs - right.createdAtTs;
    case "name-asc":
      return (
        left.name.localeCompare(right.name, "ru") ||
        compareByVersion()
      );
    case "name-desc":
      return (
        right.name.localeCompare(left.name, "ru") ||
        -compareByVersion()
      );
    case "version-asc":
      return compareByVersion();
    case "version-desc":
      return -compareByVersion();
    case "created-desc":
    default:
      return right.createdAtTs - left.createdAtTs;
  }
}

function compareUsers(left: UserRecord, right: UserRecord, sort: UserSort): number {
  switch (sort) {
    case "created-asc":
      return (left.createdAtTs ?? 0) - (right.createdAtTs ?? 0);
    case "name-desc":
      return (
        right.name.localeCompare(left.name, "ru") ||
        ((right.createdAtTs ?? 0) - (left.createdAtTs ?? 0))
      );
    case "created-desc":
      return (right.createdAtTs ?? 0) - (left.createdAtTs ?? 0);
    case "name-asc":
    default:
      return (
        left.name.localeCompare(right.name, "ru") ||
        ((right.createdAtTs ?? 0) - (left.createdAtTs ?? 0))
      );
  }
}

function formatUserRole(role: UserRole): string {
  switch (role) {
    case "worker":
      return "Исполнитель";
    case "brigadier":
      return "Бригадир";
    case "constructor":
      return "Конструктор";
    case "admin":
      return "Администратор";
  }
}

function normalizeName(value: string): string {
  return value.trim().toLowerCase();
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function formatTimestamp(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

function readStoredTab<T extends string>(
  key: string,
  allowedValues: readonly T[],
  fallback: T,
): T {
  if (typeof window === "undefined") {
    return fallback;
  }

  const storedValue = window.localStorage.getItem(key);

  if (!storedValue || !allowedValues.includes(storedValue as T)) {
    return fallback;
  }

  return storedValue as T;
}

function storeTab(key: string, value: string) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(key, value);
}

function createUserRecord(params: {
  id: number;
  name: string;
  phone: string;
  passwordHash: string | null;
  author: string | null;
  authorUserId: number | null;
  roles: UserRole[];
  isActive: boolean;
  createdAtTs: number | null;
  updatedAtTs: number | null;
  deletedAtTs: number | null;
  isNew?: boolean;
}): UserRecord {
  return {
    id: params.id,
    name: params.name,
    phone: params.phone,
    passwordHash: params.passwordHash,
    author: params.author,
    authorUserId: params.authorUserId,
    roles: [...params.roles],
    isActive: params.isActive,
    createdAtTs: params.createdAtTs,
    createdAt: params.createdAtTs ? formatTimestamp(params.createdAtTs) : "",
    updatedAtTs: params.updatedAtTs,
    updatedAt: params.updatedAtTs ? formatTimestamp(params.updatedAtTs) : "",
    deletedAtTs: params.deletedAtTs,
    isNew: params.isNew,
  };
}

function cloneUser(user: UserRecord): UserRecord {
  return createUserRecord({
    id: user.id,
    name: user.name,
    phone: user.phone,
    passwordHash: user.passwordHash,
    author: user.author,
    authorUserId: user.authorUserId,
    roles: user.roles,
    isActive: user.isActive,
    createdAtTs: user.createdAtTs,
    updatedAtTs: user.updatedAtTs,
    deletedAtTs: user.deletedAtTs,
    isNew: user.isNew,
  });
}

function areRolesEqual(left: UserRole[], right: UserRole[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  const sortedLeft = [...left].sort();
  const sortedRight = [...right].sort();

  return sortedLeft.every((role, index) => role === sortedRight[index]);
}

function getDefaultAuthorUserId(): number | null {
  return currentSession.value?.userId ?? null;
}

function getDefaultAuthorName(): string | null {
  return currentSession.value?.userName ?? null;
}

async function openBrigadierCreateOrder(productId: number) {
  brigadierModalMode.value = "create";
  brigadierModalOrderId.value = null;
  brigadierModalLoading.value = true;
  brigadierModalError.value = "";
  brigadierSaveLoading.value = false;
  brigadierModalQuantity.value = "1";
  brigadierModalOrderNumber.value = generateNextWorkOrderNumber();
  brigadierModalAssignments.value = [];

  try {
    const product = await fetchProduct(productId);
    brigadierModalProduct.value = product;
    brigadierModalAssignments.value = buildBrigadierAssignments(product.operations);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierModalError.value = getErrorMessage(error, "Не удалось загрузить изделие.");
  } finally {
    brigadierModalLoading.value = false;
  }
}

async function openBrigadierManageOrder(order: WorkOrderSummary) {
  brigadierModalMode.value = "manage";
  brigadierModalOrderId.value = order.id;
  brigadierModalLoading.value = true;
  brigadierModalError.value = "";
  brigadierSaveLoading.value = false;
  brigadierModalQuantity.value = String(order.quantity);
  brigadierModalOrderNumber.value = order.orderNumber;
  brigadierModalAssignments.value = [];

  try {
    const [product, orderDetail] = await Promise.all([
      fetchProduct(order.productId),
      fetchWorkOrder(order.id),
    ]);
    brigadierModalProduct.value = product;
    brigadierModalAssignments.value = mergeBrigadierAssignments(
      buildBrigadierAssignments(product.operations),
      orderDetail,
    );
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierModalError.value = getErrorMessage(error, "Не удалось загрузить заказ.");
  } finally {
    brigadierModalLoading.value = false;
  }
}

function closeBrigadierOrderModal() {
  brigadierModalMode.value = null;
  brigadierModalProduct.value = null;
  brigadierModalOrderId.value = null;
  brigadierModalAssignments.value = [];
  brigadierModalQuantity.value = "1";
  brigadierModalOrderNumber.value = "";
  brigadierModalLoading.value = false;
  brigadierModalError.value = "";
  brigadierSaveLoading.value = false;
}

function buildBrigadierAssignments(
  operations: OperationNode[],
  parents: string[] = [],
): BrigadierOrderAssignment[] {
  return operations.flatMap((operation) => {
    const nextParents = [...parents, operation.name];

    if (operation.children.length === 0) {
      return [
        {
          operationId: operation.id,
          operationLabel: nextParents.join(" / "),
          workerUserId: null,
          workerName: "",
        },
      ];
    }

    return buildBrigadierAssignments(operation.children, nextParents);
  });
}

function mergeBrigadierAssignments(
  baseAssignments: BrigadierOrderAssignment[],
  orderDetail: WorkOrderDetail,
): BrigadierOrderAssignment[] {
  const savedByOperation = new Map(
    orderDetail.assignments.map((assignment) => [assignment.operationId, assignment]),
  );

  return baseAssignments.map((assignment) => {
    const savedAssignment = savedByOperation.get(assignment.operationId);

    if (!savedAssignment) {
      return assignment;
    }

    return {
      ...assignment,
      workerUserId: savedAssignment.workerUserId,
      workerName: savedAssignment.workerUserName,
    };
  });
}

function handleBrigadierQuantityInput(event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  brigadierModalQuantity.value = target.value.replace(/[^\d]/g, "");
}

function handleBrigadierOrderNumberInput(event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  brigadierModalOrderNumber.value = target.value;
}

function handleBrigadierAssignmentInput(operationId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  const nextName = target.value;
  const normalizedName = normalizeName(nextName);
  const matchedWorker =
    brigadierWorkerUsers.value.find(
      (user) => normalizeName(user.name) === normalizedName,
    ) ?? null;

  brigadierModalAssignments.value = brigadierModalAssignments.value.map((assignment) =>
    assignment.operationId === operationId
      ? {
          ...assignment,
          workerName: nextName,
          workerUserId: matchedWorker?.id ?? null,
        }
      : assignment,
  );
}

function clearBrigadierAssignment(operationId: number) {
  brigadierModalAssignments.value = brigadierModalAssignments.value.map((assignment) =>
    assignment.operationId === operationId
      ? {
          ...assignment,
          workerName: "",
          workerUserId: null,
        }
      : assignment,
  );
}

function getBrigadierAssignmentError(assignment: BrigadierOrderAssignment): string {
  if (assignment.workerUserId !== null) {
    return "";
  }

  return assignment.workerName.trim()
    ? "Выберите исполнителя из списка."
    : "Назначьте исполнителя.";
}

function scrollToBrigadierSaveIssue() {
  const selector = brigadierSaveIssue.value?.selector;

  if (!selector) {
    return;
  }

  const target = document.querySelector<HTMLElement>(selector);

  if (!target) {
    return;
  }

  target.scrollIntoView({
    behavior: "smooth",
    block: "center",
    inline: "nearest",
  });

  if (target instanceof HTMLInputElement || target instanceof HTMLButtonElement) {
    target.focus({ preventScroll: true });
  }
}

function formatDuration(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours === 0) {
    return `${minutes} мин`;
  }

  if (minutes === 0) {
    return `${hours} ч`;
  }

  return `${hours} ч ${minutes} мин`;
}

function formatTimerDuration(totalMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(totalMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

function formatDurationCompact(totalMs: number): string {
  const totalMinutes = Math.max(0, Math.floor(totalMs / 60000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours === 0) {
    return `${minutes}м`;
  }

  if (minutes === 0) {
    return `${hours}ч`;
  }

  return `${hours}ч ${minutes}м`;
}

function formatPercentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatStatisticsDate(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}.${month}`;
}

function parseOrderIdFromTimerId(timerId: string): number | null {
  const parts = timerId.split(":");
  if (parts.length === 4 && parts[0] === "worker" && parts[1] === "operation") {
    return Number.parseInt(parts[2], 10);
  }
  return null;
}

function parseOperationIdFromTimerId(timerId: string): number | null {
  const parts = timerId.split(":");
  if (parts.length === 4 && parts[0] === "worker" && parts[1] === "operation") {
    return Number.parseInt(parts[3], 10);
  }
  return null;
}

function getStatisticsStackSegmentStyle(totalMs: number, chartMax: number, color: string): string {
  const heightPercent = chartMax > 0 ? (totalMs / chartMax) * 100 : 0;
  return `height: ${heightPercent}%; background: ${color};`;
}

function getStatisticsBarStyle(totalMs: number, chartMax: number): string {
  const widthPercent = chartMax > 0 ? (totalMs / chartMax) * 100 : 0;
  return `width: ${widthPercent}%;`;
}

async function selectStatisticsPeriod(days: (typeof statisticsPeriodOptions)[number]) {
  if (statisticsPeriodDays.value === days && statisticsOverview.value) {
    return;
  }

  statisticsPeriodDays.value = days;
  if (canViewStatistics.value) {
    await loadStatistics();
  }
}

function estimateWorkOrderMinutes(
  quantity: number,
  assignments: BrigadierOrderAssignment[],
): number {
  const baseMinutes = assignments.reduce(
    (total, assignment, index) => total + 18 + Math.min(10, assignment.operationLabel.length % 11) + index,
    0,
  );

  return baseMinutes * quantity;
}

async function saveBrigadierOrder() {
  if (!brigadierModalCanSave.value || !brigadierModalProduct.value) {
    scrollToBrigadierSaveIssue();
    return;
  }

  brigadierSaveLoading.value = true;
  brigadierModalError.value = "";

  const quantity =
    brigadierModalMode.value === "manage" && brigadierCurrentOrder.value
      ? brigadierCurrentOrder.value.quantity
      : Number.parseInt(brigadierModalQuantity.value, 10);
  const assignments = brigadierModalAssignments.value.map((assignment) => ({ ...assignment }));
  const totalSpentMinutes = estimateWorkOrderMinutes(quantity, assignments);

  try {
    if (brigadierModalMode.value === "manage" && brigadierCurrentOrder.value) {
      await updateWorkOrderAssignments(brigadierCurrentOrder.value.id, {
        total_spent_minutes: totalSpentMinutes,
        assignments: assignments.map((assignment) => ({
          operation_id: assignment.operationId,
          worker_user_id: assignment.workerUserId as number,
        })),
      });
    } else {
      await createWorkOrder({
        order_number: brigadierModalOrderNumber.value.trim(),
        product_id: brigadierModalProduct.value.id,
        quantity,
        total_spent_minutes: totalSpentMinutes,
        assignments: assignments.map((assignment) => ({
          operation_id: assignment.operationId,
          worker_user_id: assignment.workerUserId as number,
        })),
      });
    }

    await loadWorkOrders();
    brigadierTab.value = "active";
    closeBrigadierOrderModal();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierModalError.value = getErrorMessage(error, "Не удалось сохранить заказ.");
  } finally {
    brigadierSaveLoading.value = false;
  }
}

function generateNextWorkOrderNumber(): string {
  const maxOrderIndex = workOrders.value.reduce((maxValue, order) => {
    const match = order.orderNumber.match(/(\d+)$/);

    if (!match) {
      return maxValue;
    }

    return Math.max(maxValue, Number.parseInt(match[1], 10));
  }, 0);

  return `FC-${String(maxOrderIndex + 1).padStart(4, "0")}`;
}

async function persistUserChanges(user: UserRecord) {
  if (!editingUserDraft.value) {
    return;
  }

  usersError.value = "";

  try {
    if (user.isNew) {
      await createUserApi({
        name: editingUserDraft.value.name.trim(),
        phone: editingUserDraft.value.phone.trim(),
        roles: editingUserDraft.value.roles,
        is_active: editingUserDraft.value.isActive,
        author_user_id: editingUserDraft.value.authorUserId,
      });
    } else {
      await updateUserApi(user.id, {
        name: editingUserDraft.value.name.trim(),
        phone: editingUserDraft.value.phone.trim(),
        roles: editingUserDraft.value.roles,
        is_active: editingUserDraft.value.isActive,
        author_user_id: editingUserDraft.value.authorUserId,
      });
    }

    editingUserId.value = null;
    editingUserDraft.value = null;
    await loadUsers();
    await loadProducts();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    usersError.value = getErrorMessage(error, "Не удалось сохранить пользователя.");
  }
}

async function removeUser(user: UserRecord) {
  if (user.isNew) {
    users.value = users.value.filter((item) => item.id !== user.id);
    if (editingUserId.value === user.id) {
      editingUserId.value = null;
      editingUserDraft.value = null;
    }
    closeUserDeleteConfirmation();
    return;
  }

  usersError.value = "";

  try {
    await deleteUserApi(user.id);
    closeUserDeleteConfirmation();
    if (editingUserId.value === user.id) {
      editingUserId.value = null;
      editingUserDraft.value = null;
    }
    await loadUsers();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    usersError.value = getErrorMessage(error, "Не удалось удалить пользователя.");
  }
}

async function handleResetUserPassword(user: UserRecord) {
  if (isUserLocked(user.id)) {
    return;
  }

  usersError.value = "";

  try {
    await resetUserPasswordApi(user.id);
    await loadUsers();

    if (currentSession.value?.userId === user.id) {
      redirectToAuth("Пароль текущего пользователя был сброшен. Войдите снова.");
    }
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    usersError.value = getErrorMessage(error, "Не удалось сбросить пароль.");
  }
}
</script>

<template>
  <main class="page">
    <section v-if="authInitializing" class="auth-shell">
      <div class="auth-card">
        <p class="section-label">FlowCraft</p>
        <h2>Проверка сессии</h2>
        <p class="auth-card__description">Подготавливаю рабочее пространство пользователя.</p>
      </div>
    </section>

    <section v-else-if="!currentSession" class="auth-shell">
      <form class="auth-card" @submit.prevent="void submitAuthentication()">
        <div class="auth-card__head">
          <div class="brand-logo-frame brand-logo-frame--auth">
            <img
              :src="flowcraftLogoUrl"
              alt="FlowCraft"
              class="brand-logo"
            />
          </div>
          <div>
            <p class="section-label">Аутентификация</p>
            <h2>{{ authRequiresPasswordSetup ? "Задайте пароль" : "Вход в систему" }}</h2>
            <p class="auth-card__description">
              {{
                authRequiresPasswordSetup
                  ? `Для пользователя ${authSetupUserName || authPhone} пароль еще не задан.`
                  : "Введите номер телефона и пароль пользователя."
              }}
            </p>
          </div>
        </div>

        <label class="field">
          <span class="field__label">Номер телефона</span>
          <input
            v-model="authPhone"
            type="text"
            class="text-input"
            autocomplete="username"
            placeholder="+7 999 123-45-67"
            :readonly="authRequiresPasswordSetup"
          />
        </label>

        <label v-if="!authRequiresPasswordSetup" class="field">
          <span class="field__label">Пароль</span>
          <input
            v-model="authPassword"
            type="password"
            class="text-input"
            autocomplete="current-password"
            placeholder="Введите пароль"
          />
        </label>

        <template v-else>
          <label class="field">
            <span class="field__label">Новый пароль</span>
            <input
              v-model="authNewPassword"
              type="password"
              class="text-input"
              autocomplete="new-password"
              placeholder="Не менее 8 символов"
            />
          </label>

          <label class="field">
            <span class="field__label">Подтверждение пароля</span>
            <input
              v-model="authConfirmPassword"
              type="password"
              class="text-input"
              autocomplete="new-password"
              placeholder="Повторите пароль"
            />
          </label>
        </template>

        <p v-if="authError" class="field-error">{{ authError }}</p>

        <div class="auth-card__actions">
          <button type="submit" class="primary-button" :disabled="authSubmitting">
            <span class="button-content">
              <span class="button-icon button-icon--key" aria-hidden="true" />
              <span>
                {{
                  authSubmitting
                    ? "Обработка..."
                    : authRequiresPasswordSetup
                      ? "Сохранить пароль"
                      : "Войти"
                }}
              </span>
            </span>
          </button>
        </div>
      </form>
    </section>

    <section v-else class="shell">
      <header class="header">
        <nav class="tabs" aria-label="Разделы">
          <button
            v-for="tab in availableTabs"
            :key="tab.id"
            type="button"
            class="tab-button"
            :class="{ 'tab-button--active': activeTab === tab.id }"
            @click="setActiveTab(tab.id)"
          >
            <span class="button-content">
              <span class="role-icon" :class="`role-icon--${tab.icon}`" aria-hidden="true" />
              <span>{{ tab.label }}</span>
            </span>
          </button>
        </nav>

        <div class="current-user-card">
          <div class="current-user-card__identity">
            <span class="section-label">Текущий пользователь</span>
            <strong>{{ currentSession.userName }}</strong>
          </div>
          <div class="current-user-card__actions">
            <button type="button" class="ghost-button" @click="openChangePasswordModal">
              <span class="button-content">
                <span class="button-icon button-icon--key" aria-hidden="true" />
                <span>Изменить пароль</span>
              </span>
            </button>
            <button type="button" class="ghost-button" @click="void handleLogout()">
              <span class="button-content">
                <span class="button-icon button-icon--logout" aria-hidden="true" />
                <span>Выйти</span>
              </span>
            </button>
          </div>
        </div>

        <div class="brand-block">
          <div class="brand-logo-frame">
            <img
              :src="flowcraftLogoUrl"
              alt="FlowCraft"
              class="brand-logo"
            />
          </div>
        </div>
      </header>

      <section v-if="activeTab === 'worker'">
        <article class="constructor-panel worker-panel">
          <div class="panel-head worker-panel__head">
            <div>
              <h2>Учет времени исполнителя</h2>
              <p class="worker-panel__subtitle">
                {{
                  currentWorker
                    ? `Текущий исполнитель: ${currentWorker.name}`
                    : "Нет активного исполнителя"
                }}
              </p>
            </div>

            <button
              type="button"
              class="primary-button"
              :disabled="!currentWorker || workerTimerSubmitting"
              @click="isWorkerDayActive ? requestEndWorkerDay() : void startWorkerDay()"
            >
              <span class="button-content">
                <span
                  class="button-icon"
                  :class="isWorkerDayActive ? 'button-icon--stop' : 'button-icon--play'"
                  aria-hidden="true"
                />
                <span>{{ isWorkerDayActive ? "Закончить рабочий день" : "Начать рабочий день" }}</span>
              </span>
            </button>
          </div>

          <div v-if="!currentWorker" class="empty-table-state">
            <p>Добавьте активного пользователя с ролью исполнителя, чтобы открыть рабочий экран.</p>
          </div>

          <template v-else>
            <div class="worker-summary">
              <div class="worker-summary__card">
                <span class="section-label">Статус дня</span>
                <strong>{{ isWorkerDayActive ? "Смена идет" : "Смена не начата" }}</strong>
                <span class="worker-summary__value">{{ formatTimerDuration(workerDayElapsedMs) }}</span>
              </div>

              <div class="worker-summary__card">
                <span class="section-label">Активный таймер</span>
                <strong>{{ workerActiveTimer?.label ?? "Нет активного таймера" }}</strong>
                <span class="worker-summary__value">
                  {{
                    workerActiveTimer
                      ? formatTimerDuration(getWorkerTimerElapsedMs(workerActiveTimer.id))
                      : "00:00:00"
                  }}
                </span>
              </div>
            </div>

            <div class="worker-timer-bar">
              <button
                v-for="timer in workerPrimaryTimers"
                :key="timer.id"
                type="button"
                class="worker-timer-button"
                :class="{ 'worker-timer-button--active': isWorkerTimerActive(timer.id) }"
                :disabled="!isWorkerDayActive || workerTimerSubmitting"
                @click="void activateWorkerTimer(timer.id)"
              >
                <span class="worker-timer-button__heading">
                  <span
                    class="button-icon"
                    :class="`button-icon--timer-${timer.kind}`"
                    aria-hidden="true"
                  />
                  <span class="worker-timer-button__label">{{ timer.label }}</span>
                </span>
                <span class="worker-timer-button__value">
                  {{ formatTimerDuration(getWorkerTimerElapsedMs(timer.id)) }}
                </span>
              </button>

              <button
                v-if="workerIdleTimer"
                type="button"
                class="worker-timer-button worker-timer-button--secondary"
                :class="{ 'worker-timer-button--active': isWorkerTimerActive(workerIdleTimer.id) }"
                :disabled="!isWorkerDayActive || workerTimerSubmitting"
                @click="void activateWorkerTimer(workerIdleTimer.id)"
              >
                <span class="worker-timer-button__heading">
                  <span
                    class="button-icon"
                    :class="`button-icon--timer-${workerIdleTimer.kind}`"
                    aria-hidden="true"
                  />
                  <span class="worker-timer-button__label">{{ workerIdleTimer.label }}</span>
                </span>
                <span class="worker-timer-button__value">
                  {{ formatTimerDuration(getWorkerTimerElapsedMs(workerIdleTimer.id)) }}
                </span>
              </button>
            </div>

            <div v-if="workerAssignmentsError" class="banner banner--error">
              <p>{{ workerAssignmentsError }}</p>
              <button type="button" class="ghost-button" @click="loadWorkOrders">
                <span class="button-content">
                  <span class="button-icon button-icon--refresh" aria-hidden="true" />
                  <span>Повторить</span>
                </span>
              </button>
            </div>

            <div v-else-if="workerAssignmentsLoading" class="banner">
              <p>Загрузка назначенных операций...</p>
            </div>

            <div v-else-if="workerTimerGroups.length === 0" class="empty-table-state">
              <p>Для текущего исполнителя пока нет назначенных операций.</p>
            </div>

            <div v-else class="worker-groups">
              <section
                v-for="group in workerTimerGroups"
                :key="group.productKey"
                class="worker-group"
              >
                <button
                  type="button"
                  class="worker-group__head"
                  @click="toggleWorkerGroup(group.productKey)"
                >
                  <span class="worker-group__title">
                    <span class="button-icon button-icon--package" aria-hidden="true" />
                    <h3>
                      {{ group.orderNumbers.join(", ") }} · {{ group.productLabel }} ({{ group.quantity }} шт.)
                    </h3>
                  </span>
                  <span
                    class="worker-group__chevron"
                    :class="{
                      'worker-group__chevron--expanded':
                        workerGroupExpanded[group.productKey],
                    }"
                    aria-hidden="true"
                  />
                </button>

                <div
                  v-if="workerGroupExpanded[group.productKey]"
                  class="worker-group__timers"
                >
                  <button
                    v-for="timer in group.timers"
                    :key="timer.id"
                    type="button"
                    class="worker-timer-button worker-timer-button--operation"
                    :class="{ 'worker-timer-button--active': isWorkerTimerActive(timer.id) }"
                    :disabled="!isWorkerDayActive || workerTimerSubmitting"
                    @click="void activateWorkerTimer(timer.id)"
                  >
                    <span class="worker-timer-button__meta">
                      <span class="worker-timer-button__heading">
                        <span class="button-icon button-icon--timer-operation" aria-hidden="true" />
                        <span class="worker-timer-button__order">{{ timer.orderNumber }}</span>
                        <span class="worker-timer-button__label">{{ timer.label }}</span>
                      </span>
                    </span>
                    <span class="worker-timer-button__value">
                      {{ formatTimerDuration(getWorkerTimerElapsedMs(timer.id)) }}
                    </span>
                  </button>
                </div>
              </section>
            </div>
          </template>
        </article>
      </section>

      <section v-else-if="activeTab === 'brigadier'">
        <article class="constructor-panel">
          <div class="panel-head panel-head--stacked">
            <div>
              <h2>Управление заказами</h2>
            </div>

            <div class="subtabs" role="tablist" aria-label="Разделы бригадира">
              <button
                type="button"
                class="subtab-button"
                :class="{ 'subtab-button--active': brigadierTab === 'active' }"
                @click="setBrigadierTab('active')"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--in-work" aria-hidden="true" />
                  <span>В работе</span>
                </span>
              </button>
              <button
                type="button"
                class="subtab-button"
                :class="{ 'subtab-button--active': brigadierTab === 'orders' }"
                @click="setBrigadierTab('orders')"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--orders" aria-hidden="true" />
                  <span>Новый заказ</span>
                </span>
              </button>
            </div>
          </div>

          <template v-if="brigadierTab === 'active'">
            <div v-if="brigadierOrdersError" class="banner banner--error">
              <p>{{ brigadierOrdersError }}</p>
              <button type="button" class="ghost-button" @click="loadWorkOrders">
                <span class="button-content">
                  <span class="button-icon button-icon--refresh" aria-hidden="true" />
                  <span>Повторить</span>
                </span>
              </button>
            </div>

            <div v-else-if="brigadierOrdersLoading" class="banner">
              <p>Загрузка заказов...</p>
            </div>

            <div v-else-if="workOrders.length === 0" class="empty-table-state">
              <p>Заказы в работе пока не созданы.</p>
            </div>

            <div v-else class="table-wrap">
              <table class="products-table brigadier-table">
                <thead>
                  <tr>
                    <th>Номер заказа</th>
                    <th>Наименование</th>
                    <th>Версия</th>
                    <th>Исполнители</th>
                    <th>Суммарное время</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="order in workOrders" :key="order.id">
                    <td>{{ order.orderNumber }}</td>
                    <td>{{ order.productName }}</td>
                    <td>{{ order.productVersion }}</td>
                    <td>
                      <button
                        type="button"
                        class="secondary-button"
                        @click="openBrigadierManageOrder(order)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--people" aria-hidden="true" />
                          <span>{{ order.assignmentsCount }} назначений</span>
                        </span>
                      </button>
                    </td>
                    <td>
                      <span class="duration-badge">
                        {{ formatDuration(order.totalSpentMinutes) }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>

          <template v-else>
            <div class="toolbar">
              <label class="field field--inline">
                <span class="field__label">Поиск по изделиям</span>
                <div class="filter-input-wrap">
                  <input
                    v-model="brigadierProductFilter"
                    type="text"
                    class="text-input text-input--with-action"
                    placeholder="Например, сумка"
                  />
                  <button
                    v-if="brigadierProductFilter"
                    type="button"
                    class="field-action"
                    aria-label="Очистить фильтр"
                    title="Очистить фильтр"
                    @click="brigadierProductFilter = ''"
                  >
                    <span class="field-action__icon" aria-hidden="true" />
                  </button>
                </div>
              </label>

              <div class="field field--inline">
                <span class="field__label">Сортировка</span>
                <div class="segmented-control segmented-control--wrap" role="group" aria-label="Сортировка заказов">
                  <button
                    v-for="option in sortOptions"
                    :key="option.field"
                    type="button"
                    class="segmented-control__button segmented-control__button--icon"
                    :class="{
                      'segmented-control__button--active':
                        isBrigadierSortFieldActive(option.field),
                    }"
                    :title="`${option.label} (${getBrigadierSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                    :aria-label="`${option.label} (${getBrigadierSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                    @click="toggleBrigadierSort(option.field)"
                  >
                    <span
                      class="toolbar-icon"
                      :class="[
                        `toolbar-icon--${option.icon}`,
                        `toolbar-icon--${getBrigadierSortDirection(option.field)}`,
                      ]"
                      aria-hidden="true"
                    />
                  </button>
                </div>
              </div>
            </div>

            <div v-if="listError" class="banner banner--error">
              <p>{{ listError }}</p>
              <button type="button" class="ghost-button" @click="loadProducts">
                <span class="button-content">
                  <span class="button-icon button-icon--refresh" aria-hidden="true" />
                  <span>Повторить</span>
                </span>
              </button>
            </div>

            <div v-if="listLoading" class="banner">
              <p>Загрузка изделий...</p>
            </div>

            <div v-else class="table-wrap">
              <table class="products-table brigadier-table">
                <thead>
                  <tr>
                    <th>Наименование</th>
                    <th>Версия</th>
                    <th>Дата создания</th>
                    <th>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="product in filteredBrigadierProducts" :key="product.id">
                    <td>{{ product.name }}</td>
                    <td>{{ product.version }}</td>
                    <td>{{ product.createdAt }}</td>
                    <td>
                      <button
                        type="button"
                        class="primary-button"
                        @click="openBrigadierCreateOrder(product.id)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--play" aria-hidden="true" />
                          <span>Взять в работу</span>
                        </span>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div
              v-if="!listLoading && filteredBrigadierProducts.length === 0"
              class="empty-table-state"
            >
              <p>По текущему фильтру изделия не найдены.</p>
            </div>
          </template>
        </article>
      </section>

      <section v-else-if="activeTab === 'stats'">
        <article class="constructor-panel statistics-panel">
          <div class="panel-head">
            <div>
              <h2>Статистика производства</h2>
              <p class="worker-panel__subtitle">
                Последнее обновление:
                {{ statisticsOverview ? formatTimestamp(statisticsOverview.generatedAtTs) : "—" }}
              </p>
            </div>

            <div class="statistics-toolbar">
              <div class="segmented-control" role="group" aria-label="Период статистики">
                <button
                  v-for="days in statisticsPeriodOptions"
                  :key="days"
                  type="button"
                  class="segmented-control__button"
                  :class="{ 'segmented-control__button--active': statisticsPeriodDays === days }"
                  @click="void selectStatisticsPeriod(days)"
                >
                  {{ days }} дн.
                </button>
              </div>

              <button
                type="button"
                class="ghost-button"
                :disabled="statisticsLoading"
                @click="void loadStatistics()"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--refresh" aria-hidden="true" />
                  <span>Обновить</span>
                </span>
              </button>
            </div>
          </div>

          <div v-if="statisticsError" class="banner banner--error">
            <p>{{ statisticsError }}</p>
          </div>

          <div v-else-if="statisticsLoading" class="banner">
            <p>Загрузка статистики...</p>
          </div>

          <div v-else-if="!statisticsOverview" class="empty-table-state">
            <p>Статистика пока недоступна.</p>
          </div>

          <template v-else>
            <div class="statistics-kpis">
              <article class="statistics-kpi-card">
                <span class="section-label">Всего учтено</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.totalTrackedMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Операции</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.operationMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Подготовка</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.preparationMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Перерыв</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.breakMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Простой</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.idleMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Полезное время</span>
                <strong>{{ formatPercentage(statisticsOverview.kpis.productiveRatio) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Активные заказы</span>
                <strong>{{ statisticsOverview.kpis.activeOrdersCount }}</strong>
              </article>
            </div>

            <div class="statistics-grid">
              <section class="statistics-card statistics-card--wide">
                <div class="statistics-card__head">
                  <h3>Структура рабочего времени по дням</h3>
                </div>

                <div class="statistics-legend" aria-label="Легенда статистики">
                  <span class="statistics-legend__item">
                    <span class="statistics-legend__swatch statistics-legend__swatch--operation" aria-hidden="true" />
                    <span>Операции</span>
                  </span>
                  <span class="statistics-legend__item">
                    <span class="statistics-legend__swatch statistics-legend__swatch--preparation" aria-hidden="true" />
                    <span>Подготовка</span>
                  </span>
                  <span class="statistics-legend__item">
                    <span class="statistics-legend__swatch statistics-legend__swatch--break" aria-hidden="true" />
                    <span>Перерыв</span>
                  </span>
                  <span class="statistics-legend__item">
                    <span class="statistics-legend__swatch statistics-legend__swatch--idle" aria-hidden="true" />
                    <span>Простой</span>
                  </span>
                </div>

                <div class="stacked-chart">
                  <div
                    v-for="day in statisticsOverview.dailyBreakdown"
                    :key="day.date"
                    class="stacked-chart__item"
                  >
                    <div class="stacked-chart__column">
                      <span
                        class="stacked-chart__segment stacked-chart__segment--operation"
                        :style="getStatisticsStackSegmentStyle(day.operationMs, statisticsDailyMax, 'var(--color-primary)')"
                      />
                      <span
                        class="stacked-chart__segment stacked-chart__segment--preparation"
                        :style="getStatisticsStackSegmentStyle(day.preparationMs, statisticsDailyMax, 'var(--color-success)')"
                      />
                      <span
                        class="stacked-chart__segment stacked-chart__segment--break"
                        :style="getStatisticsStackSegmentStyle(day.breakMs, statisticsDailyMax, 'var(--color-warning)')"
                      />
                      <span
                        class="stacked-chart__segment stacked-chart__segment--idle"
                        :style="getStatisticsStackSegmentStyle(day.idleMs, statisticsDailyMax, 'var(--color-danger)')"
                      />
                    </div>
                    <span class="stacked-chart__value">{{ formatDurationCompact(day.totalMs) }}</span>
                    <span class="stacked-chart__label">{{ formatStatisticsDate(day.date) }}</span>
                  </div>
                </div>
              </section>

              <section class="statistics-card">
                <div class="statistics-card__head">
                  <h3>Трудоемкие операции</h3>
                </div>

                <div v-if="statisticsOverview.topOperations.length === 0" class="empty-table-state">
                  <p>Пока нет данных по операциям.</p>
                </div>
                <div v-else class="statistics-bars">
                  <article
                    v-for="item in statisticsOverview.topOperations"
                    :key="item.operationId"
                    class="statistics-bar-row"
                  >
                    <div class="statistics-bar-row__meta">
                      <strong>{{ item.operationName }}</strong>
                      <span>{{ item.productName }} · {{ item.productVersion }}</span>
                    </div>
                    <div class="statistics-bar-row__meta statistics-bar-row__meta--secondary">
                      <span>{{ formatDurationCompact(item.totalMs) }} · ср. {{ formatDurationCompact(item.averageMs) }}</span>
                    </div>
                    <div class="statistics-bar-row__track">
                      <span
                        class="statistics-bar-row__fill"
                        :style="getStatisticsBarStyle(item.totalMs, statisticsOperationMax)"
                      />
                    </div>
                  </article>
                </div>
              </section>

              <section class="statistics-card">
                <div class="statistics-card__head">
                  <h3>Заказы по трудозатратам</h3>
                </div>

                <div v-if="statisticsOverview.topOrders.length === 0" class="empty-table-state">
                  <p>Пока нет данных по заказам.</p>
                </div>
                <div v-else class="statistics-bars">
                  <article
                    v-for="item in statisticsOverview.topOrders"
                    :key="item.orderId"
                    class="statistics-bar-row"
                  >
                    <div class="statistics-bar-row__meta">
                      <strong>{{ item.orderNumber }} · {{ item.productName }} · {{ item.productVersion }}</strong>
                      <span>{{ formatDurationCompact(item.totalMs) }}</span>
                    </div>
                    <div class="statistics-bar-row__track">
                      <span
                        class="statistics-bar-row__fill statistics-bar-row__fill--muted"
                        :style="getStatisticsBarStyle(item.totalMs, statisticsOrderMax)"
                      />
                    </div>
                  </article>
                </div>
              </section>

              <section class="statistics-card statistics-card--wide">
                <div class="statistics-card__head">
                  <h3>Загрузка сотрудников</h3>
                </div>

                <div v-if="statisticsOverview.workers.length === 0" class="empty-table-state">
                  <p>Пока нет данных по сотрудникам.</p>
                </div>
                <div v-else class="statistics-bars">
                  <article
                    v-for="item in statisticsOverview.workers"
                    :key="item.userId"
                    class="statistics-bar-row"
                  >
                    <div class="statistics-bar-row__meta">
                      <strong>{{ item.userName }}</strong>
                      <span>
                        {{ formatDurationCompact(item.totalMs) }}
                        · операции {{ formatDurationCompact(item.operationMs) }}
                        · простой {{ formatDurationCompact(item.idleMs) }}
                        · {{ formatPercentage(item.productiveRatio) }}
                      </span>
                    </div>
                    <div class="statistics-bar-row__track">
                      <span
                        class="statistics-bar-row__fill statistics-bar-row__fill--success"
                        :style="getStatisticsBarStyle(item.totalMs, statisticsWorkerMax)"
                      />
                    </div>
                  </article>
                </div>
              </section>

              <section class="statistics-card">
                <div class="statistics-card__head">
                  <h3>Простой по дням</h3>
                </div>

                <div class="mini-chart">
                  <div
                    v-for="day in statisticsOverview.idleByDay"
                    :key="day.date"
                    class="mini-chart__item"
                  >
                    <span
                      class="mini-chart__bar"
                      :style="getStatisticsStackSegmentStyle(day.idleMs, statisticsIdleMax, 'var(--color-danger)')"
                    />
                    <span class="mini-chart__label">{{ formatStatisticsDate(day.date) }}</span>
                  </div>
                </div>
              </section>
            </div>
          </template>
        </article>
      </section>

      <section v-else-if="activeTab === 'constructor'">
        <article class="constructor-panel">
          <div class="panel-head">
            <div>
              <h2>Изделия и дерево операций</h2>
            </div>

            <button type="button" class="primary-button" @click="startCreateProduct">
              <span class="button-content">
                <span class="button-icon button-icon--plus" aria-hidden="true" />
                <span>Создать новое изделие</span>
              </span>
            </button>
          </div>

          <div class="toolbar">
            <label class="field field--inline">
              <span class="field__label">Фильтр по имени</span>
              <div class="filter-input-wrap">
                <input
                  v-model="productFilter"
                  type="text"
                  class="text-input text-input--with-action"
                  placeholder="Например, кошелек"
                />
                <button
                  v-if="productFilter"
                  type="button"
                  class="field-action"
                  aria-label="Очистить фильтр"
                  title="Очистить фильтр"
                  @click="productFilter = ''"
                >
                  <span class="field-action__icon" aria-hidden="true" />
                </button>
              </div>
            </label>

            <div class="field field--inline">
              <span class="field__label">Отображение</span>
              <div class="segmented-control" role="group" aria-label="Отображение изделий">
                <button
                  v-for="option in visibilityOptions"
                  :key="option.value"
                  type="button"
                  class="segmented-control__button segmented-control__button--icon"
                  :class="{
                    'segmented-control__button--active':
                      productVisibility === option.value,
                  }"
                  :title="option.label"
                  :aria-label="option.label"
                  @click="productVisibility = option.value"
                >
                  <span
                    class="toolbar-icon"
                    :class="`toolbar-icon--${option.icon}`"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>

            <div class="field field--inline">
              <span class="field__label">Сортировка</span>
              <div class="segmented-control segmented-control--wrap" role="group" aria-label="Сортировка изделий">
                <button
                  v-for="option in sortOptions"
                  :key="option.field"
                  type="button"
                  class="segmented-control__button segmented-control__button--icon"
                  :class="{
                    'segmented-control__button--active':
                      isSortFieldActive(option.field),
                  }"
                  :title="`${option.label} (${getSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                  :aria-label="`${option.label} (${getSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                  @click="toggleProductSort(option.field)"
                >
                  <span
                    class="toolbar-icon"
                    :class="[
                      `toolbar-icon--${option.icon}`,
                      `toolbar-icon--${getSortDirection(option.field)}`,
                    ]"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>
          </div>

          <div v-if="listError" class="banner banner--error">
            <p>{{ listError }}</p>
            <button type="button" class="ghost-button" @click="loadProducts">
              <span class="button-content">
                <span class="button-icon button-icon--refresh" aria-hidden="true" />
                <span>Повторить</span>
              </span>
            </button>
          </div>

          <div v-if="listLoading" class="banner">
            <p>Загрузка изделий...</p>
          </div>

          <div v-else class="table-wrap">
            <table class="products-table">
              <thead>
                <tr>
                  <th>Наименование</th>
                  <th>Версия</th>
                  <th>Автор</th>
                  <th>Дата создания</th>
                  <th>Активность</th>
                  <th>Операции</th>
                  <th>Копия</th>
                  <th>Удаление</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="product in filteredProducts" :key="product.id">
                  <td>{{ product.name }}</td>
                  <td>{{ product.version }}</td>
                  <td>{{ product.author }}</td>
                  <td>{{ product.createdAt }}</td>
                  <td>
                    <button
                      type="button"
                      class="status-button"
                      :class="{
                        'status-button--active': product.isActive,
                        'status-button--inactive': !product.isActive,
                      }"
                      :disabled="isProductBusy(product.id)"
                      @click="toggleProductStatus(product)"
                    >
                      <span class="button-content">
                        <span
                          class="button-icon"
                          :class="product.isActive ? 'button-icon--pause' : 'button-icon--check'"
                          aria-hidden="true"
                        />
                        <span>
                          {{
                            isProductBusy(product.id)
                              ? "Обновление..."
                              : product.isActive
                                ? "Деактивировать"
                                : "Активировать"
                          }}
                        </span>
                      </span>
                    </button>
                  </td>
                  <td>
                    <button
                      type="button"
                      class="secondary-button"
                      :disabled="isProductBusy(product.id)"
                      @click="startViewProduct(product.id)"
                    >
                      <span class="button-content">
                        <span class="button-icon button-icon--view" aria-hidden="true" />
                        <span>{{ product.operationsCount }} этапов</span>
                      </span>
                    </button>
                  </td>
                  <td>
                    <button
                      type="button"
                      class="secondary-button"
                      :disabled="isProductBusy(product.id)"
                      @click="startCopyProduct(product.id)"
                    >
                      <span class="button-content">
                        <span class="button-icon button-icon--copy" aria-hidden="true" />
                        <span>Копировать</span>
                      </span>
                    </button>
                  </td>
                  <td>
                    <button
                      type="button"
                      class="ghost-button ghost-button--danger"
                      :disabled="isProductBusy(product.id)"
                      @click="openDeleteConfirmation(product)"
                    >
                      <span class="button-content">
                        <span class="button-icon button-icon--delete" aria-hidden="true" />
                        <span>Удалить</span>
                      </span>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-if="!listLoading && filteredProducts.length === 0"
            class="empty-table-state"
          >
            <p>По текущему фильтру изделия не найдены.</p>
          </div>
        </article>
      </section>

      <section v-else>
        <article class="constructor-panel">
          <div class="panel-head">
            <div>
              <h2>Пользователи и доступы</h2>
            </div>

            <button
              type="button"
              class="primary-button"
              :disabled="editingUserId !== null"
              @click="startCreateUser"
            >
              <span class="button-content">
                <span class="button-icon button-icon--plus" aria-hidden="true" />
                <span>Добавить пользователя</span>
              </span>
            </button>
          </div>

          <div class="toolbar">
            <label class="field field--inline">
              <span class="field__label">Фильтр по имени</span>
              <div class="filter-input-wrap">
                <input
                  v-model="userFilter"
                  type="text"
                  class="text-input text-input--with-action"
                  placeholder="Например, Анна"
                />
                <button
                  v-if="userFilter"
                  type="button"
                  class="field-action"
                  aria-label="Очистить фильтр"
                  title="Очистить фильтр"
                  @click="userFilter = ''"
                >
                  <span class="field-action__icon" aria-hidden="true" />
                </button>
              </div>
            </label>

            <div class="field field--inline">
              <span class="field__label">Отображение</span>
              <div class="segmented-control" role="group" aria-label="Отображение пользователей">
                <button
                  v-for="option in visibilityOptions"
                  :key="option.value"
                  type="button"
                  class="segmented-control__button segmented-control__button--icon"
                  :class="{
                    'segmented-control__button--active':
                      userVisibility === option.value,
                  }"
                  :title="option.label"
                  :aria-label="option.label"
                  @click="userVisibility = option.value"
                >
                  <span
                    class="toolbar-icon"
                    :class="`toolbar-icon--${option.icon}`"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>

            <div class="field field--inline">
              <span class="field__label">Сортировка</span>
              <div class="segmented-control" role="group" aria-label="Сортировка пользователей">
                <button
                  v-for="option in userSortOptions"
                  :key="option.field"
                  type="button"
                  class="segmented-control__button segmented-control__button--icon"
                  :class="{
                    'segmented-control__button--active':
                      isUserSortFieldActive(option.field),
                  }"
                  :title="`${option.label} (${getUserSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                  :aria-label="`${option.label} (${getUserSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                  @click="toggleUserSort(option.field)"
                >
                  <span
                    class="toolbar-icon"
                    :class="[
                      `toolbar-icon--${option.icon}`,
                      `toolbar-icon--${getUserSortDirection(option.field)}`,
                    ]"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>
          </div>

          <div v-if="usersError" class="banner banner--error">
            <p>{{ usersError }}</p>
            <button type="button" class="ghost-button" @click="loadUsers">
              <span class="button-content">
                <span class="button-icon button-icon--refresh" aria-hidden="true" />
                <span>Повторить</span>
              </span>
            </button>
          </div>

          <div v-if="usersLoading" class="banner">
            <p>Загрузка пользователей...</p>
          </div>

          <div v-else class="table-wrap">
            <table class="products-table users-table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Телефон</th>
                  <th>Автор</th>
                  <th>Права</th>
                  <th>Статус</th>
                  <th>Дата создания</th>
                  <th>Дата изменения</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="user in filteredUsers"
                  :key="user.id"
                  :class="{
                    'table-row--locked': isUserLocked(user.id),
                    'table-row--editing': isEditingUser(user.id),
                  }"
                >
                  <td>
                    <div v-if="isEditingUser(user.id)" class="user-cell">
                      <input
                        :value="editingUserDraft?.name ?? ''"
                        type="text"
                        class="text-input users-table__input"
                        placeholder="Имя пользователя"
                        @input="handleUserNameInput(user.id, $event)"
                      />
                      <p v-if="getUserNameError(user)" class="field-error">
                        {{ getUserNameError(user) }}
                      </p>
                    </div>
                    <button
                      v-else
                      type="button"
                      class="table-link"
                      :disabled="isUserLocked(user.id)"
                      @click="startEditUser(user)"
                    >
                      <span class="button-content">
                        <span class="button-icon button-icon--edit" aria-hidden="true" />
                        <span>{{ getDisplayedUser(user).name || "Без имени" }}</span>
                      </span>
                    </button>
                  </td>
                  <td>
                    <div v-if="isEditingUser(user.id)" class="user-cell">
                      <input
                        :value="editingUserDraft?.phone ?? ''"
                        type="text"
                        class="text-input users-table__input"
                        placeholder="+7 999 123-45-67"
                        @input="handleUserPhoneInput(user.id, $event)"
                      />
                      <p v-if="getUserPhoneError(user)" class="field-error">
                        {{ getUserPhoneError(user) }}
                      </p>
                    </div>
                    <span v-else>{{ getDisplayedUser(user).phone || "—" }}</span>
                  </td>
                  <td>{{ getDisplayedUser(user).author || "—" }}</td>
                  <td>
                    <div class="user-cell">
                      <div class="role-group">
                        <button
                          v-for="role in userRoleOptions"
                          :key="role.value"
                          type="button"
                          class="role-button"
                          :class="{
                            'role-button--active':
                              getDisplayedUser(user).roles.includes(role.value),
                          }"
                          :title="role.label"
                          :aria-label="role.label"
                          :disabled="isUserLocked(user.id)"
                          @click="handleUserRoleAction(user, role.value)"
                        >
                          <span
                            class="role-icon"
                            :class="`role-icon--${role.icon}`"
                            aria-hidden="true"
                          />
                        </button>
                      </div>
                      <p v-if="getUserRolesError(user)" class="field-error">
                        {{ getUserRolesError(user) }}
                      </p>
                    </div>
                  </td>
                  <td>
                    <button
                      type="button"
                      class="status-button"
                      :class="{
                        'status-button--active': getDisplayedUser(user).isActive,
                        'status-button--inactive': !getDisplayedUser(user).isActive,
                      }"
                      :disabled="isUserLocked(user.id)"
                      @click="handleUserStatusAction(user)"
                    >
                      <span class="button-content">
                        <span
                          class="button-icon"
                          :class="getDisplayedUser(user).isActive ? 'button-icon--pause' : 'button-icon--check'"
                          aria-hidden="true"
                        />
                        <span>
                          {{
                            getDisplayedUser(user).isActive
                              ? "Деактивировать"
                              : "Активировать"
                          }}
                        </span>
                      </span>
                    </button>
                  </td>
                  <td>{{ getDisplayedUser(user).createdAt || "—" }}</td>
                  <td>{{ getDisplayedUser(user).updatedAt || "—" }}</td>
                  <td>
                    <div class="table-actions">
                      <button
                        v-if="getDisplayedUser(user).passwordHash"
                        type="button"
                        class="ghost-button"
                        :disabled="isUserLocked(user.id)"
                        @click="void handleResetUserPassword(user)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--reset-password" aria-hidden="true" />
                          <span>Сбросить пароль</span>
                        </span>
                      </button>
                      <button
                        type="button"
                        class="ghost-button ghost-button--danger"
                        :disabled="isUserLocked(user.id)"
                        @click="openUserDeleteConfirmation(user)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--delete" aria-hidden="true" />
                          <span>Удалить</span>
                        </span>
                      </button>
                      <button
                        v-if="isEditingUser(user.id)"
                        type="button"
                        class="secondary-button"
                        :disabled="!canSaveUser(user)"
                        @click="saveUserChanges(user)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--save" aria-hidden="true" />
                          <span>Сохранить изменения</span>
                        </span>
                      </button>
                      <button
                        v-if="isEditingUser(user.id)"
                        type="button"
                        class="ghost-button"
                        @click="cancelUserEdit"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--close" aria-hidden="true" />
                          <span>Отменить изменения</span>
                        </span>
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-if="!usersLoading && filteredUsers.length === 0"
            class="empty-table-state"
          >
            <p>По текущему фильтру пользователи не найдены.</p>
          </div>
        </article>
      </section>
    </section>

    <div
      v-if="changePasswordModalOpen"
      class="modal-backdrop"
      @click.self="closeChangePasswordModal"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Пароль пользователя</p>
          <h2>Изменить пароль</h2>

          <label class="field">
            <span class="field__label">Текущий пароль</span>
            <input
              v-model="changePasswordCurrent"
              type="password"
              class="text-input"
              autocomplete="current-password"
              placeholder="Если пароль уже задан"
            />
          </label>

          <label class="field">
            <span class="field__label">Новый пароль</span>
            <input
              v-model="changePasswordNext"
              type="password"
              class="text-input"
              autocomplete="new-password"
              placeholder="Не менее 8 символов"
            />
          </label>

          <label class="field">
            <span class="field__label">Подтверждение нового пароля</span>
            <input
              v-model="changePasswordConfirm"
              type="password"
              class="text-input"
              autocomplete="new-password"
              placeholder="Повторите новый пароль"
            />
          </label>

          <p v-if="changePasswordError" class="field-error">{{ changePasswordError }}</p>
        </div>

        <div class="confirm-modal__actions">
          <button type="button" class="ghost-button" @click="closeChangePasswordModal">
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="primary-button"
            :disabled="changePasswordSaving"
            @click="void submitPasswordChange()"
          >
            <span class="button-content">
              <span class="button-icon button-icon--save" aria-hidden="true" />
              <span>{{ changePasswordSaving ? "Сохранение..." : "Сохранить пароль" }}</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="isBrigadierOrderModalOpen"
      class="modal-backdrop"
      @click.self="closeBrigadierOrderModal"
    >
      <section class="modal brigadier-modal" role="dialog" aria-modal="true">
        <div class="modal__head">
          <div>
            <h2>{{ brigadierModalTitle }}</h2>
            <p class="modal__description">{{ brigadierModalDescription }}</p>
          </div>

          <button
            type="button"
            class="ghost-button"
            @click="closeBrigadierOrderModal"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Закрыть</span>
            </span>
          </button>
        </div>

        <div v-if="brigadierModalError" class="banner banner--error">
          <p>{{ brigadierModalError }}</p>
        </div>

        <div v-if="brigadierModalLoading" class="banner">
          <p>Загрузка заказа...</p>
        </div>

        <form
          v-else-if="brigadierModalProduct"
          class="order-form"
          @submit.prevent="void saveBrigadierOrder()"
        >
          <div class="order-form__header">
            <div class="order-form__summary">
              <div class="summary-card">
                <span class="section-label">Изделие</span>
                <strong>
                  {{ brigadierModalProduct.name }} · {{ brigadierModalProduct.version }}
                </strong>
              </div>
            </div>

            <div class="order-form__meta">
              <label class="field">
                <span class="field__label">Номер заказа</span>
                <input
                  :value="brigadierModalOrderNumber"
                  type="text"
                  class="text-input"
                  data-field="brigadier-order-number"
                  :readonly="brigadierModalMode === 'manage'"
                  placeholder="Например, FC-0001"
                  @input="handleBrigadierOrderNumberInput"
                />
                <p v-if="brigadierOrderNumberError" class="field-error">
                  {{ brigadierOrderNumberError }}
                </p>
              </label>

              <label class="field order-form__quantity">
                <span class="field__label">Количество изделий</span>
                <input
                  :value="brigadierModalQuantity"
                  type="text"
                  inputmode="numeric"
                  class="text-input"
                  :readonly="brigadierModalMode === 'manage'"
                  data-field="brigadier-quantity"
                  placeholder="Например, 12"
                  @input="handleBrigadierQuantityInput"
                />
                <p v-if="brigadierQuantityError" class="field-error">
                  {{ brigadierQuantityError }}
                </p>
              </label>
            </div>
          </div>

          <section class="order-assignments">
            <div class="operations-section__head">
              <div>
                <span class="field__label">Назначение исполнителей</span>
                <p class="field__hint">
                  Для каждой операции выберите исполнителя с ролью `исполнитель`.
                </p>
              </div>
            </div>

            <div v-if="brigadierWorkerUsers.length === 0" class="banner banner--error">
              <p>Нет активных пользователей с ролью исполнителя.</p>
            </div>

            <datalist id="brigadier-workers-list">
              <option
                v-for="worker in brigadierWorkerUsers"
                :key="worker.id"
                :value="worker.name"
              />
            </datalist>

            <div v-if="brigadierModalAssignments.length === 0" class="empty-table-state">
              <p>У этого изделия нет назначаемых операций.</p>
            </div>

            <div v-else class="assignment-list">
              <div
                v-for="assignment in brigadierModalAssignments"
                :key="assignment.operationId"
                class="assignment-row"
              >
                <div class="assignment-row__label">
                  {{ assignment.operationLabel }}
                </div>
                <div class="assignment-row__control">
                  <div class="assignment-input-wrap">
                    <input
                      :value="assignment.workerName"
                      type="text"
                      class="text-input text-input--with-clear"
                      list="brigadier-workers-list"
                      :data-brigadier-operation-id="assignment.operationId"
                      placeholder="Выберите исполнителя"
                      @input="handleBrigadierAssignmentInput(assignment.operationId, $event)"
                    />
                    <button
                      v-if="assignment.workerName"
                      type="button"
                      class="field-action field-action--right"
                      aria-label="Очистить исполнителя"
                      title="Очистить исполнителя"
                      @click="clearBrigadierAssignment(assignment.operationId)"
                    >
                      <span class="field-action__icon" aria-hidden="true" />
                    </button>
                  </div>
                  <p
                    v-if="getBrigadierAssignmentError(assignment)"
                    class="field-error"
                  >
                    {{ getBrigadierAssignmentError(assignment) }}
                  </p>
                </div>
              </div>
            </div>
          </section>

          <div class="modal__actions">
            <button
              v-if="brigadierSaveIssue"
              type="button"
              class="field-error-link field-error--actions"
              @click="scrollToBrigadierSaveIssue"
            >
              {{ brigadierSaveIssue.message }}
            </button>

            <button
              type="submit"
              class="primary-button"
              :disabled="!brigadierModalCanSave || brigadierSaveLoading"
            >
              <span class="button-content">
                <span class="button-icon button-icon--save" aria-hidden="true" />
                <span>{{ brigadierSaveLoading ? "Сохранение..." : brigadierModalSaveLabel }}</span>
              </span>
            </button>

            <button
              type="button"
              class="ghost-button"
              @click="closeBrigadierOrderModal"
            >
              <span class="button-content">
                <span class="button-icon button-icon--close" aria-hidden="true" />
                <span>Отменить</span>
              </span>
            </button>
          </div>
        </form>
      </section>
    </div>

    <div
      v-if="isModalOpen"
      class="modal-backdrop"
      @click.self="closeProductModal"
    >
      <section class="modal" role="dialog" aria-modal="true">
        <div class="modal__head">
          <div>
            <h2>{{ modalTitle }}</h2>
            <p class="modal__description">{{ modalDescription }}</p>
          </div>

          <button type="button" class="ghost-button" @click="closeProductModal">
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Закрыть</span>
            </span>
          </button>
        </div>

        <div v-if="modalError" class="banner banner--error">
          <p>{{ modalError }}</p>
        </div>

        <div v-if="modalLoading" class="banner">
          <p>Загрузка изделия...</p>
        </div>

        <form
          v-else
          class="product-form"
          @submit.prevent="saveProductToApi"
        >
          <div class="product-form__header">
            <div class="form-grid">
              <label class="field">
                <span class="field__label">Наименование изделия</span>
                <input
                  v-model="productName"
                  type="text"
                  class="text-input"
                  :readonly="isViewMode"
                  data-field="product-name"
                  placeholder="Например, кошелек Daily Fold"
                />
                <p
                  v-if="shouldShowFieldError(productName, productNameError)"
                  class="field-error"
                >
                  {{ productNameError }}
                </p>
              </label>

              <label class="field">
                <span class="field__label">Версия</span>
                <input
                  v-model="productVersion"
                  type="text"
                  class="text-input"
                  :readonly="isViewMode"
                  data-field="product-version"
                  placeholder="Например, 1.0"
                />
                <p
                  v-if="shouldShowFieldError(productVersion, productVersionError)"
                  class="field-error"
                >
                  {{ productVersionError }}
                </p>
              </label>
            </div>

            <p v-if="productIdentityError" class="field-error field-error--inline">
              {{ productIdentityError }}
            </p>
          </div>

          <section class="operations-section">
            <div class="operations-section__head">
              <div>
                <span class="field__label">Таблица-дерево операций</span>
                <p class="field__hint">
                  На одном уровне внутри одного родителя имя операции должно быть
                  уникальным и не может быть пустым.
                </p>
              </div>
            </div>

            <div
              v-if="operationTree.length === 0"
              class="empty-state empty-state--operations"
            >
              <p>Операции пока не добавлены.</p>
              <p>Начните с корневого этапа, например `Крой` или `Пошив`.</p>
            </div>

            <p
              v-if="shouldShowValidation && operationTreeError"
              class="field-error field-error--section"
            >
              {{ operationTreeError }}
            </p>

            <div class="operation-table-wrap">
              <table class="operation-table">
                <thead>
                  <tr>
                    <th>Операция</th>
                    <th>Тип</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in flatOperationRows" :key="row.id">
                    <td>
                      <div
                        class="operation-cell"
                        :style="{ '--level': String(row.level) }"
                      >
                        <span v-if="row.level > 0" class="operation-branch" />

                        <div class="operation-editor">
                          <div v-if="isViewMode" class="operation-text">
                            {{ row.name }}
                          </div>
                          <input
                            v-else
                            :value="row.name"
                            type="text"
                            class="operation-input"
                            :data-operation-id="row.id"
                            :placeholder="
                              row.isGroup
                                ? 'Название группы операций'
                                : 'Название операции'
                            "
                            @input="handleOperationNameInput(row.id, $event)"
                          />

                          <p
                            v-if="!isViewMode && shouldShowOperationError(row)"
                            class="field-error"
                          >
                            {{ operationErrors[row.id] }}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span
                        class="operation-badge"
                        :class="{
                          'operation-badge--group': row.isGroup,
                          'operation-badge--leaf': !row.isGroup,
                        }"
                      >
                        {{ row.isGroup ? "Группа" : "Операция" }}
                      </span>
                    </td>
                    <td>
                      <div class="operation-actions">
                        <span v-if="isViewMode" class="readonly-note">
                          Только просмотр
                        </span>
                        <template v-else>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Переместить выше"
                            aria-label="Переместить выше"
                            :disabled="!row.canMoveUp"
                            @click="moveOperationUp(row.id)"
                          >
                            <span
                              class="action-icon action-icon--up"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Переместить ниже"
                            aria-label="Переместить ниже"
                            :disabled="!row.canMoveDown"
                            @click="moveOperationDown(row.id)"
                          >
                            <span
                              class="action-icon action-icon--down"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Переместить внутрь предыдущей операции"
                            aria-label="Переместить внутрь предыдущей операции"
                            :disabled="!row.canIndent"
                            @click="indentOperation(row.id)"
                          >
                            <span
                              class="action-icon action-icon--indent"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Поднять на уровень выше"
                            aria-label="Поднять на уровень выше"
                            :disabled="!row.canOutdent"
                            @click="outdentOperation(row.id)"
                          >
                            <span
                              class="action-icon action-icon--outdent"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Создать вложенную операцию"
                            aria-label="Создать вложенную операцию"
                            @click="addChildOperation(row.id)"
                          >
                            <span
                              class="action-icon action-icon--child"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Создать следующую операцию"
                            aria-label="Создать следующую операцию"
                            @click="addSiblingOperation(row.id)"
                          >
                            <span
                              class="action-icon action-icon--sibling"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="ghost-button ghost-button--danger"
                            @click="removeOperation(row.id)"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--delete" aria-hidden="true" />
                              <span>Удалить</span>
                            </span>
                          </button>
                        </template>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="!isViewMode" class="operations-footer">
              <button
                type="button"
                class="secondary-button secondary-button--add"
                data-field="add-root-operation"
                @click="addRootOperation"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--plus" aria-hidden="true" />
                  <span>
                    {{
                      operationTree.length > 0
                        ? "Добавить корневую операцию"
                        : "Добавить первую операцию"
                    }}
                  </span>
                </span>
              </button>
            </div>
          </section>

          <div class="modal__actions">
            <button
              v-if="saveBlockIssue && !isViewMode"
              type="button"
              class="field-error-link field-error--actions"
              @click="scrollToSaveBlockIssue"
            >
              {{ saveBlockIssue.message }}
            </button>

            <button
              v-if="!isViewMode"
              type="submit"
              class="primary-button"
              :class="{ 'primary-button--blocked': !canSaveProduct && !saveLoading }"
              :aria-disabled="!canSaveProduct"
              :disabled="saveLoading"
            >
              <span class="button-content">
                <span class="button-icon button-icon--save" aria-hidden="true" />
                <span>{{ saveLoading ? "Сохранение..." : "Сохранить изделие" }}</span>
              </span>
            </button>

            <button type="button" class="ghost-button" @click="closeProductModal">
              <span class="button-content">
                <span class="button-icon button-icon--close" aria-hidden="true" />
                <span>{{ isViewMode ? "Закрыть просмотр" : "Отменить" }}</span>
              </span>
            </button>
          </div>
        </form>
      </section>
    </div>

    <div
      v-if="isDeleteModalOpen && productPendingDelete"
      class="modal-backdrop"
      @click.self="closeDeleteConfirmation"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение удаления</p>
          <h2>Удалить изделие?</h2>
          <dl class="confirm-modal__details">
            <div>
              <dt>Наименование</dt>
              <dd>{{ productPendingDelete.name }}</dd>
            </div>
            <div>
              <dt>Версия</dt>
              <dd>{{ productPendingDelete.version }}</dd>
            </div>
          </dl>
          <p class="confirm-modal__description">
            Будет удалено изделие вместе с деревом его операций. Это действие
            нельзя отменить.
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            :disabled="isProductBusy(productPendingDelete.id)"
            @click="closeDeleteConfirmation"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="ghost-button ghost-button--danger confirm-modal__delete"
            :disabled="isProductBusy(productPendingDelete.id)"
            @click="handleDeleteProduct(productPendingDelete)"
          >
            <span class="button-content">
              <span class="button-icon button-icon--delete" aria-hidden="true" />
              <span>{{ isProductBusy(productPendingDelete.id) ? "Удаление..." : "Удалить" }}</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="isUserDeleteModalOpen && userPendingDelete"
      class="modal-backdrop"
      @click.self="closeUserDeleteConfirmation"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение удаления</p>
          <h2>Удалить пользователя?</h2>
          <dl class="confirm-modal__details">
            <div>
              <dt>Имя</dt>
              <dd>{{ userPendingDelete.name || "Без имени" }}</dd>
            </div>
            <div>
              <dt>Статус</dt>
              <dd>{{ userPendingDelete.isActive ? "Активен" : "Деактивирован" }}</dd>
            </div>
          </dl>
          <p class="confirm-modal__description">
            Запись пользователя будет удалена из таблицы. Это действие нельзя
            отменить.
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            @click="closeUserDeleteConfirmation"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="ghost-button ghost-button--danger confirm-modal__delete"
            @click="deleteUser(userPendingDelete)"
          >
            <span class="button-content">
              <span class="button-icon button-icon--delete" aria-hidden="true" />
              <span>Удалить</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="isWorkerDayEndConfirmOpen"
      class="modal-backdrop"
      @click.self="closeWorkerDayEndConfirm"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение завершения</p>
          <h2>Закончить рабочий день?</h2>
          <p class="confirm-modal__description">
            Будут остановлены текущий активный таймер и рабочая смена исполнителя.
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            @click="closeWorkerDayEndConfirm"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="ghost-button ghost-button--danger confirm-modal__delete"
            :disabled="workerTimerSubmitting"
            @click="void endWorkerDay()"
          >
            <span class="button-content">
              <span class="button-icon button-icon--stop" aria-hidden="true" />
              <span>Закончить день</span>
            </span>
          </button>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.page {
  --color-bg: #f4f7fa;
  --color-surface: #ffffff;
  --color-surface-alt: #e9eef3;
  --color-surface-soft: #e3eff8;
  --color-border: #d6dee6;
  --color-muted: #8a96a3;
  --color-primary: #2f6ea3;
  --color-primary-hover: #245e8e;
  --color-accent-muted: #245e8e;
  --color-text: #1f2a33;
  --color-text-secondary: #5f6b76;
  --color-text-muted: #86919c;
  --color-success: #5e8f74;
  --color-warning: #c39a52;
  --color-danger: #c56b6b;
  --color-neutral: #8a96a3;
  padding: 24px;
  background: var(--color-bg);
  color: var(--color-text);
}

.shell {
  min-height: calc(100vh - 48px);
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: 28px;
  background: var(--color-bg);
  box-shadow: 0 20px 44px rgba(31, 42, 51, 0.08);
  backdrop-filter: blur(12px);
}

.auth-shell {
  min-height: calc(100vh - 48px);
  display: grid;
  place-items: center;
}

.auth-card {
  width: min(520px, 100%);
  display: grid;
  gap: 18px;
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: 28px;
  background: var(--color-surface);
  box-shadow: 0 18px 36px rgba(31, 42, 51, 0.08);
}

.auth-card__head {
  display: grid;
  gap: 14px;
}

.auth-card__description {
  margin: 10px 0 0;
  color: var(--color-text-secondary);
}

.auth-card__actions {
  display: flex;
  justify-content: flex-end;
}

.header {
  display: flex;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 28px;
}

.brand-block {
  flex: 0 0 auto;
  align-self: center;
}

h1,
h2 {
  margin: 0;
  color: var(--color-text);
  font-family: "Sora", "Inter", sans-serif;
}

h2 {
  font-size: 1.5rem;
}

.brand-logo-frame {
  width: clamp(360px, 44vw, 760px);
  height: 180px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-logo-frame--auth {
  width: min(460px, 100%);
  height: 140px;
}

.brand-logo {
  display: block;
  width: 364%;
  height: 504px;
  object-fit: cover;
  object-position: center;
}

.tabs {
  display: inline-flex;
  gap: 10px;
  padding: 8px;
  border-radius: 18px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  flex-wrap: wrap;
  align-self: center;
}

.current-user-card {
  min-width: 260px;
  display: grid;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
  text-align: left;
}

.current-user-card__identity {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.current-user-card strong {
  font-size: 1rem;
  line-height: 1;
  font-family: "Sora", "Inter", sans-serif;
}

.current-user-card__roles {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  line-height: 1;
}

.current-user-card__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 0;
}

.current-user-card .section-label {
  margin: 0;
  white-space: nowrap;
}

.current-user-card .ghost-button {
  padding: 8px 10px;
  font-size: 0.86rem;
}

.tab-button,
.primary-button,
.secondary-button,
.ghost-button,
.status-button {
  border: 0;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease;
}

.tab-button:hover,
.primary-button:hover,
.secondary-button:hover,
.ghost-button:hover,
.status-button:hover {
  transform: translateY(-1px);
}

.primary-button:disabled,
.secondary-button:disabled,
.ghost-button:disabled,
.status-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
}

.button-content {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.tab-button {
  padding: 14px 20px;
  border-radius: 14px;
  background: transparent;
  color: var(--color-text-secondary);
  font-weight: 600;
}

.tab-button--active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.16);
}

.placeholder-panel,
.constructor-panel,
.modal {
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface);
  box-shadow: 0 18px 36px rgba(31, 42, 51, 0.08);
}

.placeholder-panel {
  padding: 28px;
}

.placeholder-label,
.section-label {
  margin: 0 0 10px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.constructor-panel {
  padding: 22px;
}

.panel-head,
.modal__head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.panel-head {
  margin-bottom: 20px;
}

.panel-head--stacked {
  flex-direction: column;
  align-items: flex-start;
}

.worker-panel {
  display: grid;
  gap: 22px;
}

.worker-panel__head {
  margin-bottom: 0;
}

.worker-panel__subtitle {
  margin: 10px 0 0;
  color: var(--color-text-secondary);
}

.worker-summary {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.worker-summary__card {
  display: grid;
  gap: 8px;
  padding: 18px 20px;
  border-radius: 18px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}

.worker-summary__card strong {
  color: var(--color-text);
  font-size: 1.1rem;
  font-family: "Sora", "Inter", sans-serif;
}

.worker-summary__value {
  font-weight: 700;
  font-size: 2rem;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
  font-family: "Sora", "Inter", sans-serif;
}

.worker-timer-bar,
.worker-group__timers {
  display: grid;
  gap: 14px;
}

.worker-timer-bar {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.worker-groups {
  display: grid;
  gap: 18px;
}

.worker-group {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 22px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}

.worker-group__head {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.worker-group__head h3 {
  margin: 0;
  color: var(--color-text);
  font-size: 1.05rem;
}

.worker-group__title {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.worker-group__chevron {
  width: 12px;
  height: 12px;
  border-right: 2px solid var(--color-text-secondary);
  border-bottom: 2px solid var(--color-text-secondary);
  transform: rotate(45deg);
  transition: transform 0.18s ease;
  flex: 0 0 auto;
}

.worker-group__chevron--expanded {
  transform: rotate(225deg);
}

.statistics-panel {
  display: grid;
  gap: 22px;
}

.statistics-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.statistics-kpis {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(7, minmax(0, 1fr));
}

.statistics-kpi-card,
.statistics-card {
  border: 1px solid var(--color-border);
  border-radius: 20px;
  background: var(--color-surface-alt);
}

.statistics-kpi-card {
  display: grid;
  gap: 10px;
  padding: 16px 18px;
}

.statistics-kpi-card strong {
  font-family: "Sora", "Inter", sans-serif;
  font-size: 1.45rem;
  color: var(--color-text);
}

.statistics-grid {
  display: grid;
  gap: 18px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.statistics-card {
  display: grid;
  gap: 18px;
  padding: 18px;
}

.statistics-card--wide {
  grid-column: span 2;
}

.statistics-card__head h3 {
  margin: 0;
  color: var(--color-text);
  font-size: 1.05rem;
}

.statistics-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
}

.statistics-legend__item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 0.88rem;
}

.statistics-legend__swatch {
  width: 12px;
  height: 12px;
  border-radius: 4px;
}

.statistics-legend__swatch--operation {
  background: var(--color-primary);
}

.statistics-legend__swatch--preparation {
  background: var(--color-success);
}

.statistics-legend__swatch--break {
  background: var(--color-warning);
}

.statistics-legend__swatch--idle {
  background: var(--color-danger);
}

.stacked-chart {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(52px, 1fr));
  align-items: end;
}

.stacked-chart__item {
  display: grid;
  gap: 8px;
  justify-items: center;
}

.stacked-chart__column {
  width: 100%;
  height: 180px;
  display: flex;
  flex-direction: column-reverse;
  justify-content: flex-start;
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}

.stacked-chart__segment {
  display: block;
  width: 100%;
  min-height: 0;
}

.stacked-chart__value,
.stacked-chart__label {
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.stacked-chart__value {
  font-weight: 700;
  color: var(--color-text);
}

.statistics-bars {
  display: grid;
  gap: 14px;
}

.statistics-bar-row {
  display: grid;
  gap: 8px;
}

.statistics-bar-row__meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.statistics-bar-row__meta--secondary {
  margin-top: -2px;
}

.statistics-bar-row__meta strong {
  color: var(--color-text);
}

.statistics-bar-row__meta span {
  color: var(--color-text-secondary);
  font-size: 0.88rem;
}

.statistics-bar-row__track {
  height: 10px;
  border-radius: 999px;
  background: var(--color-surface);
  overflow: hidden;
}

.statistics-bar-row__fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--color-primary);
}

.statistics-bar-row__fill--muted {
  background: var(--color-text-muted);
}

.statistics-bar-row__fill--success {
  background: var(--color-success);
}

.mini-chart {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(36px, 1fr));
  align-items: end;
}

.mini-chart__item {
  display: grid;
  gap: 8px;
  justify-items: center;
}

.mini-chart__bar {
  display: block;
  width: 100%;
  height: 160px;
  min-height: 6px;
  align-self: end;
  border-radius: 14px;
  background: var(--color-danger);
}

.mini-chart__label {
  font-size: 0.76rem;
  color: var(--color-text-secondary);
}

.worker-timer-button {
  position: relative;
  width: 100%;
  padding: 16px 18px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  display: grid;
  gap: 10px;
  text-align: left;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    opacity 0.18s ease;
}

.worker-timer-button::before {
  content: "";
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 0;
  width: 0;
  border-radius: 0 999px 999px 0;
  background: var(--color-primary);
  opacity: 0;
  transition:
    width 0.18s ease,
    opacity 0.18s ease;
}

.worker-timer-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 28px rgba(31, 42, 51, 0.08);
}

.worker-timer-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
  box-shadow: none;
}

.worker-timer-button--secondary {
  background: var(--color-surface-alt);
}

.worker-timer-button--operation {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.worker-timer-button--active {
  border-color: var(--color-primary);
  background: linear-gradient(135deg, rgba(47, 110, 163, 0.22), var(--color-surface-soft));
  box-shadow:
    0 0 0 2px rgba(47, 110, 163, 0.18),
    0 18px 32px rgba(47, 110, 163, 0.16);
}

.worker-timer-button--active::before {
  width: 6px;
  opacity: 1;
}

.worker-timer-button--active .worker-timer-button__label,
.worker-timer-button--active .worker-timer-button__value,
.worker-timer-button--active .worker-timer-button__order,
.worker-timer-button--active .button-icon {
  color: var(--color-primary-hover);
}

.worker-timer-button__meta {
  display: grid;
  gap: 6px;
}

.worker-timer-button__heading {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.worker-timer-button__label {
  font-weight: 700;
  font-size: 1.3rem;
  line-height: 1.15;
}

.worker-timer-button__order {
  color: var(--color-primary-hover);
  font-size: 1.15rem;
  font-weight: 800;
  line-height: 1.1;
}

.worker-timer-button__value {
  font-weight: 700;
  font-size: 2rem;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
  font-family: "Sora", "Inter", sans-serif;
}

.modal__head {
  margin-bottom: 22px;
}

.modal__description {
  margin: 10px 0 0;
  max-width: 56ch;
  color: var(--color-text-secondary);
}

.primary-button {
  padding: 14px 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  color: #fff;
  font-weight: 700;
  box-shadow: 0 14px 28px rgba(47, 110, 163, 0.16);
}

.primary-button--blocked {
  opacity: 0.55;
  box-shadow: none;
}

.primary-button--blocked:hover {
  transform: none;
}

.secondary-button {
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--color-surface-alt);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  font-weight: 600;
}

.secondary-button--add {
  width: fit-content;
  background: var(--color-surface-soft);
  color: var(--color-text);
}

.ghost-button {
  padding: 10px 14px;
  border-radius: 12px;
  background: transparent;
  color: var(--color-text-secondary);
  font-weight: 600;
}

.ghost-button--danger {
  color: var(--color-danger);
}

.toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 16px;
  margin-bottom: 18px;
}

.field {
  display: grid;
  gap: 10px;
  align-content: start;
}

.field--inline {
  align-content: start;
}

.toolbar > .field--inline:not(:first-child) {
  width: fit-content;
  justify-self: start;
}

.filter-input-wrap {
  position: relative;
}

.segmented-control {
  display: inline-flex;
  gap: 6px;
  padding: 6px;
  border-radius: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.segmented-control__button {
  border: 0;
  border-radius: 12px;
  padding: 12px 14px;
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.segmented-control__button--icon {
  width: 40px;
  height: 40px;
  padding: 0;
  display: grid;
  place-items: center;
}

.segmented-control__button:hover {
  transform: translateY(-1px);
}

.segmented-control__button--active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.12);
}

.field__label {
  font-size: 0.88rem;
  font-weight: 700;
  color: var(--color-text-secondary);
}

.field__hint {
  margin: 6px 0 0;
  font-size: 0.92rem;
  color: var(--color-text-muted);
}

.text-input,
.select-input,
.operation-input,
.operation-text {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  background: var(--color-surface);
  color: var(--color-text);
}

.text-input,
.select-input {
  padding: 14px 16px;
}

.text-input--with-action {
  padding-left: 52px;
}

.text-input--with-clear {
  padding-right: 52px;
}

.field-action {
  position: absolute;
  top: 50%;
  left: 8px;
  transform: translateY(-50%);
  border: 0;
  border-radius: 10px;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  padding: 0;
  background: var(--color-surface-soft);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.field-action--right {
  left: auto;
  right: 8px;
}

.field-action__icon {
  position: relative;
  width: 14px;
  height: 14px;
}

.field-action__icon::before,
.field-action__icon::after {
  content: "";
  position: absolute;
  top: 6px;
  left: 0;
  width: 14px;
  height: 2px;
  border-radius: 999px;
  background: currentColor;
}

.field-action__icon::before {
  transform: rotate(45deg);
}

.field-action__icon::after {
  transform: rotate(-45deg);
}

.toolbar-icon {
  position: relative;
  width: 18px;
  height: 18px;
  display: inline-block;
}

.toolbar-icon::before,
.toolbar-icon::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  background: currentColor;
}

.toolbar-icon--all::before,
.toolbar-icon--all::after {
  width: 14px;
  height: 2px;
  left: 2px;
}

.toolbar-icon--all::before {
  top: 5px;
  box-shadow: 0 5px 0 0 currentColor;
}

.toolbar-icon--all::after {
  top: 14px;
}

.toolbar-icon--active::before {
  inset: 2px;
  border: 2px solid currentColor;
  background: transparent;
}

.toolbar-icon--active::after {
  width: 6px;
  height: 6px;
  top: 6px;
  left: 6px;
}

.toolbar-icon--inactive::before {
  inset: 2px;
  border: 2px solid currentColor;
  background: transparent;
}

.toolbar-icon--inactive::after {
  width: 16px;
  height: 2px;
  top: 8px;
  left: 1px;
  transform: rotate(-45deg);
}

.toolbar-icon--asc::after {
  width: 10px;
  height: 6px;
  top: 1px;
  left: 4px;
  clip-path: polygon(50% 0, 0 100%, 100% 100%);
}

.toolbar-icon--desc::after {
  width: 10px;
  height: 6px;
  top: 11px;
  left: 4px;
  clip-path: polygon(0 0, 100% 0, 50% 100%);
}

.toolbar-icon--name::before {
  width: 10px;
  height: 2px;
  top: 5px;
  left: 2px;
  box-shadow:
    0 4px 0 0 currentColor,
    0 8px 0 0 currentColor;
}

.toolbar-icon--name::after {
  left: 9px;
}

.toolbar-icon--version::before {
  width: 2px;
  height: 12px;
  top: 3px;
  left: 5px;
  box-shadow: 6px 0 0 0 currentColor;
}

.toolbar-icon--version::after {
  left: 9px;
}

.toolbar-icon--created::before {
  width: 12px;
  height: 12px;
  inset: 3px;
  border: 2px solid currentColor;
  background: transparent;
}

.toolbar-icon--created {
  box-shadow: inset 0 0 0 0 currentColor;
}

.toolbar-icon--created::after {
  width: 2px;
  height: 5px;
  top: 6px;
  left: 8px;
  transform-origin: bottom center;
  box-shadow: 3px -1px 0 0 currentColor;
}

.operation-input,
.operation-text {
  padding: 10px 12px;
}

.operation-text {
  min-height: 44px;
  display: flex;
  align-items: center;
  background: var(--color-surface-alt);
}

.table-wrap,
.operation-table-wrap {
  overflow-x: auto;
}

.products-table,
.operation-table {
  width: 100%;
  border-collapse: collapse;
}

.products-table th,
.products-table td,
.operation-table th,
.operation-table td {
  padding: 16px 14px;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}

.products-table th,
.operation-table th {
  font-size: 0.82rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.products-table tbody tr:last-child td,
.operation-table tbody tr:last-child td {
  border-bottom: 0;
}

.products-table tbody tr td,
.operation-table tbody tr td {
  transition: background-color 0.18s ease;
}

.products-table tbody tr:hover td,
.products-table tbody tr:focus-within td,
.operation-table tbody tr:hover td,
.operation-table tbody tr:focus-within td {
  background: var(--color-surface-soft);
}

.table-row--locked {
  opacity: 0.42;
}

.table-row--locked td {
  pointer-events: none;
}

.table-row--editing td {
  background: var(--color-surface-soft);
}

.status-button {
  min-width: 148px;
  padding: 10px 14px;
  border-radius: 999px;
  font-weight: 700;
}

.status-button--active {
  background: rgba(94, 143, 116, 0.16);
  color: var(--color-text);
}

.status-button--inactive {
  background: rgba(138, 150, 163, 0.14);
  color: var(--color-text-secondary);
}

.empty-table-state {
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}

.banner {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.banner p {
  margin: 0;
}

.banner--error {
  background: rgba(197, 107, 107, 0.12);
  color: var(--color-text);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(31, 42, 51, 0.24);
  backdrop-filter: blur(8px);
}

.modal {
  width: min(1120px, calc(100vw - 48px));
  max-height: calc(100vh - 48px);
  padding: 24px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.confirm-modal {
  width: min(520px, calc(100vw - 48px));
  padding: 24px;
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface);
  box-shadow: 0 18px 36px rgba(31, 42, 51, 0.1);
}

.confirm-modal__content {
  display: grid;
  gap: 12px;
}

.confirm-modal__eyebrow {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.confirm-modal__description {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.55;
}

.confirm-modal__details {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-surface-alt);
}

.confirm-modal__details div {
  display: grid;
  gap: 4px;
}

.confirm-modal__details dt {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.confirm-modal__details dd {
  margin: 0;
  color: var(--color-text);
  font-weight: 600;
}

.confirm-modal__actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 22px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.confirm-modal__delete {
  min-width: 132px;
}

.product-form {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 18px;
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
}

.product-form__header {
  display: grid;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--color-border);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}

.field-error {
  margin: 0;
  color: var(--color-danger);
  font-size: 0.9rem;
}

.field-error-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-primary);
  font: inherit;
  appearance: none;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
  cursor: pointer;
}

.field-error-link:hover {
  color: var(--color-primary-hover);
}

.field-error--section {
  margin-top: -6px;
}

.field-error--inline {
  margin-top: -6px;
}

.table-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.subtabs {
  display: inline-flex;
  gap: 8px;
  padding: 6px;
  border-radius: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.subtab-button {
  padding: 10px 16px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.subtab-button:hover {
  transform: translateY(-1px);
}

.subtab-button--active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.12);
}

.brigadier-table .primary-button {
  padding: 10px 14px;
  box-shadow: 0 10px 18px rgba(47, 110, 163, 0.12);
}

.duration-badge {
  display: inline-flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 999px;
  background: var(--color-surface-soft);
  color: var(--color-primary-hover);
  font-weight: 700;
  white-space: nowrap;
  font-family: "Sora", "Inter", sans-serif;
}

.brigadier-modal {
  width: min(980px, calc(100vw - 48px));
}

.order-form {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 18px;
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
}

.order-form__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--color-border);
}

.order-form__summary {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.order-form__meta {
  display: grid;
  gap: 12px;
}

.summary-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}

.summary-card strong {
  color: var(--color-text);
}

.order-form__quantity {
  align-self: start;
}

.order-assignments {
  display: grid;
  gap: 14px;
  min-height: 0;
  overflow: auto;
  padding-right: 6px;
}

.assignment-list {
  display: grid;
  gap: 12px;
}

.assignment-row {
  display: grid;
  grid-template-columns: minmax(220px, 0.9fr) minmax(260px, 1fr);
  gap: 16px;
  align-items: start;
  padding: 16px;
  border-radius: 18px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}

.assignment-row__label {
  font-weight: 600;
  color: var(--color-text);
  line-height: 1.5;
}

.assignment-row__control {
  display: grid;
  gap: 8px;
}

.assignment-input-wrap {
  position: relative;
}

.table-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-text);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.table-link:hover {
  color: var(--color-primary-hover);
}

.user-cell {
  display: grid;
  gap: 8px;
}

.users-table__input {
  min-width: 220px;
}

.hash-value {
  display: inline-block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 6px 10px;
  border-radius: 10px;
  background: var(--color-surface-alt);
  color: var(--color-text-secondary);
  font-size: 0.78rem;
}

.role-group {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.role-button {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease;
}

.role-button:hover {
  transform: translateY(-1px);
}

.role-button:disabled {
  cursor: default;
  opacity: 0.7;
}

.role-button--active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.12);
}

.role-icon {
  position: relative;
  width: 18px;
  height: 18px;
  display: inline-block;
}

.role-icon::before,
.role-icon::after {
  content: "";
  position: absolute;
  background: currentColor;
}

.role-icon--worker::before {
  top: 1px;
  left: 5px;
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.role-icon--worker::after {
  top: 10px;
  left: 3px;
  width: 12px;
  height: 6px;
  border-radius: 999px 999px 4px 4px;
}

.role-icon--brigadier::before {
  top: 1px;
  left: 2px;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  box-shadow: 8px 0 0 0 currentColor;
}

.role-icon--brigadier::after {
  top: 9px;
  left: 1px;
  width: 16px;
  height: 6px;
  border-radius: 999px;
}

.role-icon--constructor::before {
  top: 3px;
  left: 3px;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  background: transparent;
  transform: rotate(45deg);
}

.role-icon--constructor::after {
  top: 8px;
  left: 1px;
  width: 16px;
  height: 2px;
  border-radius: 999px;
}

.role-icon--admin::before {
  top: 1px;
  left: 4px;
  width: 10px;
  height: 14px;
  background: transparent;
  border: 2px solid currentColor;
  border-radius: 10px 10px 6px 6px;
}

.role-icon--admin::after {
  top: 5px;
  left: 7px;
  width: 4px;
  height: 6px;
  border-radius: 999px;
}

.role-icon--stats::before {
  bottom: 2px;
  left: 2px;
  width: 3px;
  height: 8px;
  border-radius: 2px;
  box-shadow: 5px -3px 0 0 currentColor, 10px -6px 0 0 currentColor;
}

.role-icon--stats::after {
  left: 1px;
  right: 1px;
  bottom: 1px;
  height: 2px;
}

.role-icon--users::before {
  top: 2px;
  left: 3px;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  box-shadow: 7px 0 0 0 currentColor;
}

.role-icon--users::after {
  top: 9px;
  left: 1px;
  width: 16px;
  height: 6px;
  border-radius: 999px;
}

.button-icon {
  position: relative;
  width: 16px;
  height: 16px;
  display: inline-block;
  flex: 0 0 auto;
}

.button-icon::before,
.button-icon::after {
  content: "";
  position: absolute;
  background: currentColor;
  border-radius: 999px;
}

.button-icon--play::before {
  top: 2px;
  left: 4px;
  width: 10px;
  height: 12px;
  border-radius: 0;
  clip-path: polygon(0 0, 100% 50%, 0 100%);
}

.button-icon--stop::before {
  inset: 3px;
  border-radius: 3px;
}

.button-icon--pause::before,
.button-icon--pause::after {
  top: 2px;
  width: 4px;
  height: 12px;
}

.button-icon--pause::before {
  left: 3px;
}

.button-icon--pause::after {
  right: 3px;
}

.button-icon--check::before {
  top: 7px;
  left: 2px;
  width: 5px;
  height: 2px;
  transform: rotate(45deg);
}

.button-icon--check::after {
  top: 6px;
  left: 5px;
  width: 9px;
  height: 2px;
  transform: rotate(-45deg);
}

.button-icon--refresh::before {
  inset: 1px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  background: transparent;
  border-radius: 999px;
}

.button-icon--refresh::after {
  top: 1px;
  right: 1px;
  width: 6px;
  height: 6px;
  border-radius: 0;
  clip-path: polygon(0 0, 100% 0, 100% 100%);
}

.button-icon--people::before {
  top: 1px;
  left: 2px;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  box-shadow: 7px 0 0 0 currentColor;
}

.button-icon--people::after {
  top: 8px;
  left: 1px;
  width: 14px;
  height: 6px;
}

.button-icon--plus::before,
.button-icon--plus::after {
  top: 7px;
  left: 2px;
  width: 12px;
  height: 2px;
}

.button-icon--plus::after {
  top: 2px;
  left: 7px;
  width: 2px;
  height: 12px;
}

.button-icon--view::before {
  top: 4px;
  left: 1px;
  width: 14px;
  height: 8px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--view::after {
  top: 6px;
  left: 6px;
  width: 4px;
  height: 4px;
}

.button-icon--copy::before,
.button-icon--copy::after {
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--copy::before {
  top: 3px;
  left: 5px;
  width: 8px;
  height: 9px;
}

.button-icon--copy::after {
  top: 1px;
  left: 2px;
  width: 8px;
  height: 9px;
}

.button-icon--delete::before {
  top: 4px;
  left: 3px;
  width: 10px;
  height: 9px;
  border: 2px solid currentColor;
  border-top: 0;
  background: transparent;
  border-radius: 0 0 3px 3px;
}

.button-icon--delete::after {
  top: 2px;
  left: 2px;
  width: 12px;
  height: 2px;
  box-shadow: 4px -2px 0 0 currentColor;
}

.button-icon--save::before {
  top: 1px;
  left: 2px;
  width: 12px;
  height: 14px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--save::after {
  top: 3px;
  left: 5px;
  width: 6px;
  height: 3px;
  box-shadow: 0 6px 0 0 currentColor;
}

.button-icon--key::before {
  top: 2px;
  left: 2px;
  width: 7px;
  height: 7px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--key::after {
  top: 8px;
  left: 8px;
  width: 7px;
  height: 2px;
  box-shadow: 4px 0 0 0 currentColor, 4px 3px 0 0 currentColor;
}

.button-icon--logout::before {
  top: 2px;
  left: 2px;
  width: 8px;
  height: 12px;
  border: 2px solid currentColor;
  border-right: 0;
  background: transparent;
  border-radius: 3px 0 0 3px;
}

.button-icon--logout::after {
  top: 7px;
  right: 1px;
  width: 9px;
  height: 2px;
  box-shadow: -1px -3px 0 -1px currentColor, -1px 3px 0 -1px currentColor;
}

.button-icon--reset-password::before {
  inset: 1px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  background: transparent;
  border-radius: 999px;
}

.button-icon--reset-password::after {
  top: 1px;
  right: 1px;
  width: 6px;
  height: 6px;
  border-radius: 0;
  clip-path: polygon(0 0, 100% 0, 100% 100%);
}

.button-icon--close::before,
.button-icon--close::after {
  top: 7px;
  left: 1px;
  width: 14px;
  height: 2px;
}

.button-icon--close::before {
  transform: rotate(45deg);
}

.button-icon--close::after {
  transform: rotate(-45deg);
}

.button-icon--edit::before {
  top: 2px;
  left: 3px;
  width: 10px;
  height: 3px;
  border-radius: 2px;
  transform: rotate(-45deg);
}

.button-icon--edit::after {
  top: 10px;
  left: 2px;
  width: 4px;
  height: 4px;
  border-radius: 0;
  clip-path: polygon(0 100%, 100% 100%, 100% 0);
}

.button-icon--package::before {
  top: 3px;
  left: 2px;
  width: 12px;
  height: 10px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--package::after {
  top: 3px;
  left: 7px;
  width: 2px;
  height: 10px;
}

.button-icon--orders::before {
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--orders::after {
  top: 5px;
  left: 5px;
  width: 6px;
  height: 2px;
  box-shadow: 0 4px 0 0 currentColor;
}

.button-icon--in-work::before {
  top: 1px;
  left: 3px;
  width: 10px;
  height: 10px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--in-work::after {
  top: 7px;
  left: 8px;
  width: 5px;
  height: 2px;
  transform-origin: left center;
  transform: rotate(-45deg);
}

.button-icon--timer-preparation::before {
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--timer-preparation::after {
  top: 7px;
  left: 8px;
  width: 4px;
  height: 2px;
  transform-origin: left center;
  transform: rotate(-45deg);
}

.button-icon--timer-break::before,
.button-icon--timer-break::after,
.button-icon--timer-idle::before,
.button-icon--timer-idle::after,
.button-icon--timer-operation::before,
.button-icon--timer-operation::after {
  background: currentColor;
}

.button-icon--timer-break::before,
.button-icon--timer-break::after {
  top: 2px;
  width: 4px;
  height: 12px;
}

.button-icon--timer-break::before {
  left: 3px;
}

.button-icon--timer-break::after {
  right: 3px;
}

.button-icon--timer-idle::before {
  top: 1px;
  left: 7px;
  width: 2px;
  height: 9px;
}

.button-icon--timer-idle::after {
  bottom: 1px;
  left: 7px;
  width: 2px;
  height: 2px;
}

.button-icon--timer-operation::before {
  top: 3px;
  left: 2px;
  width: 12px;
  height: 10px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--timer-operation::after {
  top: 6px;
  left: 5px;
  width: 6px;
  height: 2px;
}

.operations-section {
  display: grid;
  gap: 14px;
  min-height: 0;
  overflow: auto;
  padding-right: 6px;
}

.empty-state--operations {
  padding: 18px;
  border: 1px dashed var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
}

.empty-state--operations p {
  margin: 0;
}

.empty-state--operations p + p {
  margin-top: 8px;
  color: var(--color-text-secondary);
}

.operation-cell {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding-left: calc(var(--level) * 18px);
}

.operation-branch {
  width: 12px;
  height: 1px;
  margin-top: 22px;
  background: var(--color-muted);
  flex: 0 0 auto;
}

.operation-editor {
  width: 100%;
  display: grid;
  gap: 8px;
}

.operation-badge {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 0.84rem;
  font-weight: 700;
}

.operation-badge--group {
  background: var(--color-surface-alt);
  color: var(--color-text-secondary);
}

.operation-badge--leaf {
  background: var(--color-surface-soft);
  color: var(--color-primary-hover);
}

.operation-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.readonly-note {
  color: var(--color-text-muted);
}

.operations-footer {
  display: flex;
  justify-content: flex-start;
  padding-top: 6px;
}

.icon-action-button {
  position: relative;
  width: 40px;
  height: 40px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.icon-action-button:disabled {
  cursor: not-allowed;
  opacity: 0.38;
  transform: none;
  box-shadow: none;
}

.icon-action-button:hover {
  transform: translateY(-1px);
  background: var(--color-surface-alt);
  box-shadow: 0 10px 18px rgba(31, 42, 51, 0.08);
}

.icon-action-button:focus-visible {
  outline: 2px solid rgba(47, 110, 163, 0.28);
  outline-offset: 2px;
}

.action-icon {
  position: absolute;
  inset: 0;
}

.action-icon::before,
.action-icon::after {
  content: "";
  position: absolute;
  background: var(--color-text-secondary);
  border-radius: 999px;
}

.action-icon--up::before {
  top: 10px;
  left: 19px;
  width: 2px;
  height: 16px;
}

.action-icon--up::after {
  top: 8px;
  left: 14px;
  width: 12px;
  height: 8px;
  background: var(--color-text-secondary);
  clip-path: polygon(50% 0, 0 100%, 100% 100%);
}

.action-icon--down::before {
  top: 12px;
  left: 19px;
  width: 2px;
  height: 16px;
}

.action-icon--down::after {
  top: 24px;
  left: 14px;
  width: 12px;
  height: 8px;
  background: var(--color-text-secondary);
  clip-path: polygon(0 0, 100% 0, 50% 100%);
}

.action-icon--indent::before {
  top: 11px;
  left: 11px;
  width: 2px;
  height: 14px;
  box-shadow: 8px 0 0 0 rgba(138, 150, 163, 0.28);
}

.action-icon--indent::after {
  top: 23px;
  left: 11px;
  width: 15px;
  height: 2px;
  box-shadow:
    8px -5px 0 -4px var(--color-text-secondary),
    8px 5px 0 -4px var(--color-text-secondary);
}

.action-icon--outdent::before {
  top: 11px;
  left: 27px;
  width: 2px;
  height: 14px;
  box-shadow: -8px 0 0 0 rgba(138, 150, 163, 0.28);
}

.action-icon--outdent::after {
  top: 23px;
  left: 14px;
  width: 15px;
  height: 2px;
  box-shadow:
    -8px -5px 0 -4px var(--color-text-secondary),
    -8px 5px 0 -4px var(--color-text-secondary);
}

.action-icon--child::before {
  top: 9px;
  left: 11px;
  width: 2px;
  height: 12px;
}

.action-icon--child::after {
  top: 19px;
  left: 11px;
  width: 11px;
  height: 2px;
  box-shadow:
    11px 0 0 0 var(--color-text-secondary),
    16px -5px 0 -4px var(--color-text-secondary),
    16px 5px 0 -4px var(--color-text-secondary);
}

.action-icon--sibling::before {
  top: 19px;
  left: 10px;
  width: 14px;
  height: 2px;
}

.action-icon--sibling::after {
  top: 13px;
  left: 16px;
  width: 2px;
  height: 14px;
  box-shadow: 10px 0 0 0 rgba(138, 150, 163, 0.24);
}

.modal__actions {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
  padding-top: 14px;
  border-top: 1px solid var(--color-border);
}

.field-error--actions {
  margin-right: auto;
  flex: 1 1 auto;
  display: flex;
  justify-content: center;
  text-align: center;
}

@media (max-width: 980px) {
  .toolbar,
  .form-grid,
  .order-form__header,
  .assignment-row,
  .worker-summary,
  .worker-timer-bar,
  .statistics-kpis,
  .statistics-grid {
    grid-template-columns: 1fr;
  }

  .statistics-card--wide {
    grid-column: span 1;
  }
}

@media (max-width: 1999px) {
  .header {
    justify-content: flex-start;
  }

  .brand-block {
    order: -1;
    flex: 0 0 100%;
    align-self: flex-start;
  }

  .tabs {
    order: 0;
  }

  .current-user-card {
    order: 1;
  }
}

@media (max-width: 760px) {
  .page {
    padding: 12px;
  }

  .shell {
    min-height: auto;
    padding: 18px;
    border-radius: 22px;
  }

  .header,
  .panel-head,
  .modal__head,
  .modal__actions,
  .banner,
  .statistics-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .tabs {
    width: 100%;
    flex-wrap: wrap;
  }

  .tab-button,
  .primary-button {
    width: 100%;
  }

  .modal-backdrop {
    padding: 12px;
  }

  .modal {
    width: calc(100vw - 24px);
    max-height: calc(100vh - 24px);
    padding: 18px;
  }

  .confirm-modal {
    width: calc(100vw - 24px);
    padding: 18px;
  }

  .confirm-modal__actions {
    flex-direction: column-reverse;
    align-items: stretch;
  }

  .products-table th,
  .products-table td,
  .users-table th,
  .users-table td,
  .operation-table th,
  .operation-table td {
    min-width: 150px;
  }
}
</style>
