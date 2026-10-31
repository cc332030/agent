#!/usr/bin/env node
// 站点正文区的站内链接映射：`index.html` 里 `toSitePath()` / `bindDocLinks()` 的**可核对取值**。
//
// 为什么单独放一份：`index.html` 是文档站（浏览器端渲染），它唯一的判据是"点下去落在哪个
// hash 上"，而这段取值只能靠真的跑一遍 JS 才拿得到。原先这条判据只在 PR 描述里手工实测过
// 一次——那份代码里两个事实性错误（`resolveTarget` 对带 scheme 的目标一律返回 null、站点
// 绝对地址解析时又叠加了当前文档目录）因此都没被拦住。故把取值抽到这里，由
// `check_specs.py` 的 `check_site_link_guard` 真的执行它。
//
// 用法：node site-link-check.js <当前文档路径>
// 输出：每个用例一行 JSON（输入链接、是否拦截、落到的 hash），由调用方逐条比对。
const REPO_ROOT = './';

// 与 index.html 保持同一份实现（改一处即改两处，比对用例会当场报出来）
function normalize(path) {
  var segments = String(path).replace(/\\/g, '/').split('/');
  var stack = [];
  for (var i = 0; i < segments.length; i++) {
    var s = segments[i];
    if (!s || s === '.') continue;
    if (s === '..') {
      if (stack.length === 0) return null;
      stack.pop();
      continue;
    }
    stack.push(s);
  }
  return stack.join('/');
}

function resolveTarget(target, docDir) {
  var t = (target || '').trim();
  if (!t) return null;
  if (/^[a-zA-Z][a-zA-Z0-9+.\-]*:/.test(t)) return null;
  if (t.charAt(0) === '#') return null;
  var hash = '';
  var query = '';
  var qi = t.indexOf('?');
  if (qi >= 0) { query = t.slice(qi); t = t.slice(0, qi); }
  var hi = t.indexOf('#');
  if (hi >= 0) { hash = t.slice(hi); t = t.slice(0, hi); }
  var path = normalize(docDir + t);
  if (path === null) return null;
  return { path: path, hash: hash + query };
}

function toSitePath(target, host) {
  var t = (target || '').trim();
  host = (host || '').toLowerCase();
  if (!host) return null;
  // 先去掉 scheme：`https://h/x` 与 `//h/x` 都要认（文档里的写法两种都有）
  var m = /^[a-zA-Z][a-zA-Z0-9+.\-]*:(.*)$/.exec(t);
  if (m) t = m[1];
  var base = '//' + host.split(':')[0] + '/';   // 比到端口为止：文档里的地址不带端口
  if (t.slice(0, base.length).toLowerCase() !== base) return null;
  return t.slice(base.length);
}

// 文档里的一个 <a>（对应 `index.html` 的 `bindDocLinks`）：点击后落到的 hash；
// 返回 null 即"保持浏览器默认行为"（外链、页内锚点、非 .adoc）。
function click(href, docPath, host) {
  var docDir = docPath.indexOf('/') >= 0 ? docPath.slice(0, docPath.lastIndexOf('/') + 1) : '';
  // 站内绝对地址要先认出来：`resolveTarget` 对带 scheme 的目标一律返回 null。
  // 收回本页时基准是站点根，不叠加当前文档目录。
  var sitePath = toSitePath(href, host);
  var resolved = sitePath !== null
    ? resolveTarget('/' + sitePath, '')
    : resolveTarget(href, docDir);
  if (!resolved) return null;
  if (!/\.adoc$/i.test(resolved.path)) return null;
  return '#./' + encodeURI(resolved.path) + (resolved.hash || '');
}

if (require.main === module) {
  const docPath = process.argv[2] || 'README.adoc';
  const host = process.argv[3] || 'agent.c332030.com';
  const hrefs = require('fs').readFileSync(0, 'utf8').split('\n').filter(Boolean);
  for (const href of hrefs) {
    process.stdout.write(JSON.stringify({ href: href, hash: click(href, docPath, host) }) + '\n');
  }
}

module.exports = { click: click, toSitePath: toSitePath, resolveTarget: resolveTarget };
