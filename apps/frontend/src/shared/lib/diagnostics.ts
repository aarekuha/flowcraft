export type DiagnosticEvent = {
  at: number;
  kind: "request" | "timer_click" | "timer_state" | "js_error" | "unhandled_rejection" | "console_error" | "online" | "offline" | "page_open";
  path?: string;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  status?: number;
  duration_ms?: number;
  request_id?: string;
  order_id?: number;
  operation_id?: number;
  timer_type?: "preparation" | "operation" | "break" | "idle";
  timer_started_at?: number;
  blocked?: boolean;
  line?: number;
  column?: number;
};

type Report = {
  owner_user_id: number;
  report_key: string;
  captured_at: number;
  window_start: number;
  build: string;
  viewport_width: number;
  viewport_height: number;
  events: DiagnosticEvent[];
};
type StoredEvent = DiagnosticEvent & { userId: number; id?: number };
const DAY = 86400000;
let userId: number | null = null;
let database: Promise<IDBDatabase> | null = null;
let queue: Promise<void> = Promise.resolve();
let storageFailed = false;
let initialized = false;

function openDatabase(): Promise<IDBDatabase> {
  if (!database) {
    database = new Promise((resolve, reject) => {
      const request = indexedDB.open("flowcraft-diagnostics", 1);
      request.onupgradeneeded = () => {
        const events = request.result.createObjectStore("events", { keyPath: "id", autoIncrement: true });
        events.createIndex("at", "at");
        events.createIndex("userAt", ["userId", "at"]);
        request.result.createObjectStore("pending", { keyPath: "owner_user_id" });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error("Хранилище диагностики занято другой вкладкой."));
    });
  }
  return database;
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

function readResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export function diagnosticUser(): number | null { return userId; }

export function setDiagnosticUser(value: number | null): void {
  userId = value;
  if (value !== null) recordDiagnostic({ kind: "page_open" });
  if (initialized) return;
  initialized = true;
  window.addEventListener("error", (event) => recordDiagnostic({ kind: "js_error", line: event.lineno || 0, column: event.colno || 0 }));
  window.addEventListener("unhandledrejection", () => recordDiagnostic({ kind: "unhandled_rejection" }));
  window.addEventListener("online", () => recordDiagnostic({ kind: "online" }));
  window.addEventListener("offline", () => recordDiagnostic({ kind: "offline" }));
  const original = console.error;
  console.error = (...args: unknown[]) => {
    recordDiagnostic({ kind: "console_error" });
    original.apply(console, args);
  };
}

export function recordDiagnostic(event: Omit<DiagnosticEvent, "at">, owner = userId): void {
  if (owner === null) return;
  const entry = { ...event, at: Date.now(), userId: owner };
  queue = queue.then(async () => {
    const db = await openDatabase();
    const transaction = db.transaction("events", "readwrite");
    const done = transactionDone(transaction);
    const store = transaction.objectStore("events");
    store.add(entry);
    const cursor = store.index("at").openCursor(IDBKeyRange.upperBound(Date.now() - DAY, true));
    cursor.onsuccess = () => {
      if (cursor.result) { cursor.result.delete(); cursor.result.continue(); }
    };
    await done;
  }).catch(() => { storageFailed = true; });
}

export function diagnosticRequestPath(path: string): string | null {
  const value = path.split("?")[0];
  if (value.startsWith("/api/auth") || value.startsWith("/api/diagnostics")) return null;
  return /^\/api\/[a-zA-Z0-9/_-]+$/.test(value) && value.length <= 200 ? value : null;
}

export async function prepareDiagnosticReport(owner: number): Promise<Report> {
  await queue;
  if (storageFailed) throw new Error("Хранилище диагностики недоступно. История могла сохраниться не полностью.");
  const db = await openDatabase();
  const previous = await readResult<Report | undefined>(db.transaction("pending").objectStore("pending").get(owner));
  if (previous) return previous;
  const captured = Date.now();
  const rows = await readResult<StoredEvent[]>(db.transaction("events").objectStore("events").index("userAt").getAll(IDBKeyRange.bound([owner, captured - DAY], [owner, captured])));
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  const report: Report = {
    owner_user_id: owner,
    report_key: `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`,
    captured_at: captured,
    window_start: captured - DAY,
    build: __APP_BUILD__,
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    events: rows.map(({ userId: _owner, id: _id, ...event }) => event),
  };
  const transaction = db.transaction("pending", "readwrite");
  const done = transactionDone(transaction);
  const store = transaction.objectStore("pending");
  let result = report;
  const request = store.get(owner);
  request.onsuccess = () => {
    if (request.result) result = request.result;
    else store.put(report);
  };
  await done;
  return result;
}

export async function acknowledgeDiagnosticReport(owner: number, reportKey: string): Promise<void> {
  const db = await openDatabase();
  const transaction = db.transaction("pending", "readwrite");
  const done = transactionDone(transaction);
  const store = transaction.objectStore("pending");
  const request = store.get(owner);
  request.onsuccess = () => {
    if (request.result?.report_key === reportKey) store.delete(owner);
  };
  await done;
}

declare const __APP_BUILD__: string;
