#!/usr/bin/env python3
"""『任务频繁中断』的机械守卫：**每一步执行都要有可判定的时限**（纯 stdlib）。

要治的失效
----------
任务被中断的**最常见的可修成形态**不是模型出错，而是**某一步永远不返回**：agent 发起一次
构建/测试/网络请求后，那一步没有时限、也没有进度输出，工具层不见失败信号，于是**整轮停在
那里直到人工介入**——表现就是"任务频繁中断"（现场清理后从头再来一遍）。

规范侧已经写了这条要求（`specs/general/collab.adoc`「操作超时与超时后的处置」：**每一次操作
自带可判定的时限**，超时后先排查、再换手段继续；`specs/platform/cnb.adoc`「协作与执行者
可用性」补了本平台上的后果——本平台执行是**跨轮次接续**的，一次操作卡死不是"慢"，而是整轮
停住直到人工介入）。缺的不是又一句要求，而是**能在配置里核对、能在运行里拦住的抓手**：

* **配置侧（本脚本）**：流水线/构建配置里，**每一步**（job、stage、step，以及带时限语义的
  键）都必须能查到**可判定的时限**——`timeout` 一类键。少了就是"这一步按设计可以无限跑"。
* **运行侧（随本脚本分发的运行件）**：给**每一次**命令执行套上**墙钟时限**，到点即终止该次
  执行并**带出可读的现场**（已产出的输出 + 超时说明），使"卡住"变成一次**可继续的失败**
  而不是整轮中断；判据与用法见 `specs/general/collab.adoc`「操作超时与超时后的处置」。

用法
----
    python3 script/guard/check_pipeline_timeout.py                     # 查本仓库
    python3 script/guard/check_pipeline_timeout.py --repo <目录>        # 查任意项目
    python3 script/guard/check_pipeline_timeout.py --file x.yml         # 只查指定配置
    python3 script/guard/check_pipeline_timeout.py --require-key timeout --require-key 'timeout-minutes'
    python3 script/guard/check_pipeline_timeout.py --list-configs       # 只列出被核的配置

退出码：0 全绿；1 有违规；2 参数或前置条件错误。**配置一份都没核到**（没有可核的配置、
或约定的配置文件不存在）一律按 1 退出——"核不到"与"核过且通过"必须分得开。
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import yaml_min  # noqa: E402  （同目录的最小 YAML 子集解析器）

# 约定的**配置清单**：类型名 → 候选相对路径（命中第一个存在的即核；都不存在则记一条缺口）。
# 本仓库另在 `.guard/pipeline-timeout.toml`（若存在）里覆盖/追加，便于项目自行扩展。
CONFIG_CANDIDATES = [
    (".cnb.yml", ["cnb"]),
    (".cnb.yaml", ["cnb"]),
    (".github/workflows", ["github-workflow"]),
    (".gitlab-ci.yml", ["gitlab"]),
    ("Jenkinsfile", ["jenkins"]),
]

# `.github/workflows` 是**目录**：核其下全部 `.yml` / `.yaml`。
DIR_GLOBS = {
    ".github/workflows": (".yml", ".yaml"),
}

# 非 GitHub/CNB 的配置：该平台的"步骤容器"路径（点分，序列下标写数字通配 `*`）。
# 取值口径：**容器里的每一项都是一个可独立挂时限的执行单位**——这条按配置自身的语义给，
# 不按"看起来像不像"给。
STEP_PATHS = {
    "github-workflow": ["jobs.*.steps.*"],
    "cnb": ["$", "jobs.*", "jobs.*.stages.*", "jobs.*.stages.*.steps.*", "jobs.*.steps.*"],
    "gitlab": ["$", "job:*.script"],
    "jenkins": ["$"],
}

# 默认的**时限键**：任一命中即视为"这一步有时限"。项目可追加（`--require-key`）。
DEFAULT_TIMEOUT_KEYS = ["timeout", "timeout-minutes", "timeoutMinutes"]

# 键名里出现这些片段即视为"带时限语义的键"（即使不在默认清单里也算已设时限）——
# 判据按**语义**取，不按某个平台的写法取。
TIMEOUT_KEY_HINTS = ("timeout", "time-limit", "timelimit", "deadline", "max-duration")


def _iter_configs(root, extra_files):
    """产出被核的配置：(相对路径, 类型)。"""
    out = []
    for rel in extra_files:
        kind = "generic"
        for name, kinds in CONFIG_CANDIDATES:
            if rel == name or rel.startswith(name.rstrip("/") + "/"):
                kind = kinds[0]
        out.append((rel, kind))
    for name, kinds in CONFIG_CANDIDATES:
        path = os.path.join(root, name)
        if os.path.isdir(path):
            suffixes = DIR_GLOBS.get(name, (".yml",))
            for entry in sorted(os.listdir(path)):
                if entry.endswith(suffixes):
                    out.append((name + "/" + entry, kinds[0]))
        elif os.path.isfile(path):
            out.append((name, kinds[0]))
    # 去重、保序
    seen, uniq = set(), []
    for item in out:
        if item[0] not in seen:
            seen.add(item[0])
            uniq.append(item)
    return uniq


def _normalize_steps(node, kind, step_paths):
    """把配置里"可挂时限的执行单位"逐个取出，产出 (路径描述, 对象, 容器路径)。"""
    units = []
    for path in step_paths:
        if path == "$":
            units.append(("$", node))
            continue
        units.extend(_expand(node, path.split("."), path))
    return units


def _expand(node, parts, path):
    """按点分路径展开（`*` 展开序列/映射的每一项）。"""
    if not parts:
        return [(path, node)]
    head, rest = parts[0], parts[1:]
    out = []
    if head == "*":
        if isinstance(node, list):
            for i, item in enumerate(node):
                out.extend(_expand(item, rest, "%s[%d]" % (path, i)))
        elif isinstance(node, dict):
            for key, item in node.items():
                out.extend(_expand(item, rest, "%s[%s]" % (path, key)))
        return out
    if isinstance(node, dict) and head in node:
        out.extend(_expand(node[head], rest, path))
    return out


def _has_timeout(unit, keys, hints=TIMEOUT_KEY_HINTS):
    """该执行单位是否含可判定的时限（键名或键名里的时限语义）。"""
    if not isinstance(unit, dict):
        return False
    for key in unit:
        if key in keys:
            return True
        lowered = str(key).lower()
        if any(h in lowered for h in hints):
            return True
    return False


def check_yaml(rel, kind, text, keys, errors):
    """核一份 YAML 配置；违规写进 `errors`，返回核过的执行单位数。

    **时限可以设在该单位自己身上、也可以设在其外层容器上**（平台的时限语义就是"最近的那个
    生效/取更严者"）：例如 GitHub Actions 的 job 级 `timeout-minutes` 会约束该 job 的每个
    step（`jobs.<id>.timeout-minutes` 是官方口径），故 job 上有时限时其 steps 不必逐个再设。
    """
    try:
        node = yaml_min.load(text)
    except yaml_min.YamlSubsetError as exc:
        errors.append("%s：解析失败（%s）——配置读不出来即报红，不得当成'没有该键'"
                      % (rel, exc))
        return 0
    if node is None:
        errors.append("%s：配置为空——该项目的流水线无从核对时限" % rel)
        return 0

    if kind == "github-workflow":
        return _check_github_workflow(rel, node, keys, errors)
    if kind == "cnb":
        return _check_cnb(rel, node, keys, errors)
    return _check_generic(rel, kind, node, keys, errors)


def _check_github_workflow(rel, node, keys, errors):
    """GitHub Actions：逐 job 核——job 级时限覆盖其 steps；**可复用工作流**没有 steps。

    判据按 job 自身的形态取值，不按"看起来像"取值：
    * job 声明了 `uses:`（可复用工作流）→ 它的时限由被调工作流自己管，本文件**不可挂**，
      故不核（核了就是假红）；本工具的靶心是"本文件里能挂时限的执行单位"。
    * 其余 job → `timeout-minutes`（job 级）或**每个 step** 的 `timeout-minutes`。
    """
    jobs = yaml_min.get_path(node, "jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append("%s：未找到 jobs——配置结构变了须同步本守卫的容器路径，不得静默空转" % rel)
        return 0
    checked = 0
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            errors.append("%s：jobs.%s 不是映射——配置读法超出本守卫的判据" % (rel, job_name))
            continue
        if "uses" in job:
            continue  # 可复用工作流：时限由被调工作流承载，本文件不可挂
        steps = job.get("steps")
        if not isinstance(steps, list):
            errors.append("%s：jobs.%s 既无可复用的 `uses`、也没有 `steps`——"
                          "该 job 的时限无从判定" % (rel, job_name))
            continue
        job_level = _has_timeout(job, keys)
        for idx, step in enumerate(steps):
            name = "jobs.%s.steps[%d]" % (job_name, idx)
            if isinstance(step, dict) and ("name" in step or "uses" in step or "run" in step):
                name += "(%s)" % (step.get("name") or step.get("uses") or "run")
            checked += 1
            if job_level or _has_timeout(step, keys):
                continue
            errors.append("%s：%s 未设可判定的时限（job 级 `timeout-minutes` 或该 step 的 "
                          "`timeout-minutes`）——这一步按设计可以无限跑，卡住即整轮停住"
                          % (rel, name))
    return checked


def _check_cnb(rel, node, keys, errors):
    """CNB：`jobs.*`／`jobs.*.stages.*`／其内的 steps 逐项核（同 `STEP_PATHS` 的容器口径）。"""
    units = _normalize_steps(node, "cnb", STEP_PATHS["cnb"])
    if not units:
        errors.append("%s：未找到可挂时限的执行单位——配置结构变了须同步本守卫的容器路径" % rel)
        return 0
    checked = 0
    for name, unit in units:
        if not isinstance(unit, dict):
            continue
        if name == "$":
            # 顶层管道：逐 job 核（`jobs.<id>`）
            for job_name, job in unit.items():
                if job_name == "jobs":
                    continue
                if isinstance(job, dict):
                    checked += 1
                    if not _has_timeout(job, keys):
                        errors.append("%s：%s 未设可判定的时限（%s 之一）——"
                                      "这一步按设计可以无限跑，卡住即整轮停住"
                                      % (rel, job_name, "/".join(keys)))
            continue
        checked += 1
        if not _has_timeout(unit, keys):
            errors.append("%s：%s 未设可判定的时限（%s 之一）——"
                          "这一步按设计可以无限跑，卡住即整轮停住"
                          % (rel, name, "/".join(keys)))
    return checked


# "这张映射本身就是一个执行单位"的判据键：**只收"承载一步执行"的键**。
# 刻意**不收** `image`：镜像名是"用什么环境跑"，不是"跑了一步"——收它会把手写配置里
# 与执行无关的 `image:` 配置项（如 `.gitlab-ci.yml` 顶层的 `image:`）判成执行单位并报红。
UNIT_MARKERS = ("name", "run", "script", "uses", "stage", "steps", "commands", "sh", "bash")


def _looks_like_unit(unit):
    """这张映射本身像不像一个"执行单位"（含 `UNIT_MARKERS` 里承载执行的键）。"""
    return any(k in unit for k in UNIT_MARKERS)


def _check_generic(rel, kind, node, keys, errors):
    """其余平台：按 `STEP_PATHS` 给的容器路径逐项核（结构不符即报红、不静默空转）。"""
    step_paths = STEP_PATHS.get(kind, ["$"])
    units = _normalize_steps(node, kind, step_paths)
    if not units:
        errors.append("%s：未找到可挂时限的执行单位（按 %s 的容器路径 %s 取）——"
                      "配置结构变了须同步本守卫的容器路径，不得静默空转"
                      % (rel, kind, "/".join(step_paths)))
        return 0
    checked = 0
    for name, unit in units:
        if not isinstance(unit, dict):
            continue
        # `$`（顶层管道）与"本身不像执行单位的映射"同路：逐子项核。
        # `job:*.script` 这类容器路径取到的就是顶层映射本身，其子项才是执行单位；
        # 与执行无关的子项（`.gitlab-ci.yml` 顶层的 `values:`/`variables:` 一类配置块）
        # 不是执行单位，不核——核了就是假红。
        if name == "$" or not _looks_like_unit(unit):
            for sub_name, sub in unit.items():
                if not isinstance(sub, dict):
                    continue
                if not _looks_like_unit(sub):
                    continue  # 与执行无关的配置块
                checked += 1
                if not _has_timeout(sub, keys):
                    errors.append("%s：%s.%s 未设可判定的时限（%s 之一）——"
                                  "这一步按设计可以无限跑，卡住即整轮停住"
                                  % (rel, name, sub_name, "/".join(keys)))
            continue
        checked += 1
        if not _has_timeout(unit, keys):
            errors.append("%s：%s 未设可判定的时限（%s 之一）——"
                          "这一步按设计可以无限跑，卡住即整轮停住"
                          % (rel, name, "/".join(keys)))
    return checked


def _check_non_yaml(rel, path, keys, errors):
    """非 YAML 配置（如 Jenkinsfile/Groovy）：按文本找时限声明，找不到即报绿不报红——
    它是"尽力而为"的兜底（能否判定属语义判断），但**必须说明**核没核到。"""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        errors.append("%s：读取失败（%s）" % (rel, exc))
        return False
    lowered = text.lower()
    for key in keys:
        if key.lower() in lowered:
            return True
    for hint in TIMEOUT_KEY_HINTS:
        if hint in lowered:
            return True
    errors.append("%s：未找到任何时限声明（%s 之一）——该配置的步骤无从判定时限，"
                  "按'有时限'报绿属假绿，故按未设处置" % (rel, "/".join(keys)))
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="流水线步骤时限守卫（纯 stdlib）")
    parser.add_argument("--repo", default=os.getcwd(), help="被核的项目根目录")
    parser.add_argument("--file", action="append", default=[],
                        help="只核指定的配置（相对项目根；可多次）")
    parser.add_argument("--require-key", action="append", default=[],
                        help="追加可接受的时限键名（可多次）")
    parser.add_argument("--list-configs", action="store_true", help="只列出被核的配置")
    parser.add_argument("--quiet", action="store_true", help="只在有违规时输出")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.repo)
    if not os.path.isdir(root):
        print("参数错误：--repo 不是目录：%s" % root, file=sys.stderr)
        return 2
    keys = list(DEFAULT_TIMEOUT_KEYS) + list(args.require_key)
    configs = _iter_configs(root, args.file)
    if args.list_configs:
        for rel, kind in configs:
            print("%s\t%s" % (rel, kind))
        return 0
    if not configs:
        print("无配置可核：本项目没有约定的流水线配置（%s）——"
              "『核不到』不得当成『核过且通过』"
              % "、".join(name for name, _ in CONFIG_CANDIDATES), file=sys.stderr)
        return 1

    errors, checked = [], 0
    for rel, kind in configs:
        path = os.path.join(root, *rel.split("/"))
        if kind == "jenkins":
            _check_non_yaml(rel, path, keys, errors)
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        checked += check_yaml(rel, kind, text, keys, errors)

    if errors:
        for msg in errors:
            print("FAIL %s" % msg)
        print("\n核了 %d 个执行单位、%d 条违规——每一步执行都须有可判定的时限"
              "（判据见 specs/general/collab.adoc「操作超时与超时后的处置」）" % (checked, len(errors)))
        return 1
    if not args.quiet:
        print("OK 核了 %d 份配置、%d 个执行单位，均含可判定的时限" % (len(configs), checked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
