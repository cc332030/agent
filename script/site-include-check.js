#!/usr/bin/env node
// 站点「include 预装配」的可核对取值：把仓库里真实的 `.adoc` 喂进 `index.html` 的展开逻辑，
// 输出**装配后的文本**（交给 Asciidoctor 的那一份），由 `check_specs.py` 的
// `check_site_include_guard` 逐条比对。
//
// **本文件不渲染**：`asciidoctor.convert()` 那一跳只有浏览器里有（CDN 引入的 UMD），这里
// 输出的是它的**入参**。「正文区渲染成什么样」由 `check_specs.py` 只在需要时另调处理器核。
//
// 为什么要有这一份（失效形态，本仓库实证）：`index.html` 写过近一百行的 include 展开逻辑，
// 其中 `expandIncludes()` 一次都没被调用过——`renderDoc()` 只调了"取回片段"的
// `loadWithIncludes()`，接着把**未展开**的原文交给了 Asciidoctor。于是页面正文区是
// `Unresolved directive in <stdin> - include::_common.txt[tag=primary]`（十六处），
// 而 `PROMPTS.adoc` 承诺"正文区可直接原样复制"。当时 CI 全绿、`check_specs` 也全绿：
// 这段逻辑没有任何机械抓手，唯一的核对手段是打开浏览器肉眼看一眼。
//
// 故与 `site-link-check.js` 同一形态：**实现只留一份**（本文件从 `index.html` 里按函数名
// 把真实代码切出来执行，不另写一套），判据由 `check_specs.py` 真的跑它、逐项比对取值。
//
// 用法：
//   * `node site-include-check.js <仓库根相对路径>`：输出该文档**装配后的文本**（stdout），
//     由 `check_specs.py` 逐份比对（片段到位、`{主侧重}` 已填、可复制块是一整段）；
//   * `node site-include-check.js --boundary`：输出**边界取值**（一行一例 JSON），供
//     "切片与属性支持""取回与失败的口径"这类最容易看着像做了、其实没做的分支逐例核对。
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd().replace(/\\?$/, '/');   // 带尾斜杠：拼 `ROOT + 相对路径` 时不多不少一层

// ---- 从 index.html 切出真实实现 --------------------------------------------------
// 按 `function` 名与 `var` 名切，不抄第二份：切不到就当场报错——"判据找不到被测代码"
// 必须显形，否则本文件会退化成一份看着像在核、其实在核自己抄写的东西。
function sliceImpl(html) {
  const grab = (start, endMarker) => {
    const i = html.indexOf(start);
    if (i < 0) throw new Error('index.html 里找不到 ' + JSON.stringify(start));
    const j = html.indexOf(endMarker, i);
    if (j < 0) throw new Error('index.html 里找不到 ' + JSON.stringify(endMarker));
    return html.slice(i, j);
  };
  const parts = [
    grab('var INCLUDE_RE =', 'var TAG_START_RE ='),
    grab('var TAG_START_RE =', 'function sliceTag'),
    grab('function sliceTag', 'function includeAttrs'),
    grab('function includeAttrs', 'function expandIncludes'),
    grab('function expandIncludes', 'function fillPrimary'),
    grab('function fillPrimary', 'function loadWithIncludes'),
    grab('function loadWithIncludes', 'function toUrl'),
    grab('function normalize', '// 把文档里的链接目标解析成仓库根相对路径'),
  ];
  return parts.join('\n');
}

