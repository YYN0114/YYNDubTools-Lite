#!/usr/bin/env python
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""按 SRT 逐句克隆配音：自然语速逐句推理，句间静音拼接成整轨，并生成新时间轴 SRT。

推理后端为 IndexTTS2，要点：
  - --model-dir 指向 checkpoints 目录（含 config.yaml、gpt.pth、s2mel.pth 等）；
    其上一级目录（内含 indextts 包）会自动加入 sys.path
  - IndexTTS2 构造参数只保留当前版本支持的项（不含 use_fp16/reference_device/reuse_spk_cond_for_emo）
  - --emo-weight（emo_alpha）控制情感强度，--emo-vector 指定 8 维情感向量（默认只用「自然」）
  - --emo-audio-dir 指定「情感参考音频」目录：按 srt 同名找音频，逐文件换情感参考
    （内核限制：emo_vector 与 emo_audio_prompt 互斥，两者只能用一个）
  - --api-url 指向常驻服务（tts_resident.py）：模型在服务侧只加载一次，反复跑不再重载
所有资源路径均由命令行参数给出，不依赖脚本所在目录的相对文件；
提示音直接引用 Windows 自带音效。

输入 SRT：纯文本，一行一句（不读时间轴，1 版/2 版通用，只要正文一致）。
输出：
    <输出根>\\wav\\<子目录>\\<源名>.wav   整轨音频（16-bit PCM）
    <输出根>\\srt\\<子目录>\\<源名>.srt   按真实生成时长回写的新时间轴
    <输出根>\\progress.json                进度快照（供监视窗口读取）
    <输出根>\\run.log                      文本日志

断点续跑：wav 与 srt 都已存在则跳过，不会覆盖。

示例
----
需用装有 IndexTTS2 依赖的 Python 解释器运行：

python dub_itts.py ^
  --srt-dir "<源 SRT 目录>" ^
  --voice   "<参考音色 WAV>" ^
  --out     "<输出根目录>" ^
  --limit 2 --emo-weight 0.65

    <源 SRT 目录> = 只读，不修改
    <输出根目录>  = 输出根，下建 wav/ 与 srt/
    --model-dir   checkpoints 目录（必填）
    --emo-weight  情感强度 0~1（走「情感向量」模式；0=音色原味，1=完全「自然」）
    成品文件名固定 = 源 SRT 的文件名（wav 与 srt 同名，不能自拟）
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import re
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

SKIP_LINE = re.compile(r"^[\s\d]*$|-->|\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}")

SILENCE_FLOOR = 120     # 静音判定绝对值下限（包络，int16 满量程 32767）
SILENCE_RATIO = 0.01    # 静音判定相对峰值比例
ENV_WIN_MS = 20         # 包络平滑窗口，用于滤掉孤立噪点
SPLICE_GAP_SEC = 0.25   # 近似数字静音块达到此长度即删除（模型插入的长空块）
SPLICE_RMS = 6.0        # 近似数字静音的包络上限（采样值仅 0/1/2 这类）
SPLICE_KEEP_MS = 200    # 删除空块后在原处保留的停顿
TRIM_PAD_MS = 50        # 裁剪首尾时各保留的余量
BAD_SPEECH_SEC = 0.30   # 有效语音短于此值判为合成失败（短句不适用此限）
CHARS_PER_SEC = 4.5     # 中文自然语速估计，用于推算预期时长
RATIO_HIGH = 2.7        # 长句语音时长偏长上限（超过即疑重复）
SHORT_EXPECT_SEC = 1.5  # 预期时长短于此值视为「短句」
SHORT_RATIO_HIGH = 4.0  # 短句的偏长上限（放宽，避免短句反复死磕 seed）
SINGLE_HOLE_SEC = 0.60  # 单句台词允许的最大句内空洞
MULTI_HOLE_SEC = 1.50   # 多句台词（句间本来就有停顿）允许的最大空洞
MEL_TOKENS_PER_SEC = 25.04  # 实测：撞满 max_mel_tokens(1500) 的样本时长均为 59.91s
MEL_TOKEN_MIN = 120         # 动态限幅下限（约 4.8s 上限，短片段也够用）
MEL_TOKEN_MAX = 1500        # 动态限幅上限
CAP_RATIO = 3.0             # 限幅倍数：略高于 2.7 倍合格线，合格样本不会被截断
SENT_SPLIT = re.compile(r"[。！？!?；;]")
MAX_PIECE_CHARS = 20      # 句级切分后单片仍超过此字数，再按逗号/顿号细切（模型吞字阈值）
SEED_STEP = 7919          # 第 2 次重试起，seed 每次递增量
FIRST_RETRY_SEED = 600    # 第 1 次重试固定使用的 seed
THIRD_RETRY_SEED = 23799  # 第 2 次重试的 seed（之后每次 + SEED_STEP）
# 台词全局替换（只影响合成用文本与输出 srt，不动源文件）
TEXT_REPLACE = [
    (re.compile(r"(?<![A-Za-z])TOC(?![A-Za-z])", re.IGNORECASE), "指挥中心"),
]

