#!/usr/bin/env python
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""YYN0114配音工具(Lite)—— 字幕 / 配音批处理工具集

界面结构：
  · 顶部  两个文件夹选择器（源目录 / 输出目录），支持 拖入 / 手输 / 浏览
  · 左栏  工具栏（可折叠）：配音工具 + 目录设置地址栏 + 版权/关于
  · 右栏  常用按钮（C 位 = 一键版，其次 = ZH的csv拆分）
  · 底部  日志输出区

主流程：csv 拆分 → 台本 → 配音（IndexTTS）→ OGG，以及常用的字幕处理按钮。
不预置任何路径，全部由使用者在界面里自行设置；配置单独存 config_lite.json。

所有脚本以模块方式内嵌，打包为单文件 exe 后可任意位置运行。
"""
from __future__ import annotations

import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except Exception:                                    # 拖放库缺失时降级为手输+浏览
    TkinterDnD = None
    DND_FILES = None
    HAS_DND = False

from scripts import (                                # noqa: E402
    check_subtitle_content,
    csv_split_srt,
    delete_by_content,
    export_vo_text,
    extract_untranslated,
    find_missing_subtitles,
    remove_line_numbers,
    replace_by_dict,
    update_subtitles,
    wav_to_ogg,
)

APP_TITLE = "YYN0114配音工具(Lite)"
APP_VERSION = "1.0"
HOME_URL = "https://space.bilibili.com/1800421262"     # 发布者主页（版权页可点击）

# 不预置任何路径，全部由使用者自行选择（工作区默认落在用户主目录下）
YYN_ROOT = os.path.join(os.path.expanduser("~"), "YYNtools")

ITTS_ROOT_DEFAULT = ""

MODEL_ITTS = "IndexTTS 2.5"
MODEL_GPT = "GPT-SoVITS v2Pro"
MODELS = [MODEL_ITTS, MODEL_GPT]

# 「八向」情感向量：显示名 + 配置键；顺序 = 传给 IndexTTS 的 8 维向量顺序（不可改）
EMO8_DIMS = [
    ("高兴", "happy"), ("愤怒", "angry"), ("悲伤", "sad"), ("恐惧", "fear"),
    ("反感", "disgust"), ("低落", "low"), ("惊讶", "surprise"), ("自然", "neutral"),
]

# 配音脚本（从 exe 内释放到 %APPDATA%\YYNTools\dub_scripts 后由各自的解释器运行）
DUB_FILES = ("dub_itts.py", "dub_gpt.py", "tts_resident.py", "sound-askuser.wav")

# 常驻 TTS 服务（tts_resident.py）：端口 + 登记文件（服务启动后写 pid/port，供「关闭TTS」定位）
RESIDENT_PORT = 9882
RESIDENT_MARKER = (Path(os.environ.get("TEMP", str(Path.home())))
                   / "YYNTools" / "tts_resident.json")

# 「试听」用固定文本（纯音色、不加情感）：句子自带停顿，便于听音色与断句
PREVIEW_TEXT = "这是一段试听语音，一二三四五六七八九十，用来感受当前音色的效果。"

# 状态指示灯的颜色：正常灰 / 忙（橙）/ 需注意（红）
LED_OK = "#9e9e9e"
LED_BUSY = "#fb8c00"
LED_WARN = "#e53935"

DEFAULTS = {
    # 工作区目录：首次启动留空，需用户设置；source / srt / voices / output / votxt / dict.txt 全由它推导
    "workspace": "",
    # 以下 6 项由「工作区目录」自动推导（工作区为空时它们也留空），不再单独显示、也不用手填
    "source": "",
    "target": "",
    "dub_voice_dir": "",
    "votxt": "",
    "dict": "",
    "ffmpeg": "",
    "gptsovits": "",                               # 安装根目录，由使用者指定
    # ---------------- 配音工具（侧栏） ----------------
    "dub_in": "",                                  # 待配音的 srt 目录
    "dub_out": "",                                 # 配音输出根（下建 dub/ 与 script/）
    "dub_model": MODEL_ITTS,
    "dub_voice": "",
    "dub_emo_on": "1",
    "dub_emo_weight": "0.65",
    "dub_emo8_on": "1",
    "dub_emo_ref": "0",                            # 「按原音色参考」：同名原音频当情感参考
    "dub_pick_on": "0",                            # 单独选文件：勾选后覆盖「配音文件夹」
    "dub_pick_files": "",                          # 单独选中的文件（多个用 | 分隔，仅用于落盘）
    "dub_voice_order": "",
    "itts_root": ITTS_ROOT_DEFAULT,
    # ---------------- 常驻 TTS / 列表视图 / 手机推送 ----------------
    "auto_resident": "1",                          # 常驻模式：TTS 只加载一次，跑完不关
    "pending_dir": "",                             # 「列表视图」用：待配音文件夹的根目录
    "list_view": "0",                              # 「列表视图」：勾选后配音文件夹换成文件夹下拉
    "simple_mode": "1",                            # 「简略模式」：地址栏只留工作区 + TTS 路径（默认开）
    "ntfy_topic": "",                              # 手机 ntfy 推送主题；留空 = 不推手机，只响本地提示音
}
# 八向滑块默认值：只有「自然」为 1，其余为 0（等价于单一「自然」向量）
DEFAULTS.update({f"dub_e8_{k}": ("1.0" if k == "neutral" else "0.0") for _, k in EMO8_DIMS})

# 配置单独一份，互不影响
CONFIG_PATH = Path(os.environ.get("APPDATA", str(Path.home()))) / "YYNTools" / "config_lite.json"


# --------------------------------------------------------------- 配置持久化
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        if CONFIG_PATH.is_file():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------- 输出流
class QueueWriter(io.TextIOBase):
    """把子任务/脚本的 stdout 转进日志队列；「紧急中止」后一律丢弃（不再输出任何内容）。"""

    def __init__(self, q: queue.Queue, gate=None):
        self.q = q
        self.gate = gate          # 返回 True = 已中止，此后所有输出直接丢掉

    def write(self, s):
        if s and not (self.gate and self.gate()):
            self.q.put(s)
        return len(s)

    def flush(self):
        pass


class _Aborted(Exception):
    """「紧急中止」打断流水线用的内部异常（在检查点抛出，让 worker 立刻收工）。"""


# --------------------------------------------------------------- 路径选择行
class PathRow(ttk.Frame):
    """一行：标签 + 输入框 + 浏览按钮，支持拖入。kind='dir' 或 'file'

    pick_parent_dir=True 时「浏览」弹的是文件对话框（能进文件夹看有哪些文件），
    选中文件后取它所在的那个文件夹填入（用来挑目录的同时能预览文件）。
    """

    def __init__(self, parent, label, var: tk.StringVar, kind="dir",
                 filetypes=None, label_width=11, pick_parent_dir=False):
        super().__init__(parent)
        self.var = var
        self.kind = kind
        self.pick_parent_dir = pick_parent_dir
        self.filetypes = filetypes or [("所有文件", "*.*")]

        ttk.Label(self, text=label, width=label_width, anchor="e").pack(side="left")
        self.entry = ttk.Entry(self, textvariable=var)
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(self, text="浏览", width=6, command=self.browse).pack(side="left")

        if HAS_DND:
            for w in (self.entry,):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self.on_drop)
                except Exception:
                    pass

    def browse(self):
        if self.pick_parent_dir:
            # 用文件对话框浏览目录内容；选中哪个文件都无所谓，只取它所在的文件夹
            p = filedialog.askopenfilename(
                title="选中该文件夹里的任意文件（会取它所在的文件夹）",
                filetypes=self.filetypes)
            if p:
                self.var.set(os.path.normpath(os.path.dirname(p)))
            return
        if self.kind == "dir":
            p = filedialog.askdirectory(title="选择文件夹")
        else:
            p = filedialog.askopenfilename(title="选择文件", filetypes=self.filetypes)
        if p:
            self.var.set(os.path.normpath(p))

    def on_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        if not paths:
            return
        p = paths[0]
        if self.kind == "dir" and os.path.isfile(p):
            p = os.path.dirname(p)          # 拖文件进来 → 取其所在目录
        self.var.set(os.path.normpath(p))
        return event.action


# --------------------------------------------------------------- 折叠分区
class CollapsibleSection(ttk.Frame):
    """可折叠分区；传入 enable_var 时，标题前多一个勾选框（勾选框 + 折叠栏的组合）。

    勾选框关闭 → 分区收起并置灰语义（调用方自行决定怎么用这个开关）。
    """

    def __init__(self, parent, title, expanded=True, enable_var=None):
        super().__init__(parent)
        self.enable_var = enable_var
        self.expanded = tk.BooleanVar(value=expanded)

        head = ttk.Frame(self)
        head.pack(fill="x", pady=(6, 2))
        if enable_var is not None:
            ttk.Checkbutton(head, variable=enable_var, command=self._toggle).pack(side="left")
        ttk.Checkbutton(
            head, text=title, variable=self.expanded,
            style="Section.TCheckbutton", command=self._toggle,
        ).pack(side="left")

        self.body = ttk.Frame(self)
        self._toggle()

    def enabled(self) -> bool:
        return True if self.enable_var is None else bool(self.enable_var.get())

    def _toggle(self):
        if self.expanded.get() and self.enabled():
            self.body.pack(fill="x", padx=(14, 4))
        else:
            self.body.pack_forget()


# --------------------------------------------------------------- 主程序
class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.vars: dict[str, tk.StringVar] = {k: tk.StringVar(value=v) for k, v in self.cfg.items()}
        self.out_q: queue.Queue = queue.Queue()
        self.busy = False
        self.buttons: list[ttk.Button] = []
        self.procs: list[subprocess.Popen] = []
        # 「紧急中止」的总闸：置位后流水线在检查点抛出 _Aborted，且输出被 QueueWriter 丢弃。
        # abort_ev 指向「当前任务」的闸；每个任务另建一个专属 Event（见 _run），
        # 靠线程本地变量 _tls 绑定，这样上一批的闸不会误伤下一批。
        self.abort_ev = threading.Event()
        self._tls = threading.local()

        # 配音工具的状态（勾选框 / 滑块需要数值型变量，字符串版同步存进 vars 以便落盘）
        self.emo_on = tk.BooleanVar(value=str(self.cfg.get("dub_emo_on", "1")) not in ("", "0", "False"))
        self.emo_on.trace_add("write", lambda *_: self.vars["dub_emo_on"].set("1" if self.emo_on.get() else "0"))
        self.emo_var = tk.DoubleVar(value=float(self.cfg.get("dub_emo_weight") or 0.65))
        self.emo_var.trace_add("write", lambda *_: self.vars["dub_emo_weight"].set(f"{self.emo_var.get():.3f}"))
        # 八向向量：勾选框控制用不用八向；每个滑块 0~1，最终值 = 滑块 × 情感强度
        self.emo8_on = tk.BooleanVar(value=str(self.cfg.get("dub_emo8_on", "1")) not in ("", "0", "False"))
        self.emo8_on.trace_add("write", lambda *_: self.vars["dub_emo8_on"].set("1" if self.emo8_on.get() else "0"))
        self.emo8_vars: dict[str, tk.DoubleVar] = {}
        for _, key in EMO8_DIMS:
            dv = tk.DoubleVar(value=float(self.cfg.get(f"dub_e8_{key}") or 0.0))
            dv.trace_add(
                "write",
                lambda *_, kk=key: self.vars[f"dub_e8_{kk}"].set(f"{self.emo8_vars[kk].get():.3f}"),
            )
            self.emo8_vars[key] = dv
        # 「按原音色参考」：与 srt 同名的原音频当情感参考（找不到同名则回落用八向向量）
        self.emo_ref = tk.BooleanVar(
            value=str(self.cfg.get("dub_emo_ref", "0")) not in ("", "0", "False"))
        self.emo_ref.trace_add(
            "write", lambda *_: self.vars["dub_emo_ref"].set("1" if self.emo_ref.get() else "0"))
        # 「单独选文件」：勾选后用选中的文件替代「配音文件夹」（可跨目录、可多选）
        self.pick_on = tk.BooleanVar(
            value=str(self.cfg.get("dub_pick_on", "0")) not in ("", "0", "False"))
        self.pick_on.trace_add(
            "write", lambda *_: self.vars["dub_pick_on"].set("1" if self.pick_on.get() else "0"))
        self.pick_files: list[str] = [
            p for p in str(self.cfg.get("dub_pick_files") or "").split("|") if p]
        # 常驻模式：勾选 = 配音时启动常驻 TTS 服务并复用，跑完不关（默认开启）
        self.auto_resident = tk.BooleanVar(
            value=str(self.cfg.get("auto_resident", "1")) not in ("", "0", "False"))
        self.auto_resident.trace_add(
            "write", lambda *_: self.vars["auto_resident"].set("1" if self.auto_resident.get() else "0"))
        # 「列表视图」：勾选后「配音文件夹」换成「待配音目录」下的子文件夹下拉（只显示文件夹名）
        self.list_view = tk.BooleanVar(
            value=str(self.cfg.get("list_view", "0")) not in ("", "0", "False"))
        self.list_view.trace_add(
            "write", lambda *_: self.vars["list_view"].set("1" if self.list_view.get() else "0"))
        # 「简略模式」：勾选后地址栏只留「工作区目录 + TTS 路径」，其余地址行隐藏（值保留、功能照常）
        self.simple_mode = tk.BooleanVar(
            value=str(self.cfg.get("simple_mode", "1")) not in ("", "0", "False"))
        self.simple_mode.trace_add(
            "write", lambda *_: self.vars["simple_mode"].set("1" if self.simple_mode.get() else "0"))
        self._voice_paths: dict[str, str] = {}      # 音色显示名 → wav 绝对路径
        self._gpt_ref_text: dict[str, str] = {}     # 音色显示名 → 参考音频文本（GPT 必需）
        self._gpt_ref_lang: dict[str, str] = {}     # 音色显示名 → 参考文本语种（zh/en）
        # 状态指示灯：常驻服务最近一次探测结果（None = 没在跑）+ 上一批统计
        self._led_health = None                     # /health 的内容，或 None
        self._led_stat = (0, 0, 0)                  # (本批文件数, 无参考跳过, 失败)
        # 工作区目录：改一次，下面 6 个子路径立刻跟着变
        self._ws_job = None
        self.vars["workspace"].trace_add("write", lambda *_: self._on_workspace_change())

        root.title(f"{APP_TITLE}  v{APP_VERSION}")
        root.geometry("1080x780")
        root.minsize(900, 640)

        self._init_style()
        self._build_ui()
        self._apply_workspace(create=True)          # 启动就按工作区把目录结构补齐
        self._poll()
        self.root.after(400, self._check_workspace)  # 工作区为空 → 首次使用提醒
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -------------------------------------------------- 工作区目录
    # 工作区下由它推导的子路径（改一处即可）：源目录 / 字幕输出 / 音色目录 / 配音输出 / 台词文本 / 词表
    # dict.txt 是文件，只推导不创建；其余是目录，会顺手建出来
    WORKSPACE_SUBS = (
        ("source", "source"),
        ("target", "srt"),
        ("dub_voice_dir", "voices"),
        ("dub_out", "output"),
        ("votxt", "votxt"),
        ("dict", "dict.txt"),
        ("ffmpeg", os.path.join("ffmpeg", "ffmpeg.exe")),
    )

    def _apply_workspace(self, create: bool = False):
        """按「工作区目录」重算各子路径；create=True 时顺手把目录建出来。

        工作区为空（首次启动）→ 各子路径也留空，由用户先设工作区。
        """
        root = self.vars["workspace"].get().strip().strip('"')
        for key, name in self.WORKSPACE_SUBS:
            self.vars[key].set(os.path.join(root, name) if root else "")
        if create:
            self._make_workspace_dirs()

    def _make_workspace_dirs(self, force: bool = False):
        """补齐工作区下的目录（dict.txt 是文件，不建）。

        force=False 时只在工作区根目录已存在时创建，避免半截路径产生多余空目录。
        """
        root = self.vars["workspace"].get().strip().strip('"')
        if not root or (not force and not os.path.isdir(root)):
            return
        for _, name in self.WORKSPACE_SUBS:
            if os.path.splitext(name)[1]:        # 带扩展名 = 文件，跳过
                continue
            try:
                os.makedirs(os.path.join(root, name), exist_ok=True)
            except Exception:
                pass

    def _on_workspace_change(self):
        """改工作区目录：立即重算子路径，停顿 1.5 秒后再补目录结构。"""
        self._apply_workspace()
        if self._ws_job is not None:
            try:
                self.root.after_cancel(self._ws_job)
            except Exception:
                pass
        self._ws_job = self.root.after(1500, self._make_workspace_dirs)

    def _check_workspace(self):
        """启动提醒：工作区为空（首次使用）→ 弹窗告知先去设置。"""
        if self.vars["workspace"].get().strip():
            return
        self.sec_dirs.expanded.set(True)             # 直接展开地址栏，省得找不到
        self.sec_dirs._toggle()
        messagebox.showinfo(
            "首次使用：请先设置目录",
            "检测到「工作区目录」为空。请先在左侧「▸ 目录设置（地址栏）」里设置：\n\n"
            "① 工作区目录（必填）\n"
            "     source / srt / voices / output / votxt / dict.txt / ffmpeg.exe\n"
            "     都会在它下面自动创建并推导\n"
            "② 配音文件夹、IndexTTS 根目录等按需填写\n\n"
            f"建议把工作区放在：{YYN_ROOT}")

    # -------------------------------------------------- 样式
    def _init_style(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:
            pass
        base = ("Microsoft YaHei UI", 10)
        self.root.option_add("*Font", base)
        style.configure(".", font=base)
        style.configure("Section.TCheckbutton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Hero.TButton", font=("Microsoft YaHei UI", 13, "bold"), padding=(10, 14))
        style.configure("Main.TButton", font=("Microsoft YaHei UI", 10), padding=(10, 8))
        style.configure("Side.TButton", font=("Microsoft YaHei UI", 9), padding=(8, 5))
        # 「原声 / 试听」这种小按钮：字号与普通文本一致，几乎不留内边距
        style.configure("Mini.TButton", font=("Microsoft YaHei UI", 10), padding=(3, 0))


    # -------------------------------------------------- 界面
    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        # ============ 顶部：两个文件夹选择器 ============
        top = ttk.LabelFrame(outer, text=" 路径选择（可拖入 / 手输 / 浏览） ", padding=8)
        top.pack(fill="x")
        PathRow(top, "源目录", self.vars["source"], "dir", label_width=9).pack(fill="x", pady=2)
        PathRow(top, "输出目录", self.vars["target"], "dir", label_width=9).pack(fill="x", pady=2)
        hint_row = ttk.Frame(top)
        hint_row.pack(fill="x", pady=(4, 0))
        ttk.Label(
            hint_row, foreground="#666",
            text="源目录 = 含 ogg 与 sub_zh.csv 的文件夹　|　输出目录 = srt 输出根目录"
                 "（实际写入：输出目录 \\ 源文件夹名 \\ 文件.srt）",
        ).pack(side="left")
        # 常用工具调用：字幕类常用按钮在右侧「常用」栏，这里给出对照
        ttk.Label(
            hint_row, foreground="#666",
            text="　常用工具调用：见右侧「常用」栏"
                 "（一键版 / 拆分 / 汉化 / 去括号 / 去标号 / 导出VO / 词表替换 / 检查错误）",
        ).pack(side="left")

        # ============ 中部：左 = 工具栏（宽），右 = 常用（窄） ============
        mid = ttk.Frame(outer)
        mid.pack(fill="both", expand=True, pady=(8, 0))
        mid.columnconfigure(0, weight=1, minsize=430)   # 工具栏：固定占左边，吃掉剩余宽度
        mid.columnconfigure(1, weight=0, minsize=330)   # 常用：固定窄栏（330px）

        self._build_side(mid)      # 工具栏 → 左
        self._build_main(mid)      # 常用   → 右

        # ============ 底部：日志 ============
        logf = ttk.LabelFrame(outer, text=" 日志 ", padding=6)
        logf.pack(fill="both", expand=True, pady=(8, 0))

        bar = ttk.Frame(logf)
        bar.pack(fill="x", pady=(0, 4))
        ttk.Button(bar, text="清空日志", width=10, command=self.clear_log).pack(side="left")
        # 「紧急中止」：紧跟在「清空日志」后面、「就绪」左边。
        # 要点两下，第一下只把按钮变成「再次确定」，第二下才真中止
        self.abort_armed = False
        self.abort_btn = ttk.Button(bar, text="紧急中止", width=10, command=self.t_abort)
        self.abort_btn.pack(side="left", padx=(6, 0))
        self.status = ttk.Label(bar, text="就绪", foreground="#0a6")
        self.status.pack(side="left", padx=12)

        wrap = ttk.Frame(logf)
        wrap.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            wrap, height=12, wrap="word", state="disabled",
            font=("Consolas", 9), background="#1e1e1e", foreground="#d4d4d4",
            insertbackground="#d4d4d4",
        )
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _build_main(self, parent):
        left = ttk.LabelFrame(parent, text=" 常用 ", padding=10)
        left.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # C 位：一键版
        # ttk.Button 不支持 justify，居中只能靠补空格：第一行比第二行窄，左右各补 2 个全角空格近似居中
        self._add_button(
            left, "\u3000\u3000★  一 键 版\u3000\u3000\n自动排障、导入汉化",
            self.t_oneclick, style="Hero.TButton",
        ).pack(fill="x", pady=(0, 6))

        # 次位：ZH 的 csv 拆分
        self._add_button(
            left, "ZH 的 csv 拆分（sub_zh.csv → 多个 srt）",
            self.t_split, style="Main.TButton",
        ).pack(fill="x", pady=(0, 12))

        ttk.Separator(left, orient="horizontal").pack(fill="x", pady=(0, 10))

        # 常用栏被固定成窄栏（330px），按钮排成两列
        grid = ttk.Frame(left)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")

        pairs = [
            ("汉化字幕", self.t_update),
            ("去除括号", self.t_delete_bracket),
            ("去除标号", self.t_remove_ln),
            ("导出VO文本", self.t_export_vo),
            ("词表替换", self.t_replace_dict),
            ("检查错误", self.t_check_content),
        ]
        for i, (name, cmd) in enumerate(pairs):
            b = self._add_button(grid, name, cmd, style="Main.TButton")
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=3)

        ttk.Label(
            left, foreground="#666", justify="left", wraplength=290,
            text="提示：一键版按「查找缺失→汉化→去括号→去标号→提取未译」顺序执行。",
        ).pack(anchor="w", pady=(10, 0))

    def _build_side(self, parent):
        right = ttk.LabelFrame(parent, text=" 工具栏 ", padding=6)
        right.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        canvas = tk.Canvas(right, highlightthickness=0, width=300)
        vsb = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: self._on_tool_wheel(e, canvas))

        # --- 配音工具 ---
        sec_dub = CollapsibleSection(inner, "▸ 配音工具", expanded=True)
        sec_dub.pack(fill="x")
        dbody = sec_dub.body

        # 「模型」副栏：置顶、默认折叠，只承载「模型」下拉
        sec_model = CollapsibleSection(dbody, "▸ 模型", expanded=False)
        sec_model.pack(fill="x")
        mrow = ttk.Frame(sec_model.body)
        mrow.pack(fill="x", pady=(4, 1))
        ttk.Label(mrow, text="模型", width=6, anchor="e").pack(side="left")
        self.model_cb = ttk.Combobox(
            mrow, textvariable=self.vars["dub_model"], values=MODELS, state="readonly")
        self.model_cb.pack(side="left", fill="x", expand=True, padx=4)
        self.model_cb.bind("<<ComboboxSelected>>", lambda e: self._on_model_change())

        # 音色行：「原声」直接播放该音色的参考音频；「试听」用该音色合成一句话后播放
        vrow = ttk.Frame(dbody)
        vrow.pack(fill="x", pady=(6, 1))
        ttk.Label(vrow, text="音色", width=6, anchor="e").pack(side="left")
        self.voice_cb = ttk.Combobox(
            vrow, textvariable=self.vars["dub_voice"], values=[], state="readonly")
        self.voice_cb.pack(side="left", fill="x", expand=True, padx=4)
        self._add_button(vrow, "原声", self.t_play_voice,
                         style="Mini.TButton").pack(side="left")
        self._add_button(vrow, "试听", self.t_preview,
                         style="Mini.TButton").pack(side="left", padx=(3, 0))

        # 「配音文件夹」有两种形态：默认 = 可填/可拖的路径框；勾「列表视图」后换成文件夹下拉
        in_holder = ttk.Frame(dbody)
        in_holder.pack(fill="x", pady=1)
        self.dub_in_row = PathRow(in_holder, "配音文件夹", self.vars["dub_in"], "dir",
                                  label_width=13)
        self.dub_in_row.pack(fill="x")
        self.pending_row = ttk.Frame(in_holder)
        ttk.Label(self.pending_row, text="配音文件夹", width=13, anchor="e").pack(side="left")
        self.pending_pick = tk.StringVar()
        self.pending_items: list[str] = []            # 当前下拉里的文件夹名
        self.pending_combo = ttk.Combobox(self.pending_row, textvariable=self.pending_pick,
                                          values=[], state="readonly")
        self.pending_combo.pack(side="left", fill="x", expand=True, padx=4)
        self.pending_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_pending_pick())
        self._add_button(self.pending_row, "刷新", self._refresh_pending,
                         style="Mini.TButton").pack(side="left")
        # 列表视图：勾选后「配音文件夹」由路径框换成「待配音目录」下的文件夹下拉
        ttk.Checkbutton(dbody, text="列表视图（配音文件夹改为下拉选择）",
                        variable=self.list_view).pack(anchor="w")

        # 「情绪」副栏：情感强度 + 按原音色参考 + 八向向量，统一收在这一层（仅 IndexTTS 有效）
        sec_emo = CollapsibleSection(
            dbody, "▸ 情绪（仅 IndexTTS 有效）", expanded=True, enable_var=self.emo_on)
        sec_emo.pack(fill="x")
        # 按原音色参考：在每个 srt 所在目录找同名音频当情感参考；找不到则回落用八向向量
        ttk.Checkbutton(sec_emo.body, text="按原音色参考（同名原音频当情感参考）",
                        variable=self.emo_ref).pack(anchor="w")
        erow = ttk.Frame(sec_emo.body)
        erow.pack(fill="x", pady=2)
        ttk.Label(erow, text="情感强度", anchor="e").pack(side="left")
        ttk.Scale(erow, from_=0.0, to=1.0, variable=self.emo_var,
                  orient="horizontal").pack(side="left", fill="x", expand=True, padx=4)
        self.emo_lbl = ttk.Label(erow, width=5)
        self.emo_lbl.pack(side="left")
        self.emo_var.trace_add("write", lambda *_: self._sync_emo_label())
        self._sync_emo_label()
        ttk.Label(
            sec_emo.body, foreground="#666", justify="left", wraplength=280,
            text="0 = 完全保留音色自带情绪；1 = 完全套用下方「八向」给出的情感向量。",
        ).pack(anchor="w")
        # 八向：8 个滑块依次对应 高兴/愤怒/悲伤/恐惧/反感/低落/惊讶/自然
        ttk.Checkbutton(sec_emo.body, text="八向（用情感向量给定情绪）",
                        variable=self.emo8_on).pack(anchor="w", pady=(4, 0))
        grid8 = ttk.Frame(sec_emo.body)
        grid8.pack(fill="x", pady=2)
        for col in (1, 3):
            grid8.columnconfigure(col, weight=1, minsize=60)
        for i, (label, key) in enumerate(EMO8_DIMS):
            row, col = i // 2, (i % 2) * 2          # 每行两个滑块，共 4 行
            ttk.Label(grid8, text=label, width=4, anchor="e").grid(
                row=row, column=col, sticky="e", pady=1)
            ttk.Scale(grid8, from_=0.0, to=1.0, variable=self.emo8_vars[key],
                      orient="horizontal").grid(
                row=row, column=col + 1, sticky="ew", padx=(2, 8))
        ttk.Label(
            sec_emo.body, foreground="#666", justify="left", wraplength=280,
            text="按 高兴/愤怒/悲伤/恐惧/反感/低落/惊讶/自然 顺序送给模型；\n"
                 "实际值 = 滑块 × 上面的「情感强度」。取消勾选 = 不用八向。",
        ).pack(anchor="w")

        # 「单独选音频」：只配选中的那几个 OGG/WAV，勾选后覆盖「配音文件夹」
        ttk.Checkbutton(dbody, text="单独选音频（OGG/WAV，勾选后覆盖「配音文件夹」）",
                        variable=self.pick_on).pack(anchor="w", pady=(6, 0))
        prow = ttk.Frame(dbody)
        prow.pack(fill="x", pady=1)
        ttk.Label(prow, width=13, anchor="e", text="单独选音频").pack(side="left")
        self.pick_lbl = ttk.Label(prow, foreground="#999", anchor="w")
        self.pick_lbl.pack(side="left", fill="x", expand=True, padx=4)
        self._add_button(prow, "选择文件", self.t_pick_files, style="Mini.TButton").pack(side="left")
        self._add_button(prow, "清空", self.t_pick_clear, style="Mini.TButton").pack(
            side="left", padx=(4, 0))
        self._sync_pick_label()

        # 状态指示灯 + 常驻模式/关闭TTS
        # 左 = 指示灯（上圆点、下三行状态文字）；右 = 常驻模式勾选框 + 关闭TTS 按钮
        srow = ttk.Frame(dbody)
        srow.pack(fill="x", pady=(6, 0))
        lcol = ttk.Frame(srow)
        lcol.pack(side="left", anchor="nw")
        self.led = tk.Canvas(lcol, width=12, height=12, highlightthickness=0)
        self.led.pack(anchor="w")
        self.led_dot = self.led.create_oval(1, 1, 11, 11, fill=LED_OK, outline="")
        self.led_txt = ttk.Label(lcol, foreground="#666", justify="left")
        self.led_txt.pack(anchor="w", pady=(3, 0))
        ctl = ttk.Frame(srow)
        ctl.pack(side="left", anchor="nw", padx=(14, 0))
        ttk.Checkbutton(ctl, text="常驻模式（默认开启）",
                        variable=self.auto_resident).pack(anchor="w")
        self._add_button(ctl, "关闭TTS", self.t_tts_stop,
                         style="Mini.TButton").pack(anchor="w", pady=(4, 0))
        # 情绪/常驻一变，指示灯立刻跟着变（刷控件始终在主线程）
        self.emo_var.trace_add("write", lambda *_: self._update_led())
        self.emo_on.trace_add("write", lambda *_: self._update_led())
        self.auto_resident.trace_add("write", lambda *_: self._update_led())

        brow = ttk.Frame(dbody)
        brow.pack(fill="x", pady=(6, 2))
        self._add_button(brow, "开始", self.t_dub_start, style="Main.TButton").pack(
            side="left", fill="x", expand=True)

        ttk.Label(
            dbody, foreground="#666", justify="left", wraplength=290,
            text="产物：输出路径\\dub\\{srt,wav,ogg}\\<角色名>\\\n"
                 "配音进程后台隐藏运行（最小化，不弹窗）",
        ).pack(anchor="w", pady=(2, 0))

        # --- 目录设置 ---
        self.sec_dirs = CollapsibleSection(inner, "▸ 目录设置（地址栏）", expanded=False)
        sec_dirs = self.sec_dirs
        sec_dirs.pack(fill="x")

        # 「简略模式」：勾选后地址栏只留「工作区目录 + TTS 路径」（默认开启，方便新用户上手）
        ttk.Checkbutton(sec_dirs.body, text="简略模式（只需配置工作区与 TTS 路径）",
                        variable=self.simple_mode).pack(anchor="w", pady=(0, 4))

        # 工作区目录：独立一行；下面几个子路径都由它推导，所以不再单独列出
        ws_row = PathRow(sec_dirs.body, "工作区目录", self.vars["workspace"], "dir",
                         label_width=13)
        ws_row.pack(fill="x", pady=1)
        # 回车 / 焦点离开输入框 = 明确设定完了，这时无条件把目录结构建出来
        for seq in ("<Return>", "<FocusOut>"):
            ws_row.entry.bind(seq, lambda _e: self._make_workspace_dirs(force=True))
        ttk.Label(
            sec_dirs.body, foreground="#666", justify="left",
            text="工作区里自动创建并推导：source / srt / voices / output / votxt / dict.txt / ffmpeg.exe",
        ).pack(anchor="w", padx=(60, 0))

        # 简略模式下被隐藏的两块（放成独立容器，隐藏时整块撤下、顺序不变；里面的值照常保留）
        self._sbox_pre = ttk.Frame(sec_dirs.body)    # 音色目录 / 输出路径 / 音色顺序表
        self._sbox_pre.pack(fill="x")
        for label, key, kind in (("音色目录", "dub_voice_dir", "dir"),
                                 ("输出路径", "dub_out", "dir"),
                                 ("音色顺序表", "dub_voice_order", "file")):
            r = PathRow(self._sbox_pre, label, self.vars[key], kind, label_width=13)
            r.pack(fill="x", pady=1)
            if key == "dub_voice_dir":               # 改音色目录 = 重扫音色清单
                for seq in ("<Return>", "<FocusOut>"):
                    r.entry.bind(seq, lambda _e: self._refresh_voices())

        # 简略模式下保留：TTS 路径
        self._tts_rows = []
        for label, key, kind in (("GPT-SoVITS 目录", "gptsovits", "dir"),
                                 ("IndexTTS 根目录", "itts_root", "dir")):
            r = PathRow(sec_dirs.body, label, self.vars[key], kind, label_width=13)
            r.pack(fill="x", pady=1)
            self._tts_rows.append(r)

        self._sbox_post = ttk.Frame(sec_dirs.body)   # 待配音目录 / 手机推送主题
        self._sbox_post.pack(fill="x")
        PathRow(self._sbox_post, "待配音目录", self.vars["pending_dir"], "dir",
                label_width=13).pack(fill="x", pady=1)
        # 手机推送主题（纯文本，非路径）：留空 = 只响本地提示音、不推手机
        nrow = ttk.Frame(self._sbox_post)
        nrow.pack(fill="x", pady=1)
        ttk.Label(nrow, text="手机推送主题", width=13, anchor="e").pack(side="left")
        ttk.Entry(nrow, textvariable=self.vars["ntfy_topic"]).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Label(
            self._sbox_post, foreground="#666", justify="left", wraplength=280,
            text="手机推送主题 = ntfy.sh 的频道名（手机 App 里订阅同名频道）。留空 = 不推手机。",
        ).pack(anchor="w", padx=(60, 0))

        # --- 版权 / 关于（工具栏最底部） ---
        sec_about = CollapsibleSection(inner, "▸ 版权 / 关于", expanded=True)
        sec_about.pack(fill="x")
        cbody = sec_about.body

        ttk.Label(cbody, text=f"{APP_TITLE}  v{APP_VERSION}",
                  font=("", 10, "bold")).pack(anchor="w", pady=(2, 0))

        # 发布者署名 + 可点击的 B 站主页链接
        arow = ttk.Frame(cbody)
        arow.pack(anchor="w", pady=(3, 0))
        ttk.Label(arow, text="本软件 by ").pack(side="left")
        lk = ttk.Label(arow, text="ENOCH0114", foreground="#1a73e8",
                       cursor="hand2", font=("", 9, "underline"))
        lk.pack(side="left")
        lk.bind("<Button-1>", lambda _e: App._open_home())
        lurl = ttk.Label(cbody, foreground="#1a73e8", cursor="hand2", font=("", 8),
                         text=HOME_URL)
        lurl.pack(anchor="w", padx=(58, 0))
        lurl.bind("<Button-1>", lambda _e: App._open_home())

        # 开源许可声明：本软件以 GPL-3.0 或更新版本发布（含许可全文链接）
        ttk.Label(cbody, justify="left", wraplength=300,
                  text="开源许可：GNU GPL v3 或任何更新版本"
        ).pack(anchor="w", pady=(5, 0))
        llic = ttk.Label(cbody, text="查看许可全文（gnu.org/licenses/gpl-3.0.html）",
                         foreground="#1a73e8", cursor="hand2", font=("", 8, "underline"))
        llic.pack(anchor="w")
        llic.bind("<Button-1>", lambda _e: webbrowser.open(
            "https://www.gnu.org/licenses/gpl-3.0.html"))

        ttk.Label(
            cbody, foreground="#666", justify="left", wraplength=300,
            text="Copyright (C) 2026 ENOCH0114\n"
                 "本软件为自由软件，依据 GNU GPL v3（或更新版本）发布：\n"
                 "可自由使用、修改与再分发，分发衍生作品须同样以 GPL 开源；\n"
                 "本软件按「现状」提供，不含任何担保。\n"
                 "生成的字幕与音频，版权归原作者所有，请勿用于商业用途。\n"
                 "设置保存在 %APPDATA%\\YYNTools\\config_lite.json。\n"
                 "如有问题或涉及侵权，请通过 B 站私信联系",
        ).pack(anchor="w", pady=(3, 2))

        # 第三方组件及许可（便于使用者核对合规性；ffmpeg 需自行下载）
        ttk.Label(cbody, foreground="#666", justify="left", wraplength=300,
                  text="本软件调用的第三方组件：\n"
                       "· IndexTTS 2.5（Apache-2.0）　· GPT-SoVITS（MIT）\n"
                       "· ffmpeg（LGPL/GPL，需自行下载）",
        ).pack(anchor="w", pady=(0, 0))
        lff = ttk.Label(cbody, text="ffmpeg 下载（兰州大学镜像，解压后放到工作区\\ffmpeg\\）",
                        foreground="#1a73e8", cursor="hand2", font=("", 8, "underline"))
        lff.pack(anchor="w", pady=(0, 4))
        lff.bind("<Button-1>", lambda _e: webbrowser.open(
            "https://mirror.lzu.edu.cn/jellyfin/ffmpeg/windows/8.x/8.1.3-1/win64/"))

        # 列表视图：勾/取消时切换「配音文件夹」的两种形态（此处调用，确保 sec_dirs 已建好）
        self.list_view.trace_add("write", lambda *_: self._on_list_view_toggle())
        self._on_list_view_toggle()
        # 简略模式：勾/取消时隐藏或恢复地址栏里非必需的几行（此处调用，确保控件已建好）
        self.simple_mode.trace_add("write", lambda *_: self._on_simple_toggle())
        self._on_simple_toggle()

        self._refresh_voices()
        self._update_led()
        self._poll_led()

    # -------------------------------------------------- 版权 / 关于
    @staticmethod
    def _open_home():
        """打开发布者的 B 站主页（版权页的点名）。"""
        try:
            webbrowser.open(HOME_URL)
        except Exception as e:
            print(f"[版权] 打不开浏览器：{e}\n{HOME_URL}")

    # -------------------------------------------------- 简略模式（地址栏精简）
    def _on_simple_toggle(self):
        """简略模式：只留「工作区目录 + TTS 路径」，其余地址行整块隐藏。

        只撤控件、不动值 —— 隐藏期间配置照常生效，取消勾选即原样恢复。
        """
        if not hasattr(self, "_sbox_pre"):
            return
        if self.simple_mode.get():
            self._sbox_pre.pack_forget()
            self._sbox_post.pack_forget()
        else:
            # 按原位插回：前置块放回第一行 TTS 之前，后置块本就在末尾
            self._sbox_pre.pack(fill="x", before=self._tts_rows[0])
            self._sbox_post.pack(fill="x")

    # -------------------------------------------------- 列表视图（文件夹下拉）
    def _on_list_view_toggle(self):
        """勾/取消「列表视图」：在「配音文件夹」路径框与「待配音目录」下拉之间切换。"""
        if not hasattr(self, "pending_row"):
            return
        if self.list_view.get():
            self.dub_in_row.pack_forget()
            self.pending_row.pack(fill="x")
            if hasattr(self, "sec_dirs"):              # 待配音目录在目录设置里，展开让人看得见
                self.sec_dirs.expanded.set(True)
                self.sec_dirs._toggle()
            self._refresh_pending()
        else:
            self.pending_row.pack_forget()
            self.dub_in_row.pack(fill="x")

    def _refresh_pending(self):
        """列出「待配音目录」下的子文件夹（只显示文件夹名）。"""
        root = self.vars["pending_dir"].get().strip().strip('"')
        if not root or not os.path.isdir(root):
            self.pending_items = []
            self.pending_combo.configure(values=[])
            self.pending_pick.set("")
            print(f"[列表视图] 待配音目录未设置或无效：{root or '（空）'}")
            return
        self.pending_items = sorted(
            d for d in os.listdir(root)
            if os.path.isdir(os.path.join(root, d)))
        self.pending_combo.configure(values=self.pending_items)
        print(f"[列表视图] 读到 {len(self.pending_items)} 个文件夹：{root}")

    def _on_pending_pick(self):
        """选中某项 → 把「配音文件夹」设为它在「待配音目录」下的完整路径。"""
        name = self.pending_pick.get().strip()
        root = self.vars["pending_dir"].get().strip().strip('"')
        if name and root:
            path = os.path.join(root, name)
            self.vars["dub_in"].set(path)
            print(f"[列表视图] 配音文件夹 → {path}")

    # -------------------------------------------------- 配音工具：音色列表
    def _model(self) -> str:
        m = self.vars["dub_model"].get().strip()
        return m if m in MODELS else MODEL_ITTS

    def _voice_dir_default(self, model: str) -> str:
        if model == MODEL_GPT:
            gpt = self.vars["gptsovits"].get().strip().strip('"')
            return os.path.join(gpt, "wavs") if gpt else ""
        ws = self.vars["workspace"].get().strip().strip('"')
        return os.path.join(ws, "voices") if ws else ""

    def _sync_emo_label(self):
        self.emo_lbl.configure(text=f"{self.emo_var.get():.2f}")

    def _update_led(self):
        """刷新状态指示灯：圆点取最严重的一项，文字三行列出「情绪 / 常驻 / 上批」。

        红灯（需注意）：情绪 = 0 或 < 0.5、常驻勾了但服务没在跑、上批有无参考跳过或失败。
        橙灯（忙）：服务还在加载模型。灰灯：都正常。
        """
        if not hasattr(self, "led_dot"):
            return
        emo = self.emo_var.get()
        if not self.emo_on.get():
            emo_txt, emo_bad = "情绪 关（不做情感干预）", False
        elif emo <= 0:
            emo_txt, emo_bad = f"情绪 {emo:.2f}（未启用）", True
        elif emo < 0.5:
            emo_txt, emo_bad = f"情绪 {emo:.2f}（偏低）", True
        else:
            emo_txt, emo_bad = f"情绪 {emo:.2f}（正常）", False

        h = self._led_health
        if not self.auto_resident.get():
            res_txt, res_busy, res_bad = "常驻 关（本进程加载模型）", False, False
        elif h and h.get("state") == "ready":
            res_txt, res_busy, res_bad = "常驻 就绪", False, False
        elif h:
            res_txt, res_busy, res_bad = "常驻 加载中…", True, False
        else:
            res_txt, res_busy, res_bad = "常驻 未运行（下批自动启动）", False, True

        total, no_emo, failed = self._led_stat
        if total:
            last_txt = f"上批 无参考 {no_emo}/{total}、失败 {failed}"
            last_bad = bool(no_emo or failed)
        else:
            last_txt, last_bad = "上批 —", False

        color = LED_WARN if (emo_bad or res_bad or last_bad) else (LED_BUSY if res_busy else LED_OK)
        self.led.itemconfigure(self.led_dot, fill=color)
        self.led_txt.configure(text=f"{emo_txt}\n{res_txt}\n{last_txt}")

    def _poll_led(self):
        """每 5 秒刷一次指示灯：探测放后台线程（只写变量），刷控件始终在主线程。"""
        def work():
            self._led_health = self._resident_health(timeout=0.8)
        threading.Thread(target=work, daemon=True).start()
        self._update_led()
        self.root.after(5000, self._poll_led)

    def _confirm_low_emo(self, weight: float, where: str = "配音工具") -> bool:
        """情感强度偏低（= 指示灯变红）时的二次确认，避免低情绪下白跑一整批。"""
        if weight >= 0.5:
            return True
        if weight <= 0:
            detail = "当前「情感强度」= 0：完全不加情感，只用音色自带的情绪。"
        else:
            detail = f"当前「情感强度」= {weight:.2f}（低于 0.5）：情感参考只有很小的影响。"
        return messagebox.askokcancel(
            "情感强度偏低",
            f"{detail}\n\n{where}将在低情绪下进行。\n确定要继续吗？",
        )

    @staticmethod
    def _on_tool_wheel(event, canvas):
        """只有指针停在「工具栏」区域内时才滚动工具栏。

        按指针下的控件反查：不在 canvas（含其子控件）里就不滚；指针停在下拉框上时
        直接放行，交给下拉框自己处理滚轮。
        """
        try:
            w = canvas.winfo_containing(event.x_root, event.y_root)
        except Exception:
            return
        start = w
        while w is not None:
            if w is canvas:
                if isinstance(start, ttk.Combobox):
                    return          # 下拉框上的滚轮留给它自己（切选项），不滚工具栏
                canvas.yview_scroll(int(-event.delta / 120), "units")
                return
            w = getattr(w, "master", None)

    def _on_model_change(self):
        """切模型：音色目录自动换成该模型的默认值（仅当当前值还是「默认值/空」时才覆盖）。"""
        model = self._model()
        cur = self.vars["dub_voice_dir"].get().strip()
        defaults = {self._voice_dir_default(MODEL_ITTS), self._voice_dir_default(MODEL_GPT)}
        if not cur or cur in defaults:
            self.vars["dub_voice_dir"].set(self._voice_dir_default(model))
        self._refresh_voices()

    def _refresh_voices(self):
        """重扫音色清单：ITTS 扫 wav 目录；GPT 只认 temp.txt 里有参考文本的音色。"""
        model = self._model()
        vdir = self.vars["dub_voice_dir"].get().strip()
        names: list[str] = []
        self._voice_paths = {}
        self._gpt_ref_text = {}
        self._gpt_ref_lang = {}

        if model == MODEL_GPT:
            temp = Path(self.vars["gptsovits"].get().strip()) / "temp.txt"
            if temp.is_file():
                for ln in temp.read_text(encoding="utf-8-sig").splitlines():
                    ln = ln.strip()
                    if not ln or ln.startswith("#"):
                        continue
                    parts = ln.split("#")
                    if len(parts) < 2:
                        continue
                    rel, text = parts[0].strip(), parts[1].strip()
                    if not rel or not text:
                        continue                      # 无参考文本的音色一律不列
                    lang = parts[2].strip() if len(parts) > 2 else ""
                    full = os.path.normpath(os.path.join(
                        self.vars["gptsovits"].get().strip(), rel.replace("/", os.sep)))
                    if not os.path.isfile(full):
                        continue
                    name = self._voice_display(full, vdir)
                    names.append(name)
                    self._voice_paths[name] = full
                    self._gpt_ref_text[name] = text
                    self._gpt_ref_lang[name] = lang
        else:
            base = Path(vdir) if vdir else None
            if base and base.is_dir():
                for p in sorted(base.rglob("*.wav")):
                    name = self._voice_display(str(p), vdir)
                    names.append(name)
                    self._voice_paths[name] = str(p)

        names.sort(key=self._voice_sort_key(self._voice_order()))

        self.voice_cb.configure(values=names)
        cb = getattr(self, "auto_voice_cb", None)     # 兼容：界面上没有该控件时直接跳过
        if cb is not None:
            cb.configure(values=names)
        if names and self.vars["dub_voice"].get() not in names:
            self.vars["dub_voice"].set(names[0])

    def _voice_order(self) -> dict:
        """读「音色顺序表」（与 temp.txt 同格式），返回 {小写文件名主干: 序号}。"""
        p = Path(self.vars["dub_voice_order"].get().strip())
        order: dict = {}
        if not p.is_file():
            return order
        try:
            lines = p.read_text(encoding="utf-8-sig").splitlines()
        except Exception:
            return order
        for ln in lines:
            ln = ln.split("#", 1)[0].strip()
            if not ln:
                continue
            stem = Path(ln.replace("/", os.sep)).stem.lower()
            if stem and stem not in order:
                order[stem] = len(order)
        return order

    @staticmethod
    def _voice_sort_key(order: dict):
        """排序优先级：PD 组永远最前 → 顺序表里的次序 → 未列到的按目录原顺序排最后。"""
        last = len(order)

        def key(name: str):
            flat = name.replace("\\", "/")
            in_pd = 0 if flat.split("/")[0].lower() == "pd" else 1
            return (in_pd, order.get(Path(flat).stem.lower(), last))

        return key

    @staticmethod
    def _voice_display(full: str, vdir: str) -> str:
        try:
            rel = os.path.relpath(full, vdir)
            if not rel.startswith(".."):
                return rel
        except Exception:
            pass
        return full

    def _voice_file(self) -> str:
        name = self.vars["dub_voice"].get().strip()
        if not name:
            return ""
        return self._voice_paths.get(name) or os.path.join(
            self.vars["dub_voice_dir"].get().strip(), name)

    # -------------------------------------------------- 配音工具：解释器 / 脚本
    def _dub_work_dir(self) -> Path:
        """返回放着 dub_itts.py / dub_gpt.py / tts_resident.py 的目录（打包后自动释放到 APPDATA）。"""
        local = Path(__file__).resolve().parent / "scripts"
        if not getattr(sys, "frozen", False):
            return local
        src = Path(getattr(sys, "_MEIPASS", str(local))) / "dub_scripts"
        dst = Path(os.environ.get("APPDATA", str(Path.home()))) / "YYNTools" / "dub_scripts_lite"
        dst.mkdir(parents=True, exist_ok=True)
        for n in DUB_FILES:
            s, t = src / n, dst / n
            try:
                if s.is_file() and (not t.is_file() or t.stat().st_size != s.stat().st_size):
                    shutil.copy2(s, t)
            except Exception:
                pass
        return dst

    def _run_dub(self, script_name: str, argv: list, model: str = None) -> int:
        """用对应模型自带的解释器在后台隐藏运行配音脚本，并把输出实时转发到日志。

        model 留空 = 用界面上选中的模型；「自动流程」固定传 MODEL_ITTS。
        """
        model = model or self._model()
        work = self._dub_work_dir()
        script = work / script_name
        if model == MODEL_GPT:
            py = Path(self.vars["gptsovits"].get().strip()) / "runtime" / "python.exe"
            cwd = self.vars["gptsovits"].get().strip()
        else:
            py = Path(self.vars["itts_root"].get().strip()) / ".venv" / "Scripts" / "python.exe"
            cwd = self.vars["itts_root"].get().strip()

        for p, what in ((py, "解释器"), (script, "脚本")):
            if not Path(p).is_file():
                print(f"[错误] 找不到{what}：{p}")
                return 1

        print(f"[模型] {model}\n[解释器] {py}\n[脚本] {script}\n")
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["YYN_NTFY_TOPIC"] = self.vars["ntfy_topic"].get().strip()   # 留空 = 不推手机
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.Popen(
            [str(py), "-u", str(script)] + [str(a) for a in argv],
            cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=flags,
        )
        self.procs.append(proc)
        # 顺手统计本批「无参考跳过 / 失败」，供状态指示灯显示（刷控件交给 _poll_led）
        total = no_emo = failed = 0
        self._led_stat = (0, 0, 0)
        try:
            for line in proc.stdout:
                if self._aborted():                  # 已中止：立刻断流，不再转发/统计
                    break
                print(line.rstrip("\n"))
                if "本批" in line and "个文件" in line:
                    try:
                        total = int(line.split("本批")[1].split("个文件")[0].strip())
                        no_emo = failed = 0
                    except ValueError:
                        pass
                elif "找不到同名情感音频" in line:
                    no_emo += 1
                elif "] FAIL " in line:
                    failed += 1
                self._led_stat = (total, no_emo, failed)
            rc = proc.wait()
            self._check_abort()                        # 已中止：不再往下走（转 OGG / 下一个文件夹）
            return rc
        finally:
            self._led_stat = (total, no_emo, failed)
            if proc in self.procs:
                self.procs.remove(proc)

    def _dub_argv(self, srt_dir: str, out_root: str, sub_dir: str, emo_dir: str = "") -> list:
        argv = ["--srt-dir", srt_dir, "--voice", self._voice_file(),
                "--out", out_root, "--sub-dir", sub_dir]
        if self._model() == MODEL_GPT:
            cur = self.vars["dub_voice"].get().strip()
            argv += ["--root", self.vars["gptsovits"].get().strip(),
                     "--ref-lang", self._gpt_ref_lang.get(cur, ""),
                     "--ref-text", self._gpt_ref_text.get(cur, "")]
        else:
            argv += ["--model-dir", os.path.join(
                self.vars["itts_root"].get().strip(), "checkpoints")]
            # 勾选框关掉 = 用默认情感（不做干预）；滑块只是「开启情感」时才参与
            if self.emo8_on.get():
                vec = [self.emo8_vars[k].get() for _, k in EMO8_DIMS]
            else:
                vec = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
            argv += ["--emo-weight", f"{self.emo_var.get():.2f}" if self.emo_on.get() else "0",
                     "--emo-vector", ",".join(f"{x:.3f}" for x in vec)]
            # 按原音色参考：同名原音频当情感参考。内核里 emo_audio_prompt 与
            # emo_vector 互斥，但两个都传是有意的：找到同名音频时内核走音频、忽略向量；
            # 找不到时由 --emo-audio-fallback 回落用向量继续配。
            # emo_dir 非空 = 参考音频固定在该目录找（台本在别处，如「单独选音频」）；
            # 为空 = 就在每个 srt 自己所在目录找同名音频。
            if self.emo_on.get() and self.emo_ref.get():
                argv += (["--emo-audio-dir", emo_dir] if emo_dir else ["--emo-audio-same-dir"])
                argv += ["--emo-audio-fallback"]
        return argv

    def _wav2ogg_dir(self, in_dir: str, out_dir: str) -> int:
        ff = self.vars["ffmpeg"].get().strip()
        return self._call_patched(
            wav_to_ogg, ["--input-dir", in_dir, "--output-dir", out_dir], {"FFMPEG_PATH": ff})


    @staticmethod
    def _role_of(path: str) -> str:
        return os.path.basename(os.path.normpath(path)) if path else ""

    def _dub_paths(self):
        root = self.vars["dub_out"].get().strip().strip('"')
        return root, os.path.join(root, "dub"), os.path.join(root, "script")

    # -------------------------------------------------- 配音工具：任务

    def t_pick_files(self):
        """「单独选音频」：多选要配音的原音频 OGG/WAV（可跨目录）；勾选框勾上才生效。"""
        init = self.vars["dub_in"].get().strip().strip('"')
        if not os.path.isdir(init):
            init = YYN_ROOT
        chosen = filedialog.askopenfilenames(
            title="选择要配音的原音频（可多选）", initialdir=init,
            filetypes=[("音频文件", "*.ogg *.wav *.mp3 *.flac"),
                       ("OGG", "*.ogg"), ("WAV", "*.wav"), ("全部文件", "*.*")])
        if not chosen:
            return
        self.pick_files = list(chosen)
        self.pick_on.set(True)                     # 选完自动勾上，免得忘了勾等于没选
        self._sync_pick_label()

    def t_pick_clear(self):
        """清空「单独选文件」的选择（勾选框状态不动）。"""
        self.pick_files = []
        self._sync_pick_label()

    def _sync_pick_label(self):
        """把所选文件回显到标签，并同步进 vars 以便随配置落盘。"""
        if not hasattr(self, "pick_lbl"):
            return
        self.vars["dub_pick_files"].set("|".join(self.pick_files))
        n = len(self.pick_files)
        if not n:
            self.pick_lbl.configure(text="（未选择，勾选后会用系统文件框多选 OGG/WAV）",
                                    foreground="#999")
        else:
            more = f" 等 {n} 个" if n > 1 else ""
            self.pick_lbl.configure(text=f"{os.path.basename(self.pick_files[0])}{more}",
                                    foreground="#333")

    def _write_pick_list(self, files: list) -> str:
        """把清单写成临时文件（每行一个），供 csv_split_srt.py / dub_itts.py --only-list。"""
        try:
            d = Path(os.environ.get("TEMP", str(Path.home()))) / "YYNTools"
            d.mkdir(parents=True, exist_ok=True)
            f = d / "dub_pick_list.txt"
            f.write_text("\n".join(files), encoding="utf-8")
            return str(f)
        except Exception as e:
            print(f"[警告] 写「单独选音频」清单失败：{type(e).__name__}: {e}")
            return ""

    def t_dub_start(self):
        srt_dir = self.vars["dub_in"].get().strip().strip('"')
        # 「单独选音频」勾选且已选 → 只配选中的那几个（走「自动流程」那一套）
        picked = list(self.pick_files) if (self.pick_on.get() and self.pick_files) else []
        src_csv = ""            # 「单独选音频」用：所选音频所在目录的 sub_zh.csv
        emo_dir = ""            # 「单独选音频」用：情感参考音频（=所选音频）所在目录
        if picked:
            missing = [p for p in picked if not os.path.isfile(p)]
            if missing:
                messagebox.showwarning(
                    "所选文件不存在",
                    f"有 {len(missing)} 个文件已不存在（被移动或改名）：\n{missing[0]}")
                return
            if self._model() == MODEL_GPT:
                messagebox.showwarning("暂不支持",
                                       "「单独选音频」目前只在 IndexTTS 下生效。\n请切换模型，或取消该勾选。")
                return
            parents = sorted({os.path.dirname(p) for p in picked})
            if len(parents) > 1:
                messagebox.showwarning(
                    "所选文件跨目录",
                    f"所选文件分布在 {len(parents)} 个目录。\n"
                    "台本与产物会统一按第一个目录的角色名存放：\n"
                    f"{os.path.basename(parents[0])}")
            srt_dir, emo_dir = parents[0], parents[0]
            src_csv = os.path.join(srt_dir, "sub_zh.csv")
            if not os.path.isfile(src_csv):
                messagebox.showwarning(
                    "找不到 CSV",
                    "「单独选音频」需要同目录下的 sub_zh.csv（台词表）：\n"
                    f"{src_csv}\n\n请把所选音频放在含 sub_zh.csv 的目录里。")
                return
        elif not srt_dir or not os.path.isdir(srt_dir):
            messagebox.showwarning("缺少配音文件夹", "请先选择「配音文件夹」（待配音的 srt 目录）。")
            return
        if not self._voice_file():
            messagebox.showwarning("缺少音色", "请先选择「音色」。")
            return
        root, dub_root, script_root = self._dub_paths()
        if not root:
            messagebox.showwarning("缺少输出路径", "请先选择「输出路径」。")
            return
        role = self._role_of(srt_dir)
        script = "dub_gpt.py" if self._model() == MODEL_GPT else "dub_itts.py"
        book_dir = os.path.join(script_root, role)      # 台本目录（按角色名分子目录）
        only_list = ""
        if picked:
            # 只拆选中的这几个 Key（音频文件名主干 = sub_zh.csv 的 Key）
            only_list = self._write_pick_list(
                [os.path.splitext(os.path.basename(p))[0] for p in picked])
        # 台本作为源：单独选音频时源是「台本目录」，否则就是「配音文件夹」本身
        argv = self._dub_argv(book_dir if picked else srt_dir, dub_root, role,
                              emo_dir=emo_dir)

        def work():
            run_argv = list(argv)
            # 常驻模式（仅 IndexTTS）：复用常驻 TTS 服务，模型只加载一次；不勾 = 子进程自己加载
            if self._model() == MODEL_ITTS and self.auto_resident.get():
                print("---- 准备 TTS 服务（模型只加载一次） ----")
                if not self._resident_start():
                    print("[中止] TTS 服务不可用，本次配音取消。")
                    return
                run_argv += ["--api-url", self._resident_url()]
            elif self._model() == MODEL_ITTS and self._resident_health():
                print("---- 未勾选常驻模式：先关闭在跑的 TTS 服务（避免两边抢显存） ----")
                self.t_tts_stop()
            if picked:
                print("---- 拆分 srt（sub_zh.csv → 台本，仅所选） ----")
                cs = ["--csv", src_csv, "--out", book_dir, "--ext", "srt"]
                if only_list:
                    cs += ["--only-list", only_list]
                self._call(csv_split_srt, cs)
                print("\n---- 去除括号 ----")
                self._call(delete_by_content, ["--dir", book_dir])
                print("\n---- 配音（同名音频作情感参考） ----")
            if self._run_dub(script, run_argv) != 0:
                print("[中止] 配音未成功，跳过 ogg 转换")
                return
            print("\n---- WAV 转 OGG ----")
            self._wav2ogg_dir(os.path.join(dub_root, "wav", role),
                              os.path.join(dub_root, "ogg", role))
            if self._model() == MODEL_ITTS and self.auto_resident.get():
                print("\n[常驻] 已勾选常驻模式：服务保持运行，下一批可立即开始；要释放显存点「关闭TTS」。")

        # 情感强度偏低（指示灯变红）→ 先确认，免得白跑一整批。
        # 「情感」勾选框关掉时本就不加情感（--emo-weight 0），那是明确选择，不再拦。
        if self.emo_on.get() and not self._confirm_low_emo(self.emo_var.get(), "配音工具"):
            return
        self._run(f"配音（{self._model()}）", work)


    # -------------------------------------------------- 常驻 TTS 服务
    def _resident_url(self) -> str:
        """常驻服务地址；端口优先读登记文件（服务启动后会写进去）。"""
        port = RESIDENT_PORT
        try:
            if RESIDENT_MARKER.is_file():
                port = int(json.loads(RESIDENT_MARKER.read_text(encoding="utf-8")).get("port") or port)
        except Exception:
            pass
        return f"http://127.0.0.1:{port}"

    def _resident_health(self, timeout: float = 2.0):
        """探测常驻服务：活着返回 /health 的内容，否则 None。"""
        try:
            with urllib.request.urlopen(self._resident_url() + "/health", timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None

    def _pump_lines(self, proc):
        """把常驻服务的输出实时搬进日志窗口（模型加载进度也能看到）。"""
        try:
            for line in proc.stdout:
                self.out_q.put(line if line.endswith("\n") else line + "\n")
        except Exception:
            pass

    def _resident_start(self) -> bool:
        """确保常驻服务可用；没在跑就启动它，并等模型加载完。"""
        h = self._resident_health()
        if h and h.get("state") == "ready":
            print("[常驻] 服务已在运行，直接复用（不再加载模型）")
            return True

        proc = None
        if h:
            print("[常驻] 服务正在启动中，等它加载完…")
        else:
            work = self._dub_work_dir()
            script = work / "tts_resident.py"
            root = self.vars["itts_root"].get().strip()
            py = Path(root) / ".venv" / "Scripts" / "python.exe"
            model_dir = os.path.join(root, "checkpoints")
            for p, what in ((py, "解释器"), (script, "常驻服务脚本")):
                if not Path(p).is_file():
                    print(f"[错误] 找不到{what}：{p}")
                    return False
            print(f"[常驻] 启动 TTS 服务 → {self._resident_url()}")
            print("[常驻] 首次要加载模型，请稍候；之后每一批都直接复用，不再等待")
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["YYN_NTFY_TOPIC"] = self.vars["ntfy_topic"].get().strip()   # 留空 = 不推手机
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                proc = subprocess.Popen(
                    [str(py), "-u", str(script), "--port", str(RESIDENT_PORT),
                     "--model-dir", model_dir, "--precision", "bf16"],
                    cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", creationflags=flags,
                )
            except Exception as e:
                print(f"[错误] 常驻服务启动失败：{e}")
                return False
            threading.Thread(target=self._pump_lines, args=(proc,), daemon=True).start()

        t0 = time.time()
        last = t0
        while True:
            self._check_abort()                        # 加载途中按下中止 → 立刻收工（服务留着，不动它）
            h = self._resident_health()
            if h and h.get("state") == "ready":
                print(f"[常驻] 模型就绪，用时 {time.time() - t0:.0f}s")
                return True
            if proc is not None and proc.poll() is not None:
                print(f"[错误] 常驻服务已退出（exit={proc.returncode}），请看上面的日志")
                return False
            if time.time() - t0 > 1800:
                print("[错误] 等待常驻服务超时（30 分钟）")
                return False
            if time.time() - last >= 15:
                last = time.time()
                print(f"[常驻] 仍在加载模型… 已等 {time.time() - t0:.0f}s")
            time.sleep(2)

    def _tts_shutdown(self, put=None) -> bool:
        """停掉常驻 TTS 服务（先请它自己退，再兜底杀进程）。put 为空 = 不输出日志。

        返回是否已确实停掉。「关闭TTS」按钮与关闭 exe（选「确定」时）都走这里。
        """
        put = put or (lambda s: None)
        if not self._resident_health():
            put("[常驻] 服务未在运行（无需关闭）\n")
            return True
        pid = 0
        try:
            pid = int(json.loads(RESIDENT_MARKER.read_text(encoding="utf-8")).get("pid") or 0)
        except Exception:
            pid = 0
        put(f"[常驻] 正在关闭服务（pid={pid or '?'}）…\n")
        try:
            req = urllib.request.Request(
                self._resident_url() + "/shutdown", data=b"{}",
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass
        t0 = time.time()
        while time.time() - t0 < 10 and self._resident_health():
            time.sleep(0.5)
        if self._resident_health() and pid:      # 温柔退出没成，直接杀
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=flags)
                time.sleep(0.5)
            except Exception:
                pass
        alive = bool(self._resident_health())
        if alive:
            put("[常驻] 关闭似乎没成功，请用任务管理器结束那个 python 进程\n")
        else:
            put("[常驻] 服务已关闭，显存已释放\n")
        try:
            RESIDENT_MARKER.unlink()
        except Exception:
            pass
        return not alive

    def t_tts_stop(self):
        """「关闭TTS」：停掉常驻服务、释放显存。"""
        self._tts_shutdown(put=self.out_q.put)

    # -------------------------------------------------- 试听 / 原声
    def t_play_voice(self):
        """「原声」：直接用系统默认播放器打开当前音色参考音频。"""
        voice = self._voice_file()
        if not voice or not os.path.isfile(voice):
            messagebox.showwarning("缺少音色", "请先选择「音色」。")
            return
        try:
            os.startfile(voice)
        except Exception as e:
            messagebox.showerror("播放失败", f"{voice}\n\n{e}")

    def t_preview(self):
        """「试听」：用当前音色合成固定的一句话（不加情感），跑完直接播放。

        走 dub_itts.py 独立进程，等于每次都重新加载模型（与正式配音同一条路）。
        """
        voice = self._voice_file()
        if not voice or not os.path.isfile(voice):
            messagebox.showwarning("缺少音色", "请先选择「音色」（试听用当前音色）。")
            return

        tmp = Path(tempfile.gettempdir()) / "YYNTools" / "preview"
        srt_dir = tmp / "srt"
        out_root = tmp / "out"
        srt_dir.mkdir(parents=True, exist_ok=True)
        (srt_dir / "试听.srt").write_text(PREVIEW_TEXT + "\n", encoding="utf-8")
        wav = out_root / "wav" / "preview" / "试听.wav"
        argv = ["--srt-dir", str(srt_dir), "--voice", voice,
                "--out", str(out_root), "--sub-dir", "preview",
                "--model-dir", os.path.join(
                    self.vars["itts_root"].get().strip(), "checkpoints"),
                "--emo-weight", "0", "--no-notify", "--overwrite"]

        def work():
            print("---- 试听合成（每次都会重新加载模型） ----")
            print(f"文本：{PREVIEW_TEXT}")
            print(f"音色：{voice}")
            print("情感：不加（emo_alpha=0，纯音色）\n")
            rc = self._run_dub("dub_itts.py", argv, model=MODEL_ITTS)
            if rc == 0 and wav.is_file():
                print(f"\n试听完成，播放：{wav}")
                try:
                    os.startfile(str(wav))
                except Exception as e:
                    print(f"[提示] 自动播放失败，请手动打开：{wav}\n{e}")
            else:
                print(f"\n[错误] 试听未生成（exit={rc}）")

        self._run("试听（合成一句）", work)

    def _add_button(self, parent, text, cmd, style="Main.TButton"):
        b = ttk.Button(parent, text=text, command=cmd, style=style)
        self.buttons.append(b)
        return b

    # -------------------------------------------------- 日志
    def log(self, s: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", s)
        self.log_text.see("end")
        if int(self.log_text.index("end-1c").split(".")[0]) > 3000:
            self.log_text.delete("1.0", "500.0")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def set_status(self, text, color="#0a6"):
        self.status.configure(text=text, foreground=color)

    def _poll(self):
        try:
            while True:
                item = self.out_q.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    self.busy = False
                    for b in self.buttons:
                        b.configure(state="normal")
                    self.set_status("就绪")
                else:
                    self.log(item)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    # -------------------------------------------------- 任务执行框架
    def _run(self, title, worker):
        if self.busy:
            messagebox.showinfo("请稍候", "上一个任务还在运行中。")
            return
        self.busy = True
        # 新一轮任务开始：复位「紧急中止」的待确认状态，并换上本任务专属的闸
        self.abort_armed = False
        ev = threading.Event()
        self.abort_ev = ev
        self.abort_btn.configure(text="紧急中止")
        for b in self.buttons:
            b.configure(state="disabled")
        self.set_status(f"运行中：{title}", "#c60")
        self.log(f"\n{'=' * 58}\n▶ {title}\n{'=' * 58}\n")

        def target():
            old_out, old_err = sys.stdout, sys.stderr
            self._tls.ev = ev                              # 本线程只认自己这一代的闸
            sys.stdout = sys.stderr = QueueWriter(self.out_q, gate=ev.is_set)
            try:
                worker()
            except _Aborted:
                pass                                   # 已中止：不再输出任何内容
            except SystemExit as e:
                print(f"\n[脚本中止] exit code = {e.code}")
            except Exception:
                print("\n[异常]\n" + traceback.format_exc())
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                self._tls.ev = None
                self.out_q.put(("__DONE__", title))

        threading.Thread(target=target, daemon=True).start()

    def _cur_abort(self):
        """当前线程所属任务的中止闸；不在任务线程里（如主线程）就退回当前那个。"""
        return getattr(self._tls, "ev", None) or self.abort_ev

    def _aborted(self) -> bool:
        return self._cur_abort().is_set()

    def _check_abort(self):
        """流水线检查点：已按下「紧急中止」就立刻抛出，停止后续一切动作。"""
        if self._aborted():
            raise _Aborted()

    def _call(self, mod, argv):
        self._check_abort()
        saved = sys.argv
        sys.argv = [mod.__name__.split(".")[-1]] + list(argv)
        try:
            return mod.main()
        finally:
            sys.argv = saved

    def _call_patched(self, mod, argv, patches: dict):
        """调用脚本并临时替换其模块级路径常量"""
        backup = {}
        for k, v in patches.items():
            backup[k] = getattr(mod, k, None)
            setattr(mod, k, v)
        try:
            return self._call(mod, argv)
        finally:
            for k, v in backup.items():
                if v is not None:
                    setattr(mod, k, v)

    # -------------------------------------------------- 取值工具
    def _src(self) -> str:
        return self.vars["source"].get().strip().strip('"')

    def _dst(self) -> str:
        return self.vars["target"].get().strip().strip('"')

    def _work_dir(self) -> str:
        """实际工作目录 = 输出目录 / 源文件夹名（源文件夹名自动取自源目录）"""
        base = self._dst()
        src = self._src()
        name = os.path.basename(os.path.normpath(src)) if src else ""
        return os.path.join(base, name) if name else base

    def _csv(self) -> str:
        return os.path.join(self._src(), "sub_zh.csv")

    def _check(self, need_csv=False) -> bool:
        src, dst = self._src(), self._dst()
        if not src:
            messagebox.showwarning("缺少源目录", "请先选择「源目录」。")
            return False
        if not os.path.isdir(src):
            messagebox.showwarning("源目录无效", f"源目录不存在：\n{src}")
            return False
        if not dst:
            messagebox.showwarning("缺少输出目录", "请先选择「输出目录」。")
            return False
        if not os.path.isdir(dst):
            if not messagebox.askyesno("输出目录不存在", f"输出目录不存在：\n{dst}\n\n是否自动创建？"):
                return False
            try:
                os.makedirs(dst, exist_ok=True)
            except Exception as e:
                messagebox.showerror("创建失败", str(e))
                return False
        if need_csv and not os.path.isfile(self._csv()):
            messagebox.showwarning("找不到 CSV", f"源目录下没有 sub_zh.csv：\n{self._csv()}")
            return False
        return True

    # ================================================== 主栏任务
    def t_oneclick(self):
        if not self._check(need_csv=True):
            return
        src, dst, csv = self._src(), self._work_dir(), self._csv()

        def work():
            steps = [
                ("步骤 4 · 查找缺失", find_missing_subtitles, ["--csv-file", csv, "--target-dir", dst]),
                ("步骤 1 · 汉化字幕", update_subtitles, ["--csv-file", csv, "--target-dir", dst]),
                ("步骤 2 · 去除括号", delete_by_content, ["--dir", dst]),
                ("步骤 3 · 去除标号", remove_line_numbers, ["--target-dir", dst]),
                ("步骤 5 · 提取未译", extract_untranslated, ["--target-dir", dst]),
            ]
            for name, mod, argv in steps:
                print(f"\n---- {name} ----")
                try:
                    self._call(mod, argv)
                except SystemExit as e:
                    print(f"（该步骤以 exit code {e.code} 结束，继续下一步）")

        self._run("一键版", work)

    def t_split(self):
        if not self._check(need_csv=True):
            return
        csv, dst = self._csv(), self._work_dir()

        def work():
            print("---- 拆分 srt（sub_zh.csv → 每 Key 一个 srt） ----")
            self._call(csv_split_srt, ["--csv", csv, "--out", dst, "--ext", "srt"])
            print("\n---- 去除括号（内容仅含括号的整条删除） ----")
            self._call(delete_by_content, ["--dir", dst])

        self._run("ZH 的 csv 拆分（含去括号）", work)

    def t_update(self):
        if not self._check(need_csv=True):
            return
        csv, dst = self._csv(), self._work_dir()
        self._run("汉化字幕", lambda: self._call(update_subtitles, ["--csv-file", csv, "--target-dir", dst]))

    def t_delete_bracket(self):
        if not self._check():
            return
        dst = self._work_dir()
        self._run("去除括号", lambda: self._call(delete_by_content, ["--dir", dst]))

    def t_remove_ln(self):
        if not self._check():
            return
        dst = self._work_dir()
        self._run("去除标号", lambda: self._call(remove_line_numbers, ["--target-dir", dst]))

    def t_export_vo(self):
        if not self._check(need_csv=True):
            return
        csv, votxt = self._csv(), self.vars["votxt"].get().strip()
        self._run(
            "导出VO文本",
            lambda: self._call_patched(export_vo_text, ["--csv-file", csv], {"VOTXT_BASE": votxt}),
        )

    def t_replace_dict(self):
        if not self._check():
            return
        dst, dic = self._work_dir(), self.vars["dict"].get().strip()
        self._run(
            "词表替换",
            lambda: self._call(replace_by_dict, ["--target-dir", dst, "--dict-file", dic]),
        )

    def t_check_content(self):
        if not self._check():
            return
        dst = self._work_dir()
        self._run("检查错误", lambda: self._call(check_subtitle_content, ["--target-dir", dst]))

    # ================================================== 副栏任务







    # -------------------------------------------------- 关闭
    def _ask_close_tts(self):
        """关闭 exe 时若常驻 TTS 仍在运行，弹出三选一。

        返回 "both"（关 exe + TTS 服务，释放显存）/ "ui"（只关 exe，保留 TTS 服务）/ None（取消）。
        """
        win = tk.Toplevel(self.root)
        win.title("常驻 TTS 正在运行")
        win.transient(self.root)
        win.resizable(False, False)
        win.grab_set()
        choice = {"v": None}

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, justify="left",
            text="常驻 TTS 服务正在运行。\n\n"
                 "「确定」= 关闭 exe 与 TTS 服务（释放显存）\n"
                 "「仅UI」= 只关 exe，保留 TTS 服务（下次配音秒开）\n"
                 "「取消」= 不关闭，返回软件",
        ).pack(anchor="w")

        def pick(v):
            choice["v"] = v
            win.destroy()

        # 三个按钮并排、等宽：同一 style + grid 的 uniform 分组
        # 按钮自建，不登记进 self.buttons（本窗口销毁后可能被统一 configure）
        btns = ttk.Frame(body)
        btns.pack(anchor="e", pady=(12, 0))
        for c in range(3):
            btns.columnconfigure(c, uniform="dlg", weight=1)
        ttk.Button(btns, text="确定", command=lambda: pick("both"),
                   style="Main.TButton").grid(row=0, column=0, sticky="ew")
        ttk.Button(btns, text="仅UI", command=lambda: pick("ui"),
                   style="Main.TButton").grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(btns, text="取消", command=win.destroy,
                   style="Main.TButton").grid(row=0, column=2, sticky="ew", padx=(8, 0))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.root.wait_window(win)
        return choice["v"]

    def _ask_force_close(self) -> bool:
        """「任务运行中」的关闭确认。

        messagebox 改不了按钮文字，而这里必须有个「确定」，所以自己搭个小窗。
        """
        win = tk.Toplevel(self.root)
        win.title("任务运行中")
        win.transient(self.root)
        win.resizable(False, False)
        win.grab_set()
        ok = {"v": False}

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, justify="left",
            text="仍有任务在运行。\n\n"
                 "「确定」会立刻结束正在跑的配音/合成进程，\n"
                 "可能留下不完整的 wav / srt，下次重跑会接着补。",
        ).pack(anchor="w")

        def yes():
            ok["v"] = True
            win.destroy()

        # 按钮自建，不登记进 self.buttons
        # （本窗口销毁后可能被 _run 统一 configure，碰到已销毁控件）
        # 两个按钮并排、等宽：同一 style + grid 的 uniform 分组，宽度自然对齐
        btns = ttk.Frame(body)
        btns.pack(anchor="e", pady=(12, 0))
        btns.columnconfigure(0, uniform="dlg", weight=1)
        btns.columnconfigure(1, uniform="dlg", weight=1)
        ttk.Button(btns, text="确定", command=yes,
                   style="Main.TButton").grid(row=0, column=0, sticky="ew")
        ttk.Button(btns, text="取消", command=win.destroy,
                   style="Main.TButton").grid(row=0, column=1, sticky="ew", padx=(8, 0))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.root.wait_window(win)
        return ok["v"]

    def t_abort(self):
        """「紧急中止」：需点两下，第二下才真正结束所有在跑的操作。

        中止范围 = 所有配音子进程（连其子进程）。**不动常驻 TTS 服务**——
        模型留在显存里，中止后再跑可立即复用，不必重新加载。
        """
        if not self.abort_armed:
            self.abort_armed = True
            self.abort_btn.configure(text="再次确定")
            self.log("\n[紧急中止] 再点一次「再次确定」即中止所有任务：\n"
                     "           结束所有子进程并停止流水线（此后不再运行、不再输出任何内容）；\n"
                     "           常驻 TTS 服务保持运行，不进显存重载。\n")
            return
        self.abort_armed = False
        self.abort_btn.configure(text="紧急中止")
        self.abort_ev.set()                     # 总闸：流水线检查点会立刻抛 _Aborted，输出同时被丢弃
        self.log("\n[紧急中止] 正在中止所有任务…\n")
        self._force_kill_procs()
        self.log("[紧急中止] 已中止：子进程结束、流水线停止、日志不再新增。常驻 TTS 未动。\n")
        # 立刻交还控制权，不必等被杀的 worker 自己收尾（它之后发的 __DONE__ 无副作用）
        self.busy = False
        for b in self.buttons:
            b.configure(state="normal")
        self.set_status("已中止", "#c00")

    def _force_kill_procs(self):
        """强制退出：把还在跑的子进程（含常驻 TTS 自己拉起的子进程）连同其子进程一起结束。"""
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        for p in list(self.procs):
            try:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=flags)
            except Exception:
                pass
        self.procs.clear()

    def on_close(self):
        # 关闭保护：任务运行中先确认，「确定」才会真关
        if self.busy:
            if not self._ask_force_close():
                return
            self.abort_ev.set()                 # 让流水线立刻停手，别再开新任务
            self._force_kill_procs()
        # 常驻 TTS 仍在运行时，交给用户三选一：一起关 / 只关界面（保留服务）/ 取消
        if self._resident_health():
            choice = self._ask_close_tts()
            if choice is None:
                return
            if choice == "both":
                self._tts_shutdown()
        save_config({k: v.get() for k, v in self.vars.items()})
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
