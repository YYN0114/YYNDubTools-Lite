#!/usr/bin/env python
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""按 SRT 逐句用 GPT-SoVITS v2Pro 克隆配音（本地直跑，无需 api_v2 服务）。

与 dub_itts.py 共用同一套流程：逐句推理 → 体检 → 换 seed 重试 → 打分选优 →
写整轨 wav 与新时间轴 srt → progress.json → 完成提醒（ntfy + 提示音）。
差别只在推理后端：这里调 GPT-SoVITS 自带的 TTS_infer_pack。

要点：
  - 必须用 GPT-SoVITS 自带的 runtime\\python.exe 运行本脚本；
  - 内核用 os.getcwd() 拼资源路径，所以必须先 chdir 到 GPT-SoVITS 根目录再 import；
  - 参考音频有 3~10 秒硬约束（_set_prompt_semantic 里会 raise OSError），
    本脚本会把音色自动裁到该区间（不足则补静音）后放进临时目录使用；
  - TTS.run() 返回生成器，非流式模式下只有末尾一次 yield，取完必须 close()，
    不 close() 则 finally 里的 empty_cache() 不执行，显存不会释放。

示例
----
需用 GPT-SoVITS 自带的 runtime\\python.exe 运行：

python dub_gpt.py ^
  --srt-dir "<源 SRT 目录>" ^
  --voice   "<参考音色 WAV>" ^
  --ref-text "<参考音色对应文本>" ^
  --root    "<GPT-SoVITS 根目录>" ^
  --out     "<输出根目录>"