# 情感向量（8 维，顺序固定：高兴/愤怒/悲伤/恐惧/反感/低落/惊讶/自然）。
# 内核在「情感参考 == 音色参考」时会把 emo_alpha 强制为 1.0，且 merge_emovec
# 公式为 out = base + alpha*(emo - base)，同一音频时 emo==base，emo_alpha 不起作用。
# 向量模式下内核公式为
#   emovec = alpha * 向量情感 + (1 - alpha) * 音色自带情感
# 因此 --emo-weight 是「0=音色原味 → 1=完全自然」的强度旋钮。
# 默认向量可通过 --emo-vector 覆盖（GUI 的「八向」副栏就是给这 8 个数）。
EMO_VECTOR = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def parse_emo_vector(s: str, n: int = 8) -> list:
    """把 "0.2,0,0,0,0,0,0,0.8" 解析成 n 个 float。

    参数 s 为逗号分隔的情感向量文本（中英文逗号均可），n 为期望维数；
    返回长度 n 的 float 列表，解析失败或长度不符时回落默认向量。
    """
    if not s:
        return list(EMO_VECTOR)
    try:
        vals = [float(x) for x in str(s).replace("，", ",").split(",") if x.strip() != ""]
    except ValueError:
        print(f"警告: --emo-vector 解析失败，改用默认向量: {s!r}", file=sys.stderr)
        return list(EMO_VECTOR)
    if len(vals) != n:
        print(f"警告: --emo-vector 需要 {n} 个数值，收到 {len(vals)} 个，改用默认向量", file=sys.stderr)
        return list(EMO_VECTOR)
    return vals


def ratio_high(expected: float) -> float:
    """返回预期时长 expected 对应的「偏长」阈值倍数。

    短句（expected 小于 SHORT_EXPECT_SEC）用 SHORT_RATIO_HIGH，其余用 RATIO_HIGH。
    """
    return SHORT_RATIO_HIGH if expected < SHORT_EXPECT_SEC else RATIO_HIGH


# 「情感参考音频」按此顺序找同名文件（找到第一个即用）
EMO_AUDIO_EXTS = (".ogg", ".wav", ".mp3", ".flac")


def find_emo_audio(emo_dir: Path, stem: str) -> Path | None:
    """在 emo_dir 里按 srt 主干名找情感参考音频；找不到返回 None。"""
    for ext in EMO_AUDIO_EXTS:
        p = emo_dir / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def dynamic_max_mel_tokens(expected: float) -> int:
    """按片段预期时长推算 max_mel_tokens 上限，拦住模型的跑飞长尾。

    模型遇到难句会自回归跑飞：一直吐非语音垃圾直到撞满上限（实测 1500 token =
    59.91s，约 25.04 token/秒），成品时长虚高、有效字却很少。这里按
    「预期时长 × 偏长阈值 × token 速率」限幅，上限取 3.0 倍预期（略高于 2.7 倍的
    合格线），既不会截断合格样本，又能让跑飞样本快速撞顶暴露出来。
    """
    cap = expected * CAP_RATIO * MEL_TOKENS_PER_SEC
    return int(max(MEL_TOKEN_MIN, min(MEL_TOKEN_MAX, round(cap))))


def attempt_seed(base: int, attempt: int) -> int:
    """第 N 次尝试（attempt 从 0 起）用的 seed。

    种子池：base（默认 42）→ 600 → 23799 → 31718 → 39637 → 47556 …
    第 1 次重试固定为 600；第 2 次重试起从 23799 开始，每次 + SEED_STEP。
    """
    if attempt == 0:
        return base
    if attempt == 1:
        return FIRST_RETRY_SEED
    return THIRD_RETRY_SEED + (attempt - 2) * SEED_STEP


# ------------------------------------------------------------------ 完成提醒
# 提示音：随包分发的 CC0 音效（与脚本同目录）；缺失时由调用方回落到 MessageBeep()。
NOTIFY_SOUNDS = [
    Path(__file__).with_name("sound-askuser.wav"),
]


def _pick_notify_sound():
    """返回第一个存在的提示音文件；都不存在时返回 None（调用方回落 MessageBeep）。"""
    for p in NOTIFY_SOUNDS:
        if p.is_file():
            return p
    return None


NOTIFY_TITLE = "配音完成"                                       # 批次结束提醒的标题（可按任务自定义）
NTFY_SERVER = "https://ntfy.sh"
# 手机 ntfy App 订阅的主题：由 GUI 通过环境变量 YYN_NTFY_TOPIC 传入；留空 = 不推手机
NTFY_TOPIC = os.environ.get("YYN_NTFY_TOPIC", "").strip()
# 本地播放延迟：本地播声几乎瞬时，手机要经 ntfy -> FCM -> 系统通知，通常慢 0.5~2 秒。
# 给本地加一点延迟，两边才「同时响」。按实际听感微调（0 = 不加延迟）。
NOTIFY_DELAY_MS = 800


def notify_done(title: str, message: str) -> None:
    """批次结束提醒：手机 ntfy 推送与本地提示音并发发起，尽量同时到达。

    参数 title/message 为推送标题与正文；推送不等待返回，声音按
    NOTIFY_DELAY_MS 延迟后播放；任何一步失败都不影响主流程。
    """
    import threading

    def _push() -> None:
        if not NTFY_TOPIC:
            print("[提醒] 未设置 ntfy 主题，跳过手机推送（仅播本机提示音）", flush=True)
            return
        try:
            import urllib.request
            payload = json.dumps({
                "topic": NTFY_TOPIC,
                "title": title,
                "message": message,
                "tags": ["white_check_mark"],
            }, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                NTFY_SERVER, data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10).read()
            print(f"[提醒] 已推送手机 ntfy（{NTFY_TOPIC}）", flush=True)
        except Exception as e:
            # 手机收不到时靠这行定位失败原因
            print(f"[提醒] ntfy 推送失败：{type(e).__name__}: {e}", flush=True)

    worker = threading.Thread(target=_push, daemon=True)
    worker.start()                                     # 先发起推送，不等它返回
    try:
        import winsound
        sound = _pick_notify_sound()
        if sound is None:                              # 系统媒体目录里没有可用音效 → 用系统默认提示音
            print("[提醒] 未找到系统提示音，改用系统默认提示音", flush=True)
            if NOTIFY_DELAY_MS > 0:
                time.sleep(NOTIFY_DELAY_MS / 1000.0)
            winsound.MessageBeep()
        else:
            print(f"[提醒] 本机提示音：{sound}", flush=True)   # 打印实际播放的文件，便于与「听到的声音」核对
            if NOTIFY_DELAY_MS > 0:
                time.sleep(NOTIFY_DELAY_MS / 1000.0)    # 本地延迟，与手机对齐
            winsound.PlaySound(str(sound), winsound.SND_FILENAME)
            print("[提醒] 提示音已播完", flush=True)
    except Exception as e:
        print(f"[提醒] 本机提示音失败：{type(e).__name__}: {e}", flush=True)
    worker.join(timeout=12)                            # 收尾：确认推送已发出


