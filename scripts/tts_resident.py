#!/usr/bin/env python
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""IndexTTS 2.5 常驻配音服务：模型只加载一次，之后反复接收合成请求。

用途
----
供「Y's批处理工具」的自动流程使用（dub_itts.py 带 --api-url 时走本服务）。
不经过 Gradio / pyvideotrans 中转，直接把 IndexTTS2 内核挂在一个极简 HTTP 服务上，
自动流程需要的参数全部保留：同名音频当情感参考、八维情感向量、情感强度、seed。

接口（请求/响应都是 JSON）
----
  GET  /health    -> {"ok": true, "state": "ready"}
  POST /synth     -> {"text","voice","emo_audio","emo_weight","emo_vector","seed",
                      "language","max_mel_tokens"}
                     返回 {"ok":true,"sample_rate":24000,"capped":false,"wav_b64":"..."}
  POST /shutdown  -> {"ok": true}，随后进程退出

输出
----
启动后写一个登记文件（默认 %TEMP%\\YYNTools\\tts_resident.json）记录 pid / port，
外部（GUI 的「关闭TTS」）即使丢失进程句柄，也能据此关闭服务。

常用参数 / 示例
----
  --port      监听端口（默认 9882）
  --model-dir checkpoints 目录（含 config.yaml，必填）
  --precision 精度：auto / bf16 / fp16 / fp32（默认 bf16）

  .venv\\Scripts\\python.exe tts_resident.py --port 9882 ^
      --model-dir <模型目录>\\indexTTS2\\checkpoints ^
      --precision bf16
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import threading
import time
import traceback
import warnings
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MARKER = Path(os.environ.get("TEMP", str(Path.home()))) / "YYNTools" / "tts_resident.json"

TTS = None                      # 全局唯一的模型实例（常驻进程里只加载这一次）
LOCK = threading.Lock()         # 模型不能并发推理：一次只放一个请求进去
STATE = {"state": "loading", "loaded_at": ""}


class GuardedStream:
    """stdout/stderr 的替身：管道断了就把内容转存到日志文件，绝不往外抛。

    常驻服务的本质是"活得比 GUI 久"，而 GUI 是用管道读它的输出的。GUI 一退，
    管道读端就没了，此后任何 print 在 Windows 上都会抛 OSError([Errno 22])。
    模型内核里（infer_v2_5.py）有裸 print，一旦抛出整次合成就是 HTTP 500，
    所以必须在这里兜住：写不出去就改写到日志文件。
    """

    def __init__(self, stream, fallback: Path):
        self._stream = stream
        self._fallback = fallback
        self._fh = None
        self._dead = False

    def _sink(self):
        if self._fh is None:
            try:
                self._fh = open(self._fallback, "a", encoding="utf-8", buffering=1)
            except Exception:
                self._fh = False        # 日志文件也开不了：彻底静默，别再引发异常
        return self._fh

    def write(self, s):
        if not self._dead:
            try:
                self._stream.write(s)
                self._stream.flush()
                return
            except Exception:
                self._dead = True       # 管道断了，之后全部走文件
        fh = self._sink()
        if fh:
            try:
                fh.write(s)
            except Exception:
                pass

    def flush(self):
        if not self._dead:
            try:
                self._stream.flush()
            except Exception:
                self._dead = True
        fh = self._fh
        if fh:
            try:
                fh.flush()
            except Exception:
                pass

    def isatty(self):
        try:
            return self._stream.isatty()
        except Exception:
            return False

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_stream_guard() -> None:
    """把 sys.stdout / sys.stderr 换成 GuardedStream（日志文件落在登记文件旁边）。"""
    fallback = MARKER.with_name("tts_resident.log")
    sys.stdout = GuardedStream(sys.stdout, fallback)
    sys.stderr = GuardedStream(sys.stderr, fallback)


def log(msg: str) -> None:
    # 调用方（GUI）可能已经关掉，管道断掉不该把常驻服务一起带走
    try:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    except Exception:
        pass


# ------------------------------------------------------------------ 完成提醒
# 与 dub_itts.py 保持一致：同一个 ntfy 主题、同一个提示音、同一条延迟策略。
# 系统提示音：随包分发的 CC0 音效（与脚本同目录）
NOTIFY_SOUNDS = [
    Path(__file__).with_name("sound-askuser.wav"),
]


