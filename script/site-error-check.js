#!/usr/bin/env node
// 站点「全局异常处理」的可核对取值：把 index.html 里真实注册的全局错误处理器切出来，
// 在 node 里用最小 DOM/window 桩执行，逐例看未捕获错误会不会落到错误面板上。
//
// 治的失效：站点此前没有任何全局兜底——Asciidoctor CDN 加载失败、渲染脚本里一个
// 同步异常、一次未处理的 Promise rejection，都让页面卡在"正在加载…"或白屏、零提示。
// 这类代码"看着在"没有意义，判据是"喂一个错误进去，面板显示的到底是什么"。
// 与 site-link-check.js / site-include-check.js 同一形态：实现只留一份（从 index.html
// 切出真实代码执行），判据由 check_specs.py 真的跑它、逐项比对。
//
// 用法：node site-error-check.js --boundary
//   输出一行一例 JSON（用例名 + 面板显示文本），由调用方逐条比对。
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd().replace(/\\?$/, '/');

// 从 index.html 切出"全局异常处理"那一段真实脚本，不另写一套实现。
function sliceImpl(html) {
  const marker = '// 全局异常处理：';
  const start = html.indexOf(marker);
  if (start < 0) throw new Error('index.html 里找不到全局异常处理脚本（' + marker + '）');
  const end = html.indexOf('</script>', start);
  if (end < 0) throw new Error('index.html 里找不到全局异常处理脚本的结束标记');
  return html.slice(start, end);
}

// 最小 DOM/window 桩：只需 getElementById、addEventListener、hidden/textContent、reload。
function makeEnv() {
  let envReady = function () {};   // 由下方赋值：把 DOM 节点"放到页面里"
  const listeners = {};
  const panel = { hidden: true, addEventListener: function () {} };
  const detail = { textContent: '' };
  const retry = { _click: function () {}, addEventListener: function (type, fn) { this._click = fn; } };
  const errors = [];
  const window = {
    addEventListener: function (type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    location: { reload: function () { window._reloaded = true; } },
  };
  // 真实页面里这段脚本在 <head>，面板节点在 <body>：注册监听时还取不到节点，
  // 只有事件触发（或 DOMContentLoaded）时才在 DOM 里。桩必须复现这一时序，
  // 否则"注册时取节点、取不到就 return"的旧实现在桩里全绿、真机上全废。
  let domReady = false;
  const domListeners = {};
  const document = {
    readyState: 'loading',
    getElementById: function (id) {
      if (!domReady) return null;
      return { 'fatal-panel': panel, 'fatal-detail': detail, 'fatal-retry': retry }[id] || null;
    },
    addEventListener: function (type, fn) { (domListeners[type] = domListeners[type] || []).push(fn); },
  };
  envReady = function () {
    domReady = true;
    document.readyState = 'interactive';
    (domListeners['DOMContentLoaded'] || []).forEach(function (fn) { fn(); });
  };
  const console = { error: function () { errors.push(Array.prototype.slice.call(arguments)); } };
  return { listeners: listeners, panel: panel, detail: detail, retry: retry,
           window: window, document: document, console: console, errors: errors, domReady: envReady };
}

function run(env, src) {
  // eslint-disable-next-line no-new-func
  const fn = new Function('window', 'document', 'console', src);
  fn(env.window, env.document, env.console);
}

function fire(env, type, event) {
  (env.listeners[type] || []).forEach(function (fn) { fn(event); });
  return env.detail.textContent;
}

// ---- 边界取值：每种失效形态喂一个真实事件，看面板显示什么 --------------------------
const CASES = [
  // 同步异常（最常见的"白屏"）：应显示脚本运行出错 + 原始消息，面板可见
  ['sync-error', function () {
    const env = makeEnv();
    run(env, sliceImpl(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')));
    env.domReady();
    const text = fire(env, 'error', { type: 'error', target: env.window, error: new Error('boom') });
    return { text: text, visible: !env.panel.hidden };
  }],
  // 资源加载失败（Asciidoctor CDN 挂掉）：error 事件的 target 是 <script> 节点，
  // 不是 window——不按 target 区分会被当成普通错误、丢掉"哪个资源"这一关键线索
  ['resource-error', function () {
    const env = makeEnv();
    run(env, sliceImpl(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')));
    env.domReady();
    const text = fire(env, 'error', { type: 'error', target: { src: 'https://cdn/x.js' } });
    return { text: text, visible: !env.panel.hidden };
  }],
  // 未处理的 Promise rejection：走 unhandledrejection，reason 是拒绝原因
  ['promise-rejection', function () {
    const env = makeEnv();
    run(env, sliceImpl(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')));
    env.domReady();
    const text = fire(env, 'unhandledrejection', { type: 'unhandledrejection', reason: 'rejected!' });
    return { text: text, visible: !env.panel.hidden };
  }],
  // head 里的 CDN 加载失败：错误发生在 body 面板节点进入 DOM 之前。
  // 首因须暂存，DOM 就绪后补显示——否则本 PR 要治的那个白屏场景恰恰会漏掉。
  ['error-before-dom-ready', function () {
    const env = makeEnv();
    run(env, sliceImpl(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')));
    // 不调用 env.domReady()：面板节点还没解析进 DOM
    fire(env, 'error', { type: 'error', target: { src: 'https://cdn/x.js' } });
    const visibleBefore = !env.panel.hidden;
    env.domReady();
    return { text: env.detail.textContent, visible: !env.panel.hidden, visibleBefore: visibleBefore };
  }],
  // 首因不被覆盖：多个错误接连到来时，面板保留第一个（后来的会被 claimed 挡住）
  ['first-error-kept', function () {
    const env = makeEnv();
    run(env, sliceImpl(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')));
    env.domReady();
    fire(env, 'error', { type: 'error', target: env.window, error: new Error('first') });
    const text = fire(env, 'error', { type: 'error', target: env.window, error: new Error('second') });
    return text;
  }],
  // 面板自身写入失败（detail.textContent 抛错）：只记日志、不递归调全局处理器
  ['no-recursion', function () {
    const env = makeEnv();
    run(env, sliceImpl(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')));
    env.domReady();
    Object.defineProperty(env.detail, 'textContent', {
      set: function () { throw new Error('detail broken'); },
      get: function () { return ''; },
    });
    fire(env, 'error', { type: 'error', target: env.window, error: new Error('boom') });
    return { logged: env.errors.length > 0, visible: !env.panel.hidden };
  }],
  // 重试按钮：点击后真的重新加载（不是把面板藏掉假装恢复）
  ['retry-reloads', function () {
    const env = makeEnv();
    run(env, sliceImpl(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')));
    env.domReady();
    env.retry._click();
    return !!env.window._reloaded;
  }],
];

if (require.main === module) {
  const arg = process.argv[2];
  if (arg !== '--boundary') {
    process.stderr.write('用法: node site-error-check.js --boundary\n');
    process.exit(1);
  }
  (async function () {
    for (const [name, fn] of CASES) {
      process.stdout.write(JSON.stringify({ case: name, out: fn() }) + '\n');
    }
  })().catch(function (e) {
    process.stderr.write(String(e && e.stack || e) + '\n');
    process.exit(1);
  });
}

module.exports = { CASES: CASES, sliceImpl: sliceImpl, makeEnv: makeEnv, run: run, fire: fire };