# ------------------------------------------------------------------ 小工具
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ms_to_ts(ms: int) -> str:
    ms = max(0, int(ms))
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def read_lines(path: Path) -> list[str]:
    """读取纯文本台词，一行一句；过滤空行与疑似时间轴/序号行。"""
    raw = path.read_text(encoding="utf-8-sig")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for ln in raw.split("\n"):
        ln = ln.strip()
        if not ln or SKIP_LINE.search(ln):
            continue
        for pat, rep in TEXT_REPLACE:
            ln = pat.sub(rep, ln)
        out.append(ln)
    return out


def write_pcm16_wav(path: Path, sample_rate: int, wav_data) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), wav_data, int(sample_rate), subtype="PCM_16")


def write_srt(path: Path, cues: list[tuple[int, int, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = [
        f"{i}\n{ms_to_ts(a)} --> {ms_to_ts(b)}\n{t}"
        for i, (a, b, t) in enumerate(cues, 1)
    ]
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def _speech_envelope(arr, sample_rate: int):
    """20ms 滑动平均的幅度包络（抗单点噪点）。"""
    import numpy as np

    mag = np.abs(arr).astype(np.float32)
    if mag.ndim > 1:
        mag = mag.max(axis=1)
    n = int(mag.size)
    if n == 0:
        return mag
    win = max(1, int(sample_rate * ENV_WIN_MS / 1000.0))
    # 滑动平均：后缀和的差分（推平滑除），避免逐窗循环
    c = np.zeros(n + 1, dtype=np.float64)
    np.cumsum(mag, dtype=np.float64, out=c[1:])
    idx = np.arange(n)
    lo = np.maximum(0, idx - win + 1)
    return (c[idx + 1] - c[lo]) / (idx + 1 - lo)


def _silence_mask(arr, sample_rate: int):
    """静音掩码：按包络判定，散落的单采样噪点（如幅度 200~800 的孤立点）
    会被 20ms 平滑掉，不再干扰首尾裁剪与空洞检测。
    """
    import numpy as np

    if arr.shape[0] == 0:
        return np.zeros(0, dtype=bool)
    env = _speech_envelope(arr, sample_rate)
    peak = float(env.max()) if env.size else 0.0
    return env < max(float(SILENCE_FLOOR), peak * SILENCE_RATIO)


def splice_dead_air(arr, sample_rate: int, gap_sec: float = SPLICE_GAP_SEC,
                    rms: float = SPLICE_RMS):
    """删掉中段的"近似数字静音"空块（模型偶发插入，可达 20 秒以上）。

    只针对包络 < rms（采样值 0/1/2 这类数字静音）且长度 >= gap_sec 的整段；
    正常语音间隙带底噪，不会被误删。删除后在原处补 200ms 停顿。
    返回 (处理后的数组, 删掉的秒数)。
    """
    import numpy as np

    if arr.shape[0] == 0:
        return arr, 0.0
    env = _speech_envelope(arr, sample_rate)
    dead = env < rms
    if not dead.any():
        return arr, 0.0
    keep_gap = int(sample_rate * SPLICE_KEEP_MS / 1000.0)
    parts = []
    cursor = 0
    removed = 0.0
    for run in np.split(np.flatnonzero(dead), np.flatnonzero(np.diff(np.flatnonzero(dead)) != 1) + 1):
        s, e = int(run[0]), int(run[-1]) + 1
        dur = (e - s) / float(sample_rate)
        if dur < gap_sec:
            continue
        if s > cursor:
            parts.append(arr[cursor:s])
        if parts:
            parts.append(np.zeros((keep_gap,) + arr.shape[1:], dtype=arr.dtype))
        cursor = e
        removed += dur - SPLICE_KEEP_MS / 1000.0
    if not parts:
        return arr, 0.0
    if cursor < arr.shape[0]:
        parts.append(arr[cursor:])
    out = parts[0] if len(parts) == 1 else np.concatenate(parts, axis=0)
    return out, max(0.0, removed)


def trim_silence(arr, sample_rate: int):
    """裁掉首尾静音（两端各保留 TRIM_PAD_MS），返回裁好的数组。"""
    import numpy as np

    if arr.size == 0:
        return arr
    speech = np.flatnonzero(~_silence_mask(arr, sample_rate))
    if speech.size == 0:
        return arr[:0]
    pad = int(sample_rate * TRIM_PAD_MS / 1000)
    s = max(0, int(speech[0]) - pad)
    e = min(arr.shape[0], int(speech[-1]) + 1 + pad)
    return arr[s:e]


def inspect_audio(arr, sample_rate: int) -> tuple[float, float, float, float]:
    """体检：返回 (开头静音秒, 有效语音秒, 句内最大空洞秒, 空洞起始秒)。"""
    import numpy as np

    if arr.shape[0] == 0:
        return 0.0, 0.0, 0.0, 0.0
    sil = _silence_mask(arr, sample_rate)
    speech = np.flatnonzero(~sil)
    if speech.size == 0:
        return arr.shape[0] / sample_rate, 0.0, 0.0, 0.0
    lead = float(speech[0]) / sample_rate
    span = arr[speech[0]:speech[-1] + 1]
    speech_sec = float((~_silence_mask(span, sample_rate)).sum()) / sample_rate
    at = hole = 0.0
    idx = np.flatnonzero(_silence_mask(span, sample_rate))
    if idx.size:
        for run in np.split(idx, np.flatnonzero(np.diff(idx) != 1) + 1):
            dur = float(run[-1] - run[0] + 1) / sample_rate
            if dur > hole:
                hole, at = dur, float(run[0]) / sample_rate
    return lead, speech_sec, hole, at


def quality_score(meta: tuple, expected: float, hole_limit: float) -> float:
    """给单次推理结果打分，越小越好；<=0 表示合格。

    惩罚项：空洞超限、语音时长偏离预期（重复或漏字）、有效语音过短。
    """
    _lead, speech, hole, _at = meta
    score = 0.0
    if hole > hole_limit:
        score += 2.0 + (hole - hole_limit)
    ratio = speech / max(0.30, expected)
    hi = ratio_high(expected)
    if ratio > hi:
        score += 1.0 + (ratio - hi)
    elif ratio < 0.35:
        score += 1.0 + (0.35 - ratio) * 2.0
    if expected >= SHORT_EXPECT_SEC and speech < BAD_SPEECH_SEC:
        score += 5.0
    return score


def split_clauses(text: str) -> list[str]:
    """按句末标点把一句话切成若干片段（保留标点）。

    切分点：。！？；： 以及省略号「……」/「…」。省略号在原文里常当句读用，
    不切会留下三四十字的长片段，模型容易吞字（只合成出预期时长的三分之一）。
    不切逗号/顿号：全句逗号级切分会把一句话拆成十几段，每段独立合成后段间接缝
    各自带一次起音换气，成品听起来「几词一停/大喘气」。
    例外：句级切分后单片仍超过 MAX_PIECE_CHARS 字时，再按逗号/顿号细切一次
    （实测单片约 27 字就会被模型吞字，只剩四成时长）。这种细切的接缝落在
    逗号处，本身就是自然停顿点，不会造成「几词一停」。
    """
    pieces = re.findall(r"[^。！？；：…]+[。！？；：…]*", text)
    out: list[str] = []
    for p in (s.strip() for s in pieces):
        if not p:
            continue
        if len(p) <= MAX_PIECE_CHARS:
            out.append(p)
            continue
        subs = [s.strip() for s in re.findall(r"[^，、,]+[，、,]*", p)]
        subs = [s for s in subs if s]
        if len(subs) <= 1:
            out.append(p)
            continue
        # 贪心合包：相邻小节能合并到上限内就合并，避免切出「对你来说，」这种 5 字碎片
        buf = subs[0]
        for s in subs[1:]:
            if len(buf) + len(s) <= MAX_PIECE_CHARS:
                buf += s
            else:
                out.append(buf)
                buf = s
        out.append(buf)
    return out or [text]


def finalize_meta(meta: tuple, expected: float, hole_limit: float) -> list[str]:
    """把一次体检结果翻译成人能看的问题描述。"""
    lead, speech, hole, hole_at = meta
    warns: list[str] = []
    if lead >= 0.60:
        warns.append(f"开头静音{lead:.2f}s(已裁)")
    if hole >= hole_limit:
        warns.append(f"句内空洞{hole:.2f}s@{hole_at:.2f}s(限{hole_limit}s)")
    ratio = speech / expected
    if ratio > ratio_high(expected):
        warns.append(f"语音偏长{ratio:.1f}倍(疑似重复)")
    elif ratio < 0.50:
        warns.append(f"语音偏短{ratio:.1f}倍(疑似漏字)")
    if expected >= SHORT_EXPECT_SEC and speech < BAD_SPEECH_SEC:
        warns.append(f"有效语音仅{speech:.2f}s")
    return warns


class RemoteTTS:
    """走「常驻服务」(tts_resident.py) 的推理后端。

    接口刻意与本地 IndexTTS2.infer 对齐，这样 synth_best 里的重试/体检逻辑
    一行都不用改；区别只有两处：
      · 模型在服务侧只加载一次，本进程不碰显存；
      · seed 得随请求发给服务（本地是 torch.manual_seed 播种）。
    """

    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.last_capped = False

    def infer(self, spk_audio_prompt, text, output_path=None, lang="ZH",
              max_mel_tokens=1500, emo_alpha=0.65, emo_vector=None,
              emo_audio_prompt=None, seed=42, **kwargs):
        import base64
        import io
        import json
        import urllib.error
        import urllib.request
        import wave

        import numpy as np

        payload = {
            "text": text,
            "voice": str(spk_audio_prompt),
            "emo_audio": str(emo_audio_prompt) if emo_audio_prompt else None,
            "emo_vector": emo_vector,
            "emo_weight": float(emo_alpha),
            "seed": int(seed),
            "language": lang,
            "max_mel_tokens": int(max_mel_tokens),
        }
        req = urllib.request.Request(
            self.url + "/synth",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                res = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 服务侧 500 的原因在响应体里；不读出来，日志只剩一句 HTTP 500 没法查
            body = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(body).get("msg") or body
            except Exception:
                msg = body
            raise RuntimeError(f"常驻服务 {e.code}：{msg}") from None
        if not res.get("ok"):
            raise RuntimeError(res.get("msg") or "常驻服务返回失败")

        self.last_capped = bool(res.get("capped"))
        with wave.open(io.BytesIO(base64.b64decode(res["wav_b64"])), "rb") as w:
            sample_rate, channels = w.getframerate(), w.getnchannels()
            data = w.readframes(w.getnframes())
        arr = np.frombuffer(data, dtype=np.int16)
        if channels > 1:
            arr = arr.reshape(-1, channels)
        return sample_rate, arr


def synth_best(tts, args, text: str, expected: float, hole_limit: float, log=None,
               emo_audio=None):
    """一段文本做最多 max_retry+1 次推理，按质量打分选优。

    emo_audio 非空 = 用「情感参考音频」模式（该轮不传 emo_vector，内核规定二者互斥）。
    返回 (裁好的音频, 采样率, 体检, 尝试次数, 删除空块秒数, 问题列表, 是否合格)
    """
    import numpy as np

    # 内核 infer_generator 里：只要 emo_vector 不为 None 就会把 emo_audio_prompt 置 None，
    # 所以「音频情感」模式下必须传 emo_vector=None，且 emo_alpha 才不会被强制成 1.0。
    emo_kw = ({"emo_audio_prompt": str(emo_audio), "emo_vector": None}
              if emo_audio else {"emo_vector": args.emo_vector_parsed})

    best = None
    best_score = 1e9
    best_meta = (0.0, 0.0, 0.0, 0.0)
    best_splice = 0.0
    best_ok = False
    best_capped = False
    sample_rate = 0
    max_mel = dynamic_max_mel_tokens(expected)
    for attempt in range(int(args.max_retry) + 1):
        # IndexTTS 2.5 的 infer() 不接受 seed / diffusion_steps / inference_cfg_rate /
        # cfm_temperature 这四个参数：它们会落进 **generation_kwargs 被转发给 HF generate()，
        # 直接抛 "model_kwargs are not used by the model"；前两个 2.5 已写死 25 / 0.7。
        # 本地每次推理前给全局随机数手动播种，实现「换 seed 重试」；
        # 走常驻服务时由服务侧播种，这里把 seed 传过去即可。
        remote = isinstance(tts, RemoteTTS)
        attempt_sd = attempt_seed(int(args.seed), attempt) + int(args.seed_offset)
        if remote:
            infer_kw = {"seed": attempt_sd}
        else:
            import torch
            torch.manual_seed(attempt_sd)
            infer_kw = {}
        # 模型撞满 max_mel_tokens 时会 warnings.warn(RuntimeWarning)，这正是"跑飞"的
        # 直接证据（它想一直生成下去）。捕获它，把该次尝试直接判为不合格并换 seed。
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = tts.infer(
                spk_audio_prompt=str(args.voice_path),
                text=text,
                output_path=None,
                lang=args.language,
                do_sample=True,
                temperature=0.8,
                top_p=0.8,
                top_k=30,
                num_beams=3,
                repetition_penalty=10.0,
                length_penalty=0.0,
                max_mel_tokens=max_mel,
                max_text_tokens_per_segment=120,
                interval_silence=200,
                text_normalization=True,
                duration_factor=1.0,
                emo_alpha=args.emo_weight,
                **infer_kw,
                **emo_kw,
            )
        capped = tts.last_capped if remote else any(
            "max_mel_tokens" in str(w.message) for w in caught)
        if not (isinstance(result, tuple) and len(result) == 2):
            raise RuntimeError(f"推理未返回音频数据: {type(result).__name__}")
        sample_rate, wav_data = result
        arr = np.asarray(wav_data)
        if arr.ndim == 1:
            arr = arr[:, None]
        if arr.dtype != np.int16:
            arr = arr.astype(np.int16)
        # 模型偶发在句中插入整段"近似数字静音"（RMS<6，采样值只有 0/1/2），有时长达
        # 20 秒以上；先剔除这些数字静音空块，避免被判定为「句内空洞」而反复重试。
        arr, spliced = splice_dead_air(arr, sample_rate)
        meta = inspect_audio(arr, sample_rate)
        trimmed = trim_silence(arr, sample_rate)
        score = quality_score(meta, expected, hole_limit)
        if capped:
            score += 10.0   # 撞限幅 = 跑飞，时长再"正常"也判不合格
        # 打分选优（越小越好）：失败样本往往因塞满静音而最长，不能按最长取
        if score < best_score:
            best, best_score, best_meta = trimmed, score, meta
            best_splice, best_ok = spliced, score <= 0.0
            best_capped = capped
        if best_ok:
            break
        try:
            del arr, trimmed, wav_data
        except UnboundLocalError:
            pass
        gc.collect()
        if attempt < int(args.max_retry) and log:
            _, sp, hole, _ = meta
            why = "撞限幅(跑飞)" if capped else f"空洞 {hole:.2f}s"
            log(f"      片段异常（语音 {sp:.2f}s/预期 {expected:.2f}s、{why}、"
                f"限幅 {max_mel}token≈{max_mel / MEL_TOKENS_PER_SEC:.1f}s）"
                f"→ 换 seed 重试 {attempt + 2}/{int(args.max_retry) + 1}：{text[:16]}")
    warns = finalize_meta(best_meta, expected, hole_limit)
    if best_capped:
        warns.insert(0, "撞限幅(疑似跑飞,内容可能不完整)")
    if best_splice > 0.0:
        warns.insert(0, f"已删除空块{best_splice:.1f}s")
    return best, sample_rate, best_meta, best_ok, warns


def resolve_precision(torch_module, requested: str, device: str) -> tuple[bool, bool, str]:
    """解析精度设置，返回 (use_bf16, use_fp16, 实际精度名)。

    参数 requested 为 auto/bf16/fp16/fp32，device 为推理设备；
    device 非 cuda 时强制 fp32，requested 为 auto 时按显卡是否支持 bf16 决定。
    """
    precision = str(requested)
    if not str(device).startswith("cuda"):
        return False, False, "fp32"
    if precision == "auto":
        precision = (
            "bf16"
            if bool(getattr(torch_module.cuda, "is_bf16_supported", lambda: False)())
            else "fp16"
        )
    return precision == "bf16", precision == "fp16", precision


class Progress:
    """把进度写成 progress.json，供外部监视窗口实时读取。"""

    def __init__(self, out_root: Path, start: int, limit: int, total: int):
        self.path = out_root / "progress.json"
        self.log_path = out_root / "run.log"
        self.data = {
            "updated": now_str(),
            "state": "loading",
            "start_index": start,
            "limit": limit,
            "total": total,
            "done": 0,
            "skipped": 0,
            "empty": 0,
            "failed": 0,
            "current": "",
            "current_sentence": "",
            "elapsed_sec": 0.0,
            "avg_sec_per_file": 0.0,
            "eta_sec": None,
            "output_root": str(out_root),
        }
        self.t0 = time.time()
        self.flush()

    def set(self, **kw) -> None:
        self.data.update(kw)
        self.flush()

    def log(self, line: str) -> None:
        print(line, flush=True)
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def flush(self) -> None:
        self.data["updated"] = now_str()
        self.data["elapsed_sec"] = round(time.time() - self.t0, 1)
        self.data["eta_sec"] = None
        done = self.data["done"] + self.data["skipped"] + self.data["failed"] + self.data["empty"]
        if done > 0:
            avg = self.data["elapsed_sec"] / done
            self.data["avg_sec_per_file"] = round(avg, 2)
            left = self.data["total"] - done
            self.data["eta_sec"] = round(avg * left, 0)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass


# ------------------------------------------------------------------ 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="IndexTTS 2.5 CLI 逐句配音（SRT 驱动）")
    ap.add_argument("--srt-dir", default="",
                    help="源 SRT 目录（纯文本，一行一句）")
    ap.add_argument("--voice", required=True, help="参考音色 WAV")
    ap.add_argument("--out", required=True, help="输出根目录（下建 wav/ 与 srt/）")
    ap.add_argument("--start", type=int, default=0, help="从第几个文件开始（0 起）")
    ap.add_argument("--limit", type=int, default=0, help="本批处理文件数（0=到末尾）")
    ap.add_argument("--gap-ms", type=int, default=200, help="句间静音，毫秒")
    ap.add_argument("--model-dir", required=True,
                    help="checkpoints 目录（含 config.yaml）；其上一级目录会加入 sys.path")
    ap.add_argument("--api-url", default="",
                    help="常驻服务地址（如 http://127.0.0.1:9882）。指定后本进程不加载模型，"
                         "全部推理交给 tts_resident.py 那边常驻的模型，省掉每次重载的等待")
    ap.add_argument("--language", default="ZH")
    ap.add_argument("--device", default=None)
    ap.add_argument("--precision", default="bf16", choices=["auto", "bf16", "fp16", "fp32"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-retry", type=int, default=6,
                    help="单句体检不过关时换 seed 重试次数上限")
    ap.add_argument("--seed-offset", type=int, default=0,
                    help="整条 seed 链整体平移的偏移量（重做时用来避开与上一轮完全相同的样本）")
    ap.add_argument("--emo-weight", type=float, default=0.65,
                    help="情感强度 0~1：0=完全保留音色自带的情绪，1=完全套用情感向量")
    ap.add_argument("--emo-vector", default="",
                    help="8 维情感向量，逗号分隔，顺序=高兴,愤怒,悲伤,恐惧,反感,低落,惊讶,自然"
                         "（留空=只用「自然」）。实际生效值 = 本向量 × --emo-weight")
    ap.add_argument("--emo-audio-dir", default="",
                    help="情感参考音频目录：按 srt 同名找 .ogg/.wav/.mp3/.flac 作为情感参考；"
                         "指定后本模式优先用音频（内核与 --emo-vector 互斥），"
                         "找不到同名音频的按 --emo-audio-fallback 决定跳过还是回落向量")
    ap.add_argument("--emo-audio-same-dir", action="store_true",
                    help="情感参考音频就在「每个 srt 自己所在的目录」里按同名找"
                         "（与 --emo-audio-dir 二选一，可跨目录）")
    ap.add_argument("--emo-audio-fallback", action="store_true",
                    help="找不到同名情感音频时不跳过，改用 --emo-vector 继续配")
    ap.add_argument("--only-list", default=None,
                    help="只处理清单内的文件（每行一个文件名或去扩展名，可用 # 注释）")
    ap.add_argument("--sub-dir", default="",
                    help="在 wav/ 与 srt/ 下再套一层子目录（按角色名分开存放）")
    ap.add_argument("--clause-split", action="store_true",
                    help="按句末标点（。！？；：…）把每句切成片段分别合成（减少段间接缝换气）")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--no-notify", action="store_true",
                    help="跑完不播提示音、不推 ntfy（供 GUI「试听」这类单句调用）")
    args = ap.parse_args()
    args.emo_vector_parsed = parse_emo_vector(args.emo_vector)
    if args.emo_vector:
        print(f"情感向量: {args.emo_vector_parsed} × 强度 {args.emo_weight}")

    srt_dir = Path(args.srt_dir) if args.srt_dir else None
    voice, out_root = Path(args.voice), Path(args.out)
    args.voice_path = voice
    if not voice.is_file():
        print(f"参考音色不存在: {voice}", file=sys.stderr)
        return 1

    if srt_dir and srt_dir.is_dir():
        files = sorted(p for p in srt_dir.iterdir() if p.suffix.lower() == ".srt")
    else:
        print(f"源 SRT 目录不存在: {srt_dir}", file=sys.stderr)
        return 1
    if args.only_list:
        lst = Path(args.only_list)
        if not lst.is_file():
            print(f"清单文件不存在: {lst}", file=sys.stderr)
            return 1
        want = set()
        for ln in lst.read_text(encoding="utf-8-sig").splitlines():
            ln = ln.split("#", 1)[0].strip()
            if ln:
                want.add(Path(ln).stem.lower())
        files = [p for p in files if p.stem.lower() in want]
        missing = want - {p.stem.lower() for p in files}
        if missing:
            print(f"清单里 {len(missing)} 个文件在源目录找不到（已忽略）: "
                  f"{sorted(missing)[:5]}", file=sys.stderr)
    if args.start:
        files = files[args.start:]
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("没有待处理的 SRT", file=sys.stderr)
        return 1

    wav_dir = out_root / "wav" / args.sub_dir
    srt_dir_out = out_root / "srt" / args.sub_dir
    wav_dir.mkdir(parents=True, exist_ok=True)
    srt_dir_out.mkdir(parents=True, exist_ok=True)
    prog = Progress(out_root, args.start, args.limit, len(files))
    prog.log(f"\n===== {now_str()} 本批 {len(files)} 个文件 "
             f"(start={args.start}, limit={args.limit or '全部'}) =====")

    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)

    # 模型根目录 = checkpoints 的上一级（内含 indextts 包），加入 sys.path 以便导入
    node_dir = Path(args.model_dir).resolve().parent
    if str(node_dir) not in sys.path:
        sys.path.insert(0, str(node_dir))
    try:
        import numpy as np
    except ImportError:
        print("numpy 不可用，请用 indexTTS2\\.venv\\Scripts\\python.exe 运行本脚本",
              file=sys.stderr)
        return 1

    if args.api_url:
        # 常驻模式：模型由 tts_resident.py 那边加载一次并常驻，本进程不再碰显存
        tts = RemoteTTS(args.api_url)
        prog.set(state="loading")
        prog.log(f"使用常驻服务 {args.api_url}（本进程不加载模型）")
        prog.set(state="running")
    else:
        try:
            import torch
        except ImportError:
            print("PyTorch 不可用，请用 indexTTS2\\.venv\\Scripts\\python.exe 运行本脚本",
                  file=sys.stderr)
            return 1
        from indextts.infer_v2_5 import IndexTTS2

        device = str(args.device) if args.device else ("cuda:0" if torch.cuda.is_available() else "cpu")
        use_bf16, use_fp16, effective = resolve_precision(torch, args.precision, device)
        model_dir = Path(args.model_dir).resolve()
        if not (model_dir / "config.yaml").is_file():
            print(f"模型目录不完整（缺 config.yaml）: {model_dir}", file=sys.stderr)
            return 1

        prog.set(state="loading")
        t0 = time.time()
        tts = IndexTTS2(
            cfg_path=str(model_dir / "config.yaml"),
            model_dir=str(model_dir),
            use_bf16=use_bf16,
            device=device,
            use_cuda_kernel=False,
            use_qwen_emo=False,
        )
        prog.log(f"模型就绪 device={device} precision={effective} 用时 {time.time() - t0:.0f}s")
        prog.set(state="running")

    gap_samples = 0
    gap_ms = int(args.gap_ms)
    suspicious: list[tuple] = []
    emo_audio_dir = Path(args.emo_audio_dir) if args.emo_audio_dir else None
    if emo_audio_dir:
        prog.log(f"情感参考音频目录: {emo_audio_dir}（按 srt 同名匹配 "
                 f"{'/'.join(EMO_AUDIO_EXTS)}）")
    elif args.emo_audio_same_dir:
        tail = "找不到则改用向量继续配" if args.emo_audio_fallback else "找不到则跳过该文件"
        prog.log(f"情感参考音频: 与 srt 同目录按同名匹配 {'/'.join(EMO_AUDIO_EXTS)}（{tail}）")

    for i, srt_path in enumerate(files, 1):
        stem = srt_path.stem
        wav_out = wav_dir / f"{stem}.wav"
        srt_out = srt_dir_out / f"{stem}.srt"
        prog.set(current=f"{stem}.srt ({i}/{len(files)})", current_sentence="")

        if wav_out.is_file() and srt_out.is_file() and not args.overwrite:
            prog.set(skipped=prog.data["skipped"] + 1)
            prog.flush()
            continue

        lines = read_lines(srt_path)
        if not lines:
            prog.log(f"[{i}/{len(files)}] 空文件跳过 {stem}.srt")
            prog.set(empty=prog.data["empty"] + 1)
            prog.flush()
            continue
        if any(re.search(r"[()（）]", ln) for ln in lines):
            prog.log(f"[{i}/{len(files)}] 跳过（内容含括号）{stem}.srt")
            prog.set(skipped=prog.data["skipped"] + 1)
            prog.flush()
            continue

        # 情感参考目录：固定目录 > 与 srt 同目录（后者允许清单里跨目录）
        cur_emo_dir = emo_audio_dir or (srt_path.parent if args.emo_audio_same_dir else None)
        emo_audio = find_emo_audio(cur_emo_dir, stem) if cur_emo_dir else None
        if cur_emo_dir and emo_audio is None:
            if args.emo_audio_fallback:
                prog.log(f"[{i}/{len(files)}] 无同名情感音频，改用「八向」向量 {stem}.srt")
            else:
                prog.log(f"[{i}/{len(files)}] 跳过（找不到同名情感音频）{stem}.srt")
                prog.set(skipped=prog.data["skipped"] + 1)
                prog.flush()
                continue

        t1 = time.time()
        try:
            parts: list = []
            cues: list[tuple[int, int, str]] = []
            cursor_ms = 0
            sample_rate = 0
            for k, text in enumerate(lines, 1):
                nseg = len([x for x in SENT_SPLIT.split(text) if x.strip()]) or 1
                hole_limit = SINGLE_HOLE_SEC if nseg <= 1 else MULTI_HOLE_SEC
                expected = max(0.40, len(text) / CHARS_PER_SEC)
                pieces = split_clauses(text) if args.clause_split else [text]
                line_parts: list = []
                speech = 0.0
                warns: list[str] = []
                sample_rate = 0
                for pi, piece in enumerate(pieces, 1):
                    tag = f"第 {k}/{len(lines)} 句" + (f" 片段 {pi}/{len(pieces)}" if len(pieces) > 1 else "")
                    prog.set(current_sentence=f"{tag}：{piece[:24]}")
                    piece_expected = max(0.40, len(piece) / CHARS_PER_SEC)
                    arr, sample_rate, meta, ok, pw = synth_best(
                        tts, args, piece, piece_expected, hole_limit, prog.log,
                        emo_audio=emo_audio)
                    speech += meta[1]
                    warns.extend(pw)
                    line_parts.append(arr)
                    if pi < len(pieces):
                        gap_n = int(round(sample_rate * gap_ms / 1000.0))
                        line_parts.append(np.zeros((gap_n, arr.shape[1]), dtype=np.int16))
                arr = line_parts[0] if len(line_parts) == 1 else np.concatenate(line_parts, axis=0)
                eff = arr.shape[0] / float(sample_rate)
                ratio = speech / expected
                if ratio > ratio_high(expected):
                    warns.append(f"整句偏长{ratio:.1f}倍(疑似重复)")
                elif ratio < 0.50:
                    warns.append(f"整句偏短{ratio:.1f}倍(疑似漏字)")
                if warns:
                    suspicious.append((stem, k, text, len(pieces), ";".join(warns)))
                dur_ms = int(round(eff * 1000.0))
                cues.append((cursor_ms, cursor_ms + dur_ms, text))
                parts.append(arr)
                cursor_ms += dur_ms
                if k < len(lines):
                    gap_samples = int(round(sample_rate * gap_ms / 1000.0))
                    parts.append(np.zeros((gap_samples, arr.shape[1]), dtype=np.int16))
                    cursor_ms += gap_ms

            merged = parts[0] if len(parts) == 1 else np.concatenate(parts, axis=0)
            if merged.shape[0] == 0:
                raise RuntimeError("整轨为空（全部句子都未生成有效语音）")
            write_pcm16_wav(wav_out, sample_rate, merged)
            write_srt(srt_out, cues)
            total_s = cursor_ms / 1000.0
            prog.set(done=prog.data["done"] + 1, current_sentence="")
            prog.log(f"[{i}/{len(files)}] OK   {stem}.wav  "
                     f"{len(lines)} 句 / {total_s:.1f}s / 用时 {time.time() - t1:.1f}s")
            prog.flush()
        except Exception as e:
            prog.set(failed=prog.data["failed"] + 1, current_sentence="")
            prog.log(f"[{i}/{len(files)}] FAIL {stem}.wav: {type(e).__name__} {str(e)[:200]}")
            prog.flush()
        finally:
            # 及时回收：长静音样本的数组很大，多句/多次重试后容易把内存吃满
            parts = []
            merged = None
            gc.collect()

    prog.set(state="finished", current="")
    d = prog.data
    if suspicious:
        csv_path = out_root / "suspicious.csv"
        fresh = not csv_path.exists()
        with csv_path.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as f:
            w = csv.writer(f)
            if fresh:
                w.writerow(["文件", "第几句", "台词", "推理次数", "问题"])
            w.writerows(suspicious)
        prog.log(f"可疑条目 {len(suspicious)} 条，已追加到 {csv_path}")
    prog.log(f"完成: 成功 {d['done']} / 跳过 {d['skipped']} / 空文件 {d['empty']} "
             f"/ 失败 {d['failed']} / 共 {d['total']}  耗时 {d['elapsed_sec'] / 60:.1f} 分钟")
    if not args.no_notify:
        notify_done(
            NOTIFY_TITLE,
            f"成功 {d['done']} / 跳过 {d['skipped']} / 空文件 {d['empty']} / 失败 {d['failed']}\n"
            f"共 {d['total']} 个，耗时 {d['elapsed_sec'] / 60:.1f} 分钟\n"
            f"可疑 {len(suspicious)} 条（见 suspicious.csv）",
        )
    return 0 if d["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