def _pick_notify_sound():
    """返回第一个存在的提示音文件；都不存在时返回 None（调用方回落 MessageBeep）。"""
    for p in NOTIFY_SOUNDS:
        if p.is_file():
            return p
    return None
NTFY_SERVER = "https://ntfy.sh"
# 手机 ntfy App 订阅的主题：由 GUI 通过环境变量 YYN_NTFY_TOPIC 传入；留空 = 不推手机
NTFY_TOPIC = os.environ.get("YYN_NTFY_TOPIC", "").strip()
NOTIFY_DELAY_MS = 800


def notify(title: str, message: str, tags=None) -> None:
    """手机 ntfy 推送与系统提示音并发发起；任何一步失败都不影响服务本身。"""
    import threading

    def _push() -> None:
        if not NTFY_TOPIC:
            log("未设置 ntfy 主题，跳过手机推送")
            return
        try:
            import urllib.request
            payload = json.dumps({
                "topic": NTFY_TOPIC,
                "title": title,
                "message": message,
                "tags": list(tags or ["white_check_mark"]),
            }, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                NTFY_SERVER, data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10).read()
            log(f"已推送手机提醒：{title}")
        except Exception as e:
            # 记录手机推送失败结果，便于排查
            log(f"ntfy 推送失败：{type(e).__name__}: {e}")

    worker = threading.Thread(target=_push, daemon=True)
    worker.start()
    try:
        import winsound
        sound = _pick_notify_sound()
        if sound is None:                              # 系统媒体目录里没有可用音效 → 用系统默认提示音
            log("未找到系统提示音，改用系统默认提示音")
            if NOTIFY_DELAY_MS > 0:
                time.sleep(NOTIFY_DELAY_MS / 1000.0)
            winsound.MessageBeep()
        else:
            log(f"本机提示音：{sound}")                 # 打印实际播放的文件，便于核对
            if NOTIFY_DELAY_MS > 0:
                time.sleep(NOTIFY_DELAY_MS / 1000.0)   # 本地延迟，与手机对齐
            winsound.PlaySound(str(sound), winsound.SND_FILENAME)
    except Exception as e:
        log(f"本机提示音失败：{type(e).__name__}: {e}")
    worker.join(timeout=12)


def resolve_precision(torch_module, requested: str, device: str) -> tuple[bool, bool, str]:
    """与 dub_itts.py 同一套精度判定：仅 CUDA 下区分 bf16/fp16，否则 fp32。"""
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


