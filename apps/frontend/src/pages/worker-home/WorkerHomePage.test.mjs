import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import * as vue from 'vue';
import { createWorkerTimerRequests } from '../../shared/lib/workerTimerRequests.ts';

const sourceText = fs.readFileSync(new URL('./WorkerHomePage.vue', import.meta.url), 'utf8')
  .split('<script setup lang="ts">')[1].split('</script>')[0];
const source = ts.createSourceFile('worker.ts', sourceText, ts.ScriptTarget.Latest, true);
const names = new Set([
  'loadWorkerWorkspace', 'loadWorkerAssignments', 'loadWorkerTimerState',
  'activateWorkerTimer', 'applyWorkerTimerApiState', 'syncWorkerTimers',
  'resetWorkerTimerState', 'getTimerIdForApiTarget',
  'parseOrderIdFromTimerId', 'parseOperationIdFromTimerId',
]);
const functions = source.statements
  .filter(node => ts.isFunctionDeclaration(node) && names.has(node.name?.text))
  .map(node => node.getText(source)).join('\n');

function createWorkspace() {
  const setup = `
    const {ref,computed,watch,nextTick} = vue;
    const PREPARATION_TIMER_ID='preparation', BREAK_TIMER_ID='break', IDLE_TIMER_ID='idle';
    const operationId='worker:operation:492:518';
    const base=[{id:'preparation',kind:'preparation'},{id:'break',kind:'break'},{id:'idle',kind:'idle'}];
    const operation={id:operationId,kind:'operation',assignmentStatus:'in_work'};
    const workOrderDetails=ref([operation]),workerAssignmentsError=ref(''),workerAssignmentsLoading=ref(false);
    const workerQrRouteTarget=ref(null),workerAssignmentStatusFilter=ref('in_work');
    let workerAssignmentsRequestId=0;
    const workerTimers=ref({}),activeWorkerTimerId=ref(null),workerDayStartedAt=ref(1),workerTimerSubmitting=ref(false),workerTimerNow=ref(0),isSmartphoneViewport=ref(false);
    const workerTimerRequests=createWorkerTimerRequests(busy=>workerTimerSubmitting.value=busy);
    const workerTimerDefinitions=computed(()=>[...base,...workOrderDetails.value]);
    const canLoadWorkerWorkspace=()=>true,focusWorkerOrderFromRoute=async()=>{},isUnauthorizedError=()=>false;
    const getErrorMessage=e=>e.message;
    const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
    const breakState={shift:{startedAtTs:1},activeTimer:{timerType:'break',startedAtTs:1},timerTotals:[]};
    const operationState={shift:{startedAtTs:1},activeTimer:{timerType:'operation',orderId:492,operationId:518,startedAtTs:12345},timerTotals:[]};
    const controls={failAssignments:false,reads:[],switches:[]};
    const fetchWorkerAssignedWorkOrders=async()=>{if(controls.failAssignments)throw new Error('Network failure');return [operation];};
    const fetchWorkerTimerState=()=>{const request=deferred();controls.reads.push(request);return request.promise;};
    const switchWorkerTimer=()=>{const request=deferred();controls.switches.push(request);return request.promise;};
  `;
  const expose = `
    const stop=watch(workerTimerDefinitions,defs=>syncWorkerTimers(defs),{immediate:true});
    applyWorkerTimerApiState(breakState);
    ({loadWorkerWorkspace,activateWorkerTimer,resetWorkerTimerState,controls,
      workerTimerSubmitting,workerAssignmentsError,activeWorkerTimerId,workerTimers,
      operationId,breakState,operationState,stop});
  `;
  const code = ts.transpileModule(setup + functions + expose, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  return vm.runInNewContext(code, { vue, createWorkerTimerRequests, Date });
}
const flush = async () => { await vue.nextTick(); await Promise.resolve(); };

test('keeps busy until all reads finish and ignores older state', async function testOverlappingReads() {
  `
  Проверяем поздний ответ при двух загрузках:
  - сначала получить новое состояние операции, затем старое состояние перерыва
  - не снимать блокировку до завершения обоих запросов
  - сохранить активную операцию после прихода старого ответа
  `;
  const w = createWorkspace();
  try {
    const first = w.loadWorkerWorkspace(); await flush();
    const second = w.loadWorkerWorkspace(); await flush();
    w.controls.reads[1].resolve(w.operationState); await second;
    assert.equal(w.workerTimerSubmitting.value, true);
    assert.equal(w.activeWorkerTimerId.value, w.operationId);
    await w.activateWorkerTimer('preparation');
    assert.equal(w.controls.switches.length, 0);
    w.controls.reads[0].resolve(w.breakState); await first;
    assert.equal(w.activeWorkerTimerId.value, w.operationId);
    assert.equal(w.workerTimerSubmitting.value, false);
  } finally { w.stop(); }
});

test('does not overwrite confirmed switch with read started during switch', async function testReadDuringSwitch() {
  `
  Проверяем загрузку во время переключения с перерыва:
  - задержать ответ загрузки со старым перерывом
  - подтвердить переключение на операцию до прихода загрузки
  - сохранить операцию и исходное время запуска после старого ответа
  `;
  const w = createWorkspace();
  try {
    const switching = w.activateWorkerTimer(w.operationId);
    const loading = w.loadWorkerWorkspace(); await flush();
    w.controls.switches[0].resolve(w.operationState); await switching;
    assert.equal(w.activeWorkerTimerId.value, w.operationId);
    assert.equal(w.workerTimerSubmitting.value, true);
    w.controls.reads[0].resolve(w.breakState); await loading;
    assert.equal(w.activeWorkerTimerId.value, w.operationId);
    assert.equal(w.workerTimers.value[w.operationId].startedAtMs, 12345);
    assert.equal(w.workerTimerSubmitting.value, false);
  } finally { w.stop(); }
});

test('retains operation after assignment refresh fails and allows retry', async function testAssignmentsFailure() {
  `
  Проверяем ошибку обновления назначений после успешного запуска:
  - подтвердить операцию и завершить запрос назначений сетевой ошибкой
  - сохранить видимую операцию, активность и время запуска, показать ошибку
  - успешно повторить обновление без сброса таймера
  `;
  const w = createWorkspace();
  try {
    w.controls.failAssignments = true;
    const switching = w.activateWorkerTimer(w.operationId);
    w.controls.switches[0].resolve(w.operationState); await switching; await flush();
    assert.equal(w.activeWorkerTimerId.value, w.operationId);
    assert.equal(w.workerTimers.value[w.operationId].startedAtMs, 12345);
    assert.equal(w.workerAssignmentsError.value, 'Network failure');
    assert.equal(w.workerTimerSubmitting.value, false);
    w.controls.failAssignments = false;
    const loading = w.loadWorkerWorkspace(); await flush();
    w.controls.reads[0].resolve(w.operationState); await loading;
    assert.equal(w.activeWorkerTimerId.value, w.operationId);
    assert.equal(w.workerAssignmentsError.value, '');
  } finally { w.stop(); }
});

test('discarded session response cannot unlock or overwrite new session', async function testResetWithPendingRead() {
  `
  Проверяем сброс страницы при незавершённой загрузке:
  - начать новую загрузку после сброса состояния
  - проигнорировать старый ответ и сохранить блокировку нового запроса
  - применить только состояние новой загрузки
  `;
  const w = createWorkspace();
  try {
    const old = w.loadWorkerWorkspace(); await flush();
    w.resetWorkerTimerState();
    const current = w.loadWorkerWorkspace(); await flush();
    w.controls.reads[0].resolve(w.operationState); await old;
    assert.equal(w.activeWorkerTimerId.value, null);
    assert.equal(w.workerTimerSubmitting.value, true);
    w.controls.reads[1].resolve(w.breakState); await current;
    assert.equal(w.activeWorkerTimerId.value, 'break');
    assert.equal(w.workerTimerSubmitting.value, false);
  } finally { w.stop(); }
});
