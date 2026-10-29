"""pathconfig - 读「规范集合的运行期配置」（取值的唯一一处定义）。

定位
----
同一份取值原先在执行侧、判据侧、文档模板各有一份，谁也不知道以哪份为准；三处各自漂移时
不会有任何东西报红——脚本换了取值、文档还写着旧的，新开实例照着文档找不到东西，而检查照旧
全绿。通用判据见 `specs/general/coding.adoc`「取值的唯一来源」。

本模块把「值」与「用它的地方」分开：**值只在同目录的 TOML 配置里**（改它不用改 `.py`），
执行侧与判据侧都取值于那一处。判据见 `check_specs.check_paths_single_source_guard`。

用法
----
    import pathconfig

    pathconfig.load()                    # 现场仓库那一份
    pathconfig.load("/path/to/repo")     # 指定仓库根（单测重定向用）
    cfg = pathconfig.load()
    cfg.landing_path()                   # 由配置里那两层目录名拼出的落点全路径

行为与副作用
------------
只读一个 TOML 文件，不写任何文件、不联网、无第三方依赖（`tomllib` 属标准库）。

关键约定与设计决策
------------------
* **家目录不进程配置**：配置只给家目录下的目录名，家目录本身由调用方现场取
  （`os.path.expanduser`）——配置里写绝对路径的话，同一份配置换台机器就失效，
  "落点只有一处"也退化成"每台机器各写一份"。
* **配置缺失或键不齐即报错、不退回硬编码**：退回默认值等于把"配置文件"变成可选装饰，
  两份来源又回来了（"核不到"与"核过且通过"必须分得清，见 `specs/general/verify.adoc`
  「验证的效力等级」）。故 `load()` 缺文件即抛 `ConfigError`；`_require` 缺键即抛。
* **不做格式兜底**：TOML 语法错由 `tomllib` 直接抛，转成 `ConfigError` 一并报出——
  读配置的失败路径只有一条，报错文案里带文件路径与出错项。
* **与 `fetch-specs.py` 里的读取实现是"同一件事的两个必须自足的副本"**（不是同一份逻辑
  写两遍）：判据脚本在仓库里跑、执行脚本还要能从**落点**单独跑，落点里没有 `script/`
  这一层（本仓库实测：从落点跑时互相 import 会 `ModuleNotFoundError`）。故两边各自内联
  读取，而**取值只有一处**；"代码里不写第二份字面量"由
  `check_specs.check_paths_single_source_guard` 机械核住。
* **配置跟着自己走**：读取层先找**本模块旁边**那一份（本模块与配置一起被分发时就在一处），
  找不到再按仓库内路径找——只按仓库路径找时，被分发出去的那一份当场读不到配置。
"""

import os
import tomllib

# 配置文件的仓库内相对路径：**本模块自己的定位**（与配置里 `scripts.config` 互为核对，
# 判据侧据此核"文档引的那一句指向的还是它"）。它是读取层的接线，不是"运行期取值"，
# 故留在代码里而不进配置文件——配置里写"配置文件自己叫什么"会绕成一个圈。
CONFIG_REL = "script/specs-config.toml"


class ConfigError(RuntimeError):
    """配置本身的问题（文件缺失、TOML 非法、必填键缺失）——属致命错，不静默退默认值。"""