def synth(req: dict) -> dict:
    """按请求合成一段音频，返回 WAV 的 base64。"""
    import numpy as np
    import torch

    text = (req.get("text") or "").strip()
    if not text:
        raise ValueError("text 为空")

    voice = req.get("voice") or ""
    if not os.path.isfile(voice):
        raise FileNotFoundError(f"音色文件不存在: {voice}")

    emo_audio = req.get("emo_audio") or None
    if emo_audio and not os.path.isfile(emo_audio):
        raise FileNotFoundError(f"情感参考音频不存在: {emo_audio}")

    # 内核规定：emo_vector 不为 None 时会把 emo_audio_prompt 置 None，二者只能用一个
    if emo_audio:
        emo_kw = {"emo_audio_prompt": str(emo_audio), "emo_vector": None}
    else:
        emo_kw = {"emo_vector": req.get("emo_vector")}

    max_mel = int(req.get("max_mel_tokens", 1500))
    with LOCK:
        # IndexTTS 2.5 的 infer() 不收 seed，靠给全局随机数播种来复现（与 dub_itts.py 一致）
        torch.manual_seed(int(req.get("seed", 42)))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = TTS.infer(
                spk_audio_prompt=str(voice),
                text=text,
                output_path=None,
                lang=req.get("language", "ZH"),
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
                emo_alpha=float(req.get("emo_weight", 0.65)),
                **emo_kw,
            )
        # 撞满 max_mel_tokens 会 warn(RuntimeWarning)，那是"跑飞"的直接证据，回传给调用方
        capped = any("max_mel_tokens" in str(w.message) for w in caught)

    if not (isinstance(result, tuple) and len(result) == 2):
        raise RuntimeError(f"推理未返回音频数据: {type(result).__name__}")
    sample_rate, wav_data = result
    arr = np.asarray(wav_data)
    if arr.ndim == 1:
        arr = arr[:, None]
    if arr.dtype != np.int16:
        arr = arr.astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(int(arr.shape[1]))
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(arr.tobytes())
    return {
        "sample_rate": int(sample_rate),
        "capped": bool(capped),
        "wav_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] in ("/health", "/"):
            return self._json({"ok": True, **STATE})
        self._json({"ok": False, "msg": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception as e:
            return self._json({"ok": False, "msg": f"请求解析失败: {e}"}, 400)

        if path == "/shutdown":
            self._json({"ok": True})
            log("收到 shutdown，退出")
            # 等提醒发完（含系统播声）再退：进程一旦退出，声音会被中断
            threading.Thread(
                target=lambda: (notify("TTS 服务已关闭",
                                       "显存已释放；下次配音需要重新加载模型", ["zzz"]),
                                self.server.shutdown()),
                daemon=True).start()
            return
        if path != "/synth":
            return self._json({"ok": False, "msg": "not found"}, 404)

        t0 = time.time()
        try:
            out = synth(req)
        except Exception as e:
            # 完整堆栈写到日志；响应里带最后两帧，客户端能把失败原因显示出来
            tb = traceback.format_exc()
            log(f"合成失败：{type(e).__name__}: {e}\n{tb}")
            return self._json(
                {"ok": False, "msg": f"{type(e).__name__}: {e}",
                 "trace": "".join(tb.strip().splitlines(keepends=True)[-4:])},
                500)
        log(f"合成「{(req.get('text') or '')[:16]}」耗时 {time.time() - t0:.1f}s")
        self._json({"ok": True, **out})

    def log_message(self, fmt, *a):
        pass


def main() -> int:
    global TTS

    # 先装输出保护：服务要比 GUI 活得久，GUI 退出后管道即断
    install_stream_guard()

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9882)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model-dir", required=True, help="checkpoints 目录（含 config.yaml）")
    ap.add_argument("--device", default=None)
    ap.add_argument("--precision", default="bf16", choices=["auto", "bf16", "fp16", "fp32"])
    args = ap.parse_args()

    # 先写登记文件：正在加载模型时也要能被「关闭TTS」找到并杀掉
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(
        json.dumps({"pid": os.getpid(), "port": args.port,
                    "started": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False),
        encoding="utf-8",
    )
    log(f"常驻服务启动 pid={os.getpid()} port={args.port}")

    # 模型根目录 = checkpoints 的上一级（内含 indextts 包），加入 sys.path 以便导入
    node_dir = Path(args.model_dir).resolve().parent
    if str(node_dir) not in sys.path:
        sys.path.insert(0, str(node_dir))
    import torch
    from indextts.infer_v2_5 import IndexTTS2

    device = args.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    use_bf16, _, effective = resolve_precision(torch, args.precision, device)
    model_dir = Path(args.model_dir).resolve()
    if not (model_dir / "config.yaml").is_file():
        log(f"模型目录不完整（缺 config.yaml）: {model_dir}")
        notify("TTS 服务启动失败", f"模型目录不完整（缺 config.yaml）\n{model_dir}", ["warning"])
        try:
            MARKER.unlink()
        except Exception:
            pass
        return 1

    t0 = time.time()
    log(f"正在加载模型 {model_dir} device={device} precision={effective} …")
    try:
        TTS = IndexTTS2(
            cfg_path=str(model_dir / "config.yaml"),
            model_dir=str(model_dir),
            use_bf16=use_bf16,
            device=device,
            use_cuda_kernel=False,
            use_qwen_emo=False,
        )
    except Exception as e:
        log(f"模型加载失败：{type(e).__name__}: {e}")
        notify("TTS 服务启动失败", f"模型加载失败：{type(e).__name__}: {e}", ["warning"])
        try:
            MARKER.unlink()
        except Exception:
            pass
        return 1
    STATE["state"] = "ready"
    STATE["loaded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    log(f"模型就绪，用时 {time.time() - t0:.0f}s → http://{args.host}:{args.port}")
    notify("TTS 服务已就绪",
           f"模型加载 {time.time() - t0:.0f}s\n{args.host}:{args.port}\n下一批配音可立即开始（不再等加载）",
           ["rocket"])

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            MARKER.unlink()
        except Exception:
            pass
        log("已停止")
    return 0


if __name__ == "__main__":
    try:
        _code = main()
    except Exception as _e:          # 服务跑到一半挂了，手机也要知道
        log(f"服务异常退出：{type(_e).__name__}: {_e}")
        notify("TTS 服务异常退出", f"{type(_e).__name__}: {_e}", ["warning"])
        _code = 1
    sys.exit(_code)