function loadImpl() {
  const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
  const src = sliceImpl(html) + '\nreturn {' +
    'sliceTag: sliceTag, expandIncludes: expandIncludes, fillPrimary: fillPrimary,' +
    'loadWithIncludes: loadWithIncludes, includeCache: includeCache, INCLUDE_RE: INCLUDE_RE};\n';
  const toUrlStub = 'function toUrl(p) { return "./" + encodeURI(p); }\n';
  // 站点的 `fetch` 在 node 里换成读盘：取的是同一份仓库字节（站点对该路径直出原文）
  // `__VIRTUAL__` 是边界用例用的**内存文件**（层在真实仓库之上）：那些用例要的是
  // 「两轮之间片段换了内容」这类输入，落成仓库文件既脏工作区、又改不动第二轮的内容。
  const fetchStub =
    'global.fetch = function (url) {\n' +
    '  var p = decodeURI(String(url).replace(/^\\.\\//, ""));\n' +
    '  var v = global.__VIRTUAL__ || {};\n' +
    '  if (Object.prototype.hasOwnProperty.call(v, p)) {\n' +
    '    return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(v[p]); } });\n' +
    '  }\n' +
    '  var abs = ' + JSON.stringify(ROOT) + ' + p;\n' +
    '  if (!fs.existsSync(abs)) return Promise.resolve({ ok: false, status: 404, text: function () { return Promise.resolve(""); } });\n' +
    '  return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(fs.readFileSync(abs, "utf8")); } });\n' +
    '};\n';
  const fn = new Function('fs', 'path', toUrlStub + fetchStub + 'var includeCache = {};\n' + src);
  return fn(fs, path);
}

const impl = loadImpl();

// 取回次数：主文档须**每次重新取**（`cache: 'no-cache'` 是站点一直以来的口径；把它也塞进
// 片段缓存里，等于按 hash 切回同一份文档时看到的还是上一次的字节）。片段留在缓存里只为
// 省下同一轮里重复引用同一份的请求次数——这两件事分不开时，"缓存"看起来总是对的。
let fetchCount = 0;
const _baseFetch = global.fetch;
global.fetch = function (u) { fetchCount++; return _baseFetch(u); };

function dirOf(p) {
  return p.indexOf('/') >= 0 ? p.slice(0, p.lastIndexOf('/') + 1) : '';
}

async function assemble(doc) {
  const raw = await impl.loadWithIncludes(doc);   // 取不到时它自己抛（带原因）
  return impl.fillPrimary(impl.expandIncludes(raw, dirOf(doc), 0));
}

// ---- 边界取值 --------------------------------------------------------------
// 切片（`tag=` 取段）、属性支持（`lines=` / `tags=`）与**缓存的作用范围**这三支
// **光看主流程看不出来**：段外的孤立 `end::` 会被当成本段结尾而返回空串、未实现的属性会做
// 整文展开、片段缓存跨轮留着旧内容——三种都静默给出**错误内容**，比把原指令留在页面上更
// 难发现。故给它们逐例的可核对取值。
//
// 夹具走 `__VIRTUAL__`（fetch 前的内存层），不落仓库文件：这些用例要的是"两轮之间内容变了"
// 这类输入，落成文件既脏工作区、又没法让第二轮读到不同内容。
const virtual = {};
global.__VIRTUAL__ = virtual;

function seed(name, text) {
  virtual[name] = text;
  impl.includeCache[name] = text;      // `expandIncludes()` 直接从缓存取片段
}

const FRAG = 'L1\n// tag::t[]\nIN\n// end::t[]\nL5\n';

