import assert from "node:assert/strict";
import test from "node:test";
import "fake-indexeddb/auto";
import { diagnosticRequestPath, setDiagnosticUser, recordDiagnostic, prepareDiagnosticReport, acknowledgeDiagnosticReport } from "./diagnostics.ts";

globalThis.window = Object.assign(new EventTarget(), { innerWidth: 800, innerHeight: 600 });
globalThis.__APP_BUILD__ = "test";

test("history covers 24 hours, separates users and survives retries", async () => {
  `Проверяем сохранение диагностической истории:
  - включить только события текущего пользователя за сутки
  - повторить отправку неизменённого отчёта до подтверждения сервера
  - сохранить новые события для следующего отчёта`;
  const realNow = Date.now;
  const now = realNow();
  try {
    Date.now = () => now - 86400001;
    setDiagnosticUser(1);
    recordDiagnostic({ kind: "timer_click", operation_id: 111 });
    Date.now = () => now - 23 * 3600000;
    recordDiagnostic({ kind: "timer_click", operation_id: 222 });
    setDiagnosticUser(2);
    recordDiagnostic({ kind: "timer_click", operation_id: 333 });
    Date.now = () => now;
    setDiagnosticUser(1);
    const [first, parallel] = await Promise.all([prepareDiagnosticReport(1), prepareDiagnosticReport(1)]);
    assert.equal(first.report_key, parallel.report_key);
    assert.equal(first.captured_at - first.window_start, 86400000);
    assert.deepEqual(first.events.filter(e => e.kind === "timer_click").map(e => e.operation_id), [222]);
    recordDiagnostic({ kind: "timer_click", operation_id: 444 });
    assert.deepEqual(await prepareDiagnosticReport(1), first);
    await acknowledgeDiagnosticReport(1, "wrong-key");
    assert.deepEqual(await prepareDiagnosticReport(1), first);
    setDiagnosticUser(null);
    setDiagnosticUser(1);
    const reloaded = await import("./diagnostics.ts?reload");
    assert.deepEqual(await reloaded.prepareDiagnosticReport(1), first);
    await acknowledgeDiagnosticReport(1, first.report_key);
    const next = await prepareDiagnosticReport(1);
    assert.notEqual(next.report_key, first.report_key);
    assert.deepEqual(next.events.filter(e => e.kind === "timer_click").map(e => e.operation_id), [222, 444]);
    const other = await prepareDiagnosticReport(2);
    assert.deepEqual(other.events.filter(e => e.kind === "timer_click").map(e => e.operation_id), [333]);
  } finally {
    Date.now = realNow;
    setDiagnosticUser(null);
  }
});

test("request metadata excludes authentication and query parameters", () => {
  `Проверяем фильтрацию адресов запросов:
  - исключить авторизацию и отправку диагностики
  - удалить параметры и отклонить внешние адреса`;
  assert.equal(diagnosticRequestPath("/api/auth/login"), null);
  assert.equal(diagnosticRequestPath("/api/diagnostics/reports"), null);
  assert.equal(diagnosticRequestPath("/api/timers/state?token=secret"), "/api/timers/state");
  assert.equal(diagnosticRequestPath("https://example.com/api/orders"), null);
});