产物：<输出根>\\wav\\<子目录>\\<源名>.wav 、<输出根>\\srt\\<子目录>\\<源名>.srt
"""
from __future__ import annotations

import argparse
import csv
import gc
import os
import re
import shutil
import sys
import tempfile
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dub_itts as D  # noqa: E402  复用质检/写盘/进度/提醒等公共逻辑

REF_MAX_SEC = 10.0    # GPT-SoVITS 参考音频上限（超过会被内核拒绝）
REF_PAD_SEC = 3.5     # 参考音频不足 3 秒时补到这么长（补静音）
GPT_VERSION = "v2Pro"
WEIGHTS = {
    "t2s": "GPT_SoVITS/pretrained_models/s1v3.ckpt",
    "vits": "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth",
    "bert": "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
    "hubert": "GPT_SoVITS/pretrained_models/chinese-hubert-base",
}


def guess_lang(text: str) -> str:
    """参考文本语种：含 CJK 返回 zh，纯非 CJK 返回 en（统一走 zh 识别中英混排）。"""
    return "zh" if any("\u4e00" <= c <= "\u9fff" for c in text) else "en"


def prepare_ref(voice: Path, work: Path) -> Path:
    """把音色裁到 3~10 秒（内核硬约束），写入临时目录并返回该路径。

    同一路径整批复用，内核按路径缓存参考特征，只编码一次。
    """
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(voice), dtype="float32", always_2d=True)
    pcm = np.clip(data.mean(axis=1) * 32767.0, -32768, 32767).astype(np.int16)[:, None]
    pcm = D.trim_silence(pcm, sr)                      # 先去掉首尾静音，参考更干净
    if pcm.shape[0] == 0:
        pcm = np.zeros((int(sr * REF_PAD_SEC), 1), dtype=np.int16)
    maxn = int(sr * REF_MAX_SEC)
    if pcm.shape[0] > maxn:
        pcm = pcm[:maxn]
    minn = int(sr * REF_PAD_SEC)
    if pcm.shape[0] < minn:
        pcm = np.concatenate(
            [pcm, np.zeros((minn - pcm.shape[0], 1), dtype=np.int16)], axis=0)
    out = work / f"ref_{voice.stem}_{sr}.wav"
    sf.write(str(out), pcm, sr, subtype="PCM_16")
    return out


def synth_best(tts, args, ref_wav: Path, text: str, expected: float,
               hole_limit: float, log=None):
    """一段文本做最多 max_retry+1 次推理，按质量打分选优（与 dub_itts 同口径）。

    参数：tts 为 GPT-SoVITS 的 TTS 实例，ref_wav 为裁到 3~10 秒的参考音频，
    text/expected/hole_limit 为该片段文本、预期时长与句内空洞上限，log 为日志回调。
    返回 (裁好的音频, 采样率, 体检结果, 是否合格, 问题列表)。
    """
    import numpy as np

    best = None
    best_score = 1e9
    best_meta = (0.0, 0.0, 0.0, 0.0)
    best_splice = 0.0
    best_ok = False
    sample_rate = 32000
    for attempt in range(int(args.max_retry) + 1):
        inputs = {
            "text": text,
            "text_lang": args.lang,
            "ref_audio_path": str(ref_wav),
            "prompt_text": args.ref_text,
            "prompt_lang": args.ref_lang,
            "top_k": 15,
            "top_p": 1.0,
            "temperature": 1.0,
            "text_split_method": "cut0",   # 不切：每段台词自己就是一个片段
            "batch_size": 1,
            "speed_factor": 1.0,
            "split_bucket": True,
            "fragment_interval": 0.0,
            "seed": D.attempt_seed(int(args.seed), attempt) + int(args.seed_offset),
            "parallel_infer": True,
            "repetition_penalty": 1.35,
            "return_fragment": False,
            "streaming_mode": False,
        }
        gen = tts.run(inputs)
        try:
            sample_rate, wav_data = next(gen)
        finally:
            gen.close()                    # 触发内核 finally 里的 empty_cache()
        arr = np.asarray(wav_data)
        if arr.ndim == 1:
            arr = arr[:, None]
        if arr.dtype != np.int16:
            arr = arr.astype(np.int16)
        arr, spliced = D.splice_dead_air(arr, sample_rate)
        meta = D.inspect_audio(arr, sample_rate)
        trimmed = D.trim_silence(arr, sample_rate)
        score = D.quality_score(meta, expected, hole_limit)
        if score < best_score:
            best, best_score, best_meta = trimmed, score, meta
            best_splice, best_ok = spliced, score <= 0.0
        if best_ok:
            break
        del arr, trimmed, wav_data
        gc.collect()
        if attempt < int(args.max_retry) and log:
            _, sp, hole, _ = meta
            log(f"      片段异常（语音 {sp:.2f}s/预期 {expected:.2f}s、空洞 {hole:.2f}s）"
                f"→ 换 seed 重试 {attempt + 2}/{int(args.max_retry) + 1}：{text[:16]}")
    warns = D.finalize_meta(best_meta, expected, hole_limit)
    if best_splice > 0.0:
        warns.insert(0, f"已删除空块{best_splice:.1f}s")
    return best, sample_rate, best_meta, best_ok, warns


def main() -> int:
    ap = argparse.ArgumentParser(description="GPT-SoVITS v2Pro CLI 逐句配音（SRT 驱动）")
    ap.add_argument("--srt-dir", required=True, help="源 SRT 目录（纯文本，一行一句）")
    ap.add_argument("--voice", required=True, help="参考音色 WAV")
    ap.add_argument("--out", required=True, help="输出根目录（下建 wav/ 与 srt/）")
    ap.add_argument("--root", required=True, help="GPT-SoVITS 根目录（含 runtime 与 GPT_SoVITS）")
    ap.add_argument("--ref-text", default="", help="参考音色对应文本（temp.txt 第 2 列）")
    ap.add_argument("--ref-lang", default="", help="参考文本语种 zh/en（留空按文本自动判断）")
    ap.add_argument("--lang", default="zh", help="待合成台词的语种")
    ap.add_argument("--start", type=int, default=0, help="从第几个文件开始（0 起）")
    ap.add_argument("--limit", type=int, default=0, help="本批处理文件数（0=到末尾）")
    ap.add_argument("--gap-ms", type=int, default=200, help="句间静音，毫秒")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-retry", type=int, default=6,
                    help="单句体检不过关时换 seed 重试次数上限")
    ap.add_argument("--seed-offset", type=int, default=0,
                    help="整条 seed 链整体平移的偏移量（重做时用来避开与上一轮相同的样本）")
    ap.add_argument("--only-list", default=None,
                    help="只处理清单内的文件（每行一个文件名或去扩展名，可用 # 注释）")
    ap.add_argument("--sub-dir", default="",
                    help="在 wav/ 与 srt/ 下再套一层子目录（按角色名分开存放）")
    ap.add_argument("--clause-split", action="store_true",
                    help="按句末标点把每句切成片段分别合成（减少段间接缝换气）")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    if not args.ref_lang:
        args.ref_lang = guess_lang(args.ref_text)

    srt_dir, voice, out_root = Path(args.srt_dir), Path(args.voice), Path(args.out)
    root = Path(args.root).resolve()
    if not voice.is_file():
        print(f"参考音色不存在: {voice}", file=sys.stderr)
        return 1
    if not (root / "GPT_SoVITS" / "TTS_infer_pack" / "TTS.py").is_file():
        print(f"GPT-SoVITS 根目录不完整: {root}", file=sys.stderr)
        return 1

    files = sorted(p for p in srt_dir.iterdir() if p.suffix.lower() == ".srt")
    if args.only_list:
        lst = Path(args.only_list)
        if not lst.is_file():
            print(f"清单文件不存在: {lst}", file=sys.stderr)
            return 1
        want = {Path(ln.split("#", 1)[0].strip()).stem.lower()
                for ln in lst.read_text(encoding="utf-8-sig").splitlines()
                if ln.split("#", 1)[0].strip()}
        files = [p for p in files if p.stem.lower() in want]
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
    prog = D.Progress(out_root, args.start, args.limit, len(files))
    prog.log(f"\n===== {D.now_str()} GPT-SoVITS {GPT_VERSION} 本批 {len(files)} 个文件 "
             f"(start={args.start}, limit={args.limit or '全部'}) =====")

    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)

    # ---- 内核只在 import 时读一次 cwd，必须先 chdir 再 import ----
    os.chdir(root)
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ.setdefault("version", GPT_VERSION)
    for p in (str(root), str(root / "GPT_SoVITS")):
        if p not in sys.path:
            sys.path.append(p)
    prog.set(state="loading")
    t0 = time.time()
    try:
        import torch
        from GPT_SoVITS.TTS_infer_pack.TTS import TTS
    except ImportError as e:
        print(f"依赖缺失，请用 GPT-SoVITS 自带的 runtime\\python.exe 运行本脚本：{e}",
              file=sys.stderr)
        return 1

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tts = TTS({"custom": {
        "version": GPT_VERSION,
        "device": device,
        "is_half": device == "cuda",
        "t2s_weights_path": WEIGHTS["t2s"],
        "vits_weights_path": WEIGHTS["vits"],
        "bert_base_path": WEIGHTS["bert"],
        "cnhuhbert_base_path": WEIGHTS["hubert"],
    }})
    prog.log(f"模型就绪 device={device} is_half={device == 'cuda'} "
             f"用时 {time.time() - t0:.0f}s")

    work = Path(tempfile.mkdtemp(prefix="yyn_gpt_ref_"))
    try:
        ref_wav = prepare_ref(voice, work)
        prog.log(f"参考音频: {voice.name} → {ref_wav.name}")
        prog.set(state="running")
        run_batch(tts, args, prog, files, ref_wav, wav_dir, srt_dir_out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if prog.data["failed"] == 0 else 1


def run_batch(tts, args, prog, files, ref_wav, wav_dir, srt_dir_out) -> None:
    """逐文件合成整轨 wav 与新时间轴 srt，并累计可疑条目（与 dub_itts 主循环同构）。

    参数：prog 负责进度与日志，files 为待处理 SRT 列表，ref_wav 为参考音频，
    wav_dir/srt_dir_out 为产物目录；无返回值。
    """
    import numpy as np

    gap_ms = int(args.gap_ms)
    suspicious: list[tuple] = []

    for i, srt_path in enumerate(files, 1):
        stem = srt_path.stem
        wav_out = wav_dir / f"{stem}.wav"
        srt_out = srt_dir_out / f"{stem}.srt"
        prog.set(current=f"{stem}.srt ({i}/{len(files)})", current_sentence="")

        if wav_out.is_file() and srt_out.is_file() and not args.overwrite:
            prog.set(skipped=prog.data["skipped"] + 1)
            prog.flush()
            continue

        lines = D.read_lines(srt_path)
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

        t1 = time.time()
        parts: list = []
        try:
            cues: list[tuple[int, int, str]] = []
            cursor_ms = 0
            sample_rate = 0
            for k, text in enumerate(lines, 1):
                nseg = len([x for x in D.SENT_SPLIT.split(text) if x.strip()]) or 1
                hole_limit = D.SINGLE_HOLE_SEC if nseg <= 1 else D.MULTI_HOLE_SEC
                expected = max(0.40, len(text) / D.CHARS_PER_SEC)
                pieces = D.split_clauses(text) if args.clause_split else [text]
                line_parts: list = []
                speech = 0.0
                warns: list[str] = []
                for pi, piece in enumerate(pieces, 1):
                    tag = f"第 {k}/{len(lines)} 句" + (
                        f" 片段 {pi}/{len(pieces)}" if len(pieces) > 1 else "")
                    prog.set(current_sentence=f"{tag}：{piece[:24]}")
                    arr, sample_rate, meta, _ok, pw = synth_best(
                        tts, args, ref_wav, piece,
                        max(0.40, len(piece) / D.CHARS_PER_SEC), hole_limit, prog.log)
                    speech += meta[1]
                    warns.extend(pw)
                    line_parts.append(arr)
                    if pi < len(pieces):
                        gap_n = int(round(sample_rate * gap_ms / 1000.0))
                        line_parts.append(np.zeros((gap_n, arr.shape[1]), dtype=np.int16))
                arr = (line_parts[0] if len(line_parts) == 1
                       else np.concatenate(line_parts, axis=0))
                ratio = speech / expected
                if ratio > D.ratio_high(expected):
                    warns.append(f"整句偏长{ratio:.1f}倍(疑似重复)")
                elif ratio < 0.50:
                    warns.append(f"整句偏短{ratio:.1f}倍(疑似漏字)")
                if warns:
                    suspicious.append((stem, k, text, len(pieces), ";".join(warns)))
                dur_ms = int(round(arr.shape[0] / float(sample_rate) * 1000.0))
                cues.append((cursor_ms, cursor_ms + dur_ms, text))
                parts.append(arr)
                cursor_ms += dur_ms
                if k < len(lines):
                    gap_n = int(round(sample_rate * gap_ms / 1000.0))
                    parts.append(np.zeros((gap_n, arr.shape[1]), dtype=np.int16))
                    cursor_ms += gap_ms

            merged = parts[0] if len(parts) == 1 else np.concatenate(parts, axis=0)
            if merged.shape[0] == 0:
                raise RuntimeError("整轨为空（全部句子都未生成有效语音）")
            D.write_pcm16_wav(wav_out, sample_rate, merged)
            D.write_srt(srt_out, cues)
            prog.set(done=prog.data["done"] + 1, current_sentence="")
            prog.log(f"[{i}/{len(files)}] OK   {stem}.wav  "
                     f"{len(lines)} 句 / {cursor_ms / 1000.0:.1f}s / 用时 {time.time() - t1:.1f}s")
        except Exception as e:
            prog.set(failed=prog.data["failed"] + 1, current_sentence="")
            prog.log(f"[{i}/{len(files)}] FAIL {stem}.wav: {type(e).__name__} {str(e)[:200]}")
        finally:
            parts = []
            gc.collect()
            prog.flush()

    prog.set(state="finished", current="")
    d = prog.data
    if suspicious:
        csv_path = prog.path.parent / "suspicious.csv"
        fresh = not csv_path.exists()
        with csv_path.open("a", encoding="utf-8-sig" if fresh else "utf-8", newline="") as f:
            w = csv.writer(f)
            if fresh:
                w.writerow(["文件", "第几句", "台词", "推理次数", "问题"])
            w.writerows(suspicious)
        prog.log(f"可疑条目 {len(suspicious)} 条，已追加到 {csv_path}")
    prog.log(f"完成: 成功 {d['done']} / 跳过 {d['skipped']} / 空文件 {d['empty']} "
             f"/ 失败 {d['failed']} / 共 {d['total']}  耗时 {d['elapsed_sec'] / 60:.1f} 分钟")
    D.notify_done(
        f"{D.NOTIFY_TITLE}（GPT-SoVITS）",
        f"成功 {d['done']} / 跳过 {d['skipped']} / 空文件 {d['empty']} / 失败 {d['failed']}\n"
        f"共 {d['total']} 个，耗时 {d['elapsed_sec'] / 60:.1f} 分钟\n"
        f"可疑 {len(suspicious)} 条（见 suspicious.csv）",
    )


if __name__ == "__main__":
    sys.exit(main())