class Config:
    """一份已读入的运行期配置；属性即"唯一真源"里的那些取值。"""

    # 必填项的属性名清单（读完即逐个取一遍）：一份配置缺了哪一项都须在加载时报出来，
    # 而不是等某条分支用到了才炸——"这一轮没走到那条分支"会把缺项伪装成一切正常。
    REQUIRED = ("landing_home_dir", "landing_app_dir", "base_url", "manifest_entry",
                "manifest_optional", "install_scripts", "entry_scripts", "config_rel",
                "timeout_seconds", "workers", "tmp_dir", "self_update_suffix",
                "self_handoff_suffix")

    def __init__(self, data, path):
        self.path = path
        self._data = data

    # ---- 取值 ----

    def _get(self, section, key):
        table = self._data.get(section)
        if not isinstance(table, dict) or key not in table:
            raise ConfigError(
                f"配置 {self.path} 缺少必填项 [{section}].{key}——"
                "路径与运行期取值只有这一处来源，缺项时调用方不得自己补一个默认值"
                "（那会让同一取值重新长出第二份）")
        return table[key]

    @property
    def landing_home_dir(self):
        """家目录下第一层目录名（落点的父目录）。"""
        return str(self._get("landing", "home_dir"))

    @property
    def landing_app_dir(self):
        """家目录下第二层目录名（落点自己）。"""
        return str(self._get("landing", "app_dir"))

    def landing_path(self, home=None):
        """落点全路径：`<家目录>/<home_dir>/<app_dir>`（只有一个落点，不按平台另取）。

        `home` 不给时按本机用户家目录取——**家目录在这里现取、不在配置里写死**。
        """
        home = os.path.expanduser("~") if home is None else home
        return os.path.join(home, *self.landing_rel)

    @property
    def landing_name(self):
        """落点的仓库外部写法（`<home_dir>/<app_dir>`）：文档与报错里引用它时用这一串。

        分隔符取 `/` 而不是 `os.sep`：这一串是**写给人看、给人抄**的路径写法（文档、报错、
        判据字面量都按它核），按平台变的话，同一份仓库在 Windows 上核出来的字面量与 Linux
        不同——两份写法又回来了。
        """
        return f"{self.landing_home_dir}/{self.landing_app_dir}"

    @property
    def landing_rel(self):
        """与 `landing_name` 同一串的分段形式：拼**本机**路径时用它（按平台分隔符）。"""
        return (self.landing_home_dir, self.landing_app_dir)

    @property
    def base_url(self):
        """规范来源的默认地址。"""
        return str(self._get("source", "base_url"))

    @property
    def manifest_entry(self):
        """取文件清单的来源文件（入口文档）。"""
        return str(self._get("manifest", "entry"))

    @property
    def manifest_optional(self):
        """有则取的文件清单。"""
        return tuple(self._get("manifest", "optional"))

    @property
    def install_scripts(self):
        """随规范分发的安装脚本（含逻辑代码）。"""
        return tuple(self._get("scripts", "all"))

    @property
    def entry_scripts(self):
        """其中**给人直接敲**的入口（取完须补可执行位）。"""
        return tuple(self._get("scripts", "entry"))

    @property
    def config_rel(self):
        """本文件自己的仓库内路径（与 `CONFIG_REL` 互为核对）。"""
        return str(self._get("scripts", "config"))

    @property
    def timeout_seconds(self):
        """单次请求超时（秒）。"""
        return int(self._get("network", "timeout_seconds"))

    @property
    def workers(self):
        """并发请求数。"""
        return int(self._get("network", "workers"))

    @property
    def tmp_dir(self):
        """临时产物的根目录名（工作目录下）。"""
        return str(self._get("temporary", "dir"))

    @property
    def self_update_suffix(self):
        """更新自身时新版本脚本的文件名后缀。"""
        return str(self._get("temporary", "self_update_suffix"))

    @property
    def self_handoff_suffix(self):
        """待换标记（交接文件）的文件名后缀。"""
        return str(self._get("temporary", "self_handoff_suffix"))


def config_path(repo_root):
    """某仓库根下配置文件的全路径（落点由 `CONFIG_REL` 唯一给出）。"""
    return os.path.join(repo_root, *CONFIG_REL.split("/"))


def config_beside_module():
    """**与本模块同处**的那一份配置（配置随本模块一起被分发时就是它）；不在时返回 `None`。

    为什么就近优先：本模块与配置会随安装脚本一起落到别处（落点根下），那里没有 `script/`
    这一层——只按仓库内路径找时，被分发出去的那一份读不到配置、当场退出。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        CONFIG_REL.split("/")[-1])
    return path if os.path.isfile(path) else None


def load_file(path):
    """读**指定的那一份**配置；文件不在、TOML 非法、必填项缺失一律抛 `ConfigError`。

    执行侧（`fetch-specs.py`）走这一条：它的配置落点要按"本脚本旁边优先"定，
    与本模块所在目录无关，故由调用方给出路径、本模块只管读。
    """
    if not os.path.isfile(path):
        raise ConfigError(
            f"缺少运行期配置 {path}——路径与运行期取值只有这一处来源，"
            "文件不在时执行侧与判据侧无从取值（不得退回各自写死的默认值，那就是第二份来源）")
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"配置 {path} 不是合法 TOML：{exc}") from exc
    cfg = Config(data, path)
    # 读完即核一遍必填项：缺键必须在加载时就报，而不是等某条分支用到了才炸（那时
    # "这一轮没走到那条分支"会把配置缺项伪装成一切正常）
    for name in Config.REQUIRED:
        getattr(cfg, name)
    return cfg


def load(repo_root=None):
    """读入配置；文件不在、TOML 非法、必填项缺失一律抛 `ConfigError`（不退回默认值）。

    `repo_root` 不给时取本模块所在目录的父目录（`script/` 的上一层即仓库根）。
    给了 `repo_root` 就按它找、**不再就近兜底**：判据要核的是"这个仓库的配置"，
    拿旁边那份顶上等于对着另一份取值核（两份同时存在时，就近那份永远赢）。
    """
    root = os.path.abspath(repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 显式指定仓库根时按它找；否则先找与本模块同处的那一份（配置随分发物走时就在那里），
    # 再找仓库内那一份
    path = config_path(root) if repo_root else (config_beside_module() or config_path(root))
    return load_file(path)