const BOUNDARY_CASES = [
  // 段外的孤立 `end::` 在前：它不是本段的结尾，取段须继续往后找，返回段内正文而非空串
  ['orphan-end', function () {
    return impl.sliceTag('A\n// end::t[]\nB\n// tag::t[]\nIN\n// end::t[]\nC\n', 't');
  }],
  // 正常取段（正例：与上面成对，防"一律返回原指令 / 一律返回空"也判绿）
  ['plain-tag', function () {
    return impl.sliceTag(FRAG, 't');
  }],
  // 没有该 tag：返回 null，由调用方保留原指令（不得当成"这一段是空的"）
  ['missing-tag', function () {
    return impl.sliceTag(FRAG, 'nope');
  }],
  // 未实现的属性：保留原指令，不做整文展开（整文展开会静默给出错误内容）
  ['lines-attr', function () {
    seed('boundary.txt', FRAG);
    return impl.expandIncludes('include::boundary.txt[lines=1..2]', '', 0);
  }],
  ['tags-attr', function () {
    seed('boundary.txt', FRAG);
    return impl.expandIncludes('include::boundary.txt[tags=t]', '', 0);
  }],
  // 取不到片段：保留原指令，让读者看见"未装配"
  ['missing-file', function () {
    return impl.expandIncludes('include::nope.txt[]', '', 0);
  }],
  // 主文档即便已经在缓存里，也必须**重新取**一次（片段那几次不该跟着重取）
  ['main-refetched', async function () {
    virtual['boundary-main.adoc'] = 'V1\n';
    impl.includeCache['boundary-main.adoc'] = 'V1\n';
    const before = fetchCount;
    await impl.loadWithIncludes('boundary-main.adoc');
    virtual['boundary-main.adoc'] = 'V2\n';
    const second = await impl.loadWithIncludes('boundary-main.adoc');
    return (second === 'V2\n' && fetchCount - before === 2) ? 'main' : 'cached:' + JSON.stringify(second);
  }],
  // 片段**不跨轮复用**：主文档每轮重取、片段却留着上一轮的话，页面上是新旧混拼
  ['fragment-refetched', async function () {
    virtual['frag-main.adoc'] = 'doc\ninclude::frag-body.txt[]\n';
    virtual['frag-body.txt'] = 'OLD\n';
    const first = impl.expandIncludes(await impl.loadWithIncludes('frag-main.adoc'), '', 0);
    virtual['frag-body.txt'] = 'NEW\n';
    const second = impl.expandIncludes(await impl.loadWithIncludes('frag-main.adoc'), '', 0);
    if (first.indexOf('OLD') < 0) return 'first:' + JSON.stringify(first);
    return second.indexOf('NEW') >= 0 ? 'refetched' : 'stale:' + JSON.stringify(second);
  }],
  // 同一轮里重复引用同一份片段：只取一次（与上一条成对——防"干脆不缓存"把这条也改坏）
  ['fragment-once-per-round', async function () {
    virtual['dup-main.adoc'] = 'include::dup-body.txt[]\ninclude::dup-body.txt[]\n';
    virtual['dup-body.txt'] = 'X\n';
    const before = fetchCount;
    await impl.loadWithIncludes('dup-main.adoc');
    return fetchCount - before === 2 ? 'once' : 'fetches:' + (fetchCount - before);
  }],
  // 主文档取不到：要能分得清「HTTP 404」与「网络失败」——折成一个 null 时，网断了会
  // 显示成"该文件可能不在本仓库"，用户照着这句查错方向
  ['main-missing-error', async function () {
    try {
      await impl.loadWithIncludes('no-such-doc.adoc');
      return 'resolved';
    } catch (e) {
      return /HTTP 404/.test(e.message) ? 'http-404' : 'msg:' + e.message;
    }
  }],
  // 片段取不到**不算整轮失败**：正文照出，缺的那一处保留原指令（静默吞掉等于复制出去半份）
  ['fragment-missing-kept', async function () {
    virtual['frag-missing.adoc'] = 'body\ninclude::no-such-frag.txt[]\n';
    return await impl.loadWithIncludes('frag-missing.adoc');
  }],
];

if (require.main === module) {
  const arg = process.argv[2];
  if (arg === '--boundary') {
    (async function () {
      for (const [name, fn] of BOUNDARY_CASES) {
        process.stdout.write(JSON.stringify({ case: name, out: await fn() }) + '\n');
      }
    })().catch(function (e) {
      process.stderr.write(String(e && e.stack || e) + '\n');
      process.exit(1);
    });
    return;
  }
  if (!arg || process.argv.length > 3) {
    // 多给一个参数就**报错**：旧版这里收 `assembled` / `expanded` / `slice:` 三种步骤名，
    // 静默忽略会让人以为"那一步还在、只是没打印"
    process.stderr.write('用法: node site-include-check.js <文档路径> | --boundary\n');
    process.exit(2);
  }
  assemble(arg).then(function (text) {
    process.stdout.write(text);
  }).catch(function (e) {
    process.stderr.write(String(e && e.stack || e) + '\n');
    process.exit(1);
  });
}

module.exports = { assemble: assemble, impl: impl };
