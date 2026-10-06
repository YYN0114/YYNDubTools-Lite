<img src="assets/icon.png" alt="YYNDubTools-Lite" width="150">

# YYNDubTools-Lite · YYN0114配音工具(Lite)

> 字幕与配音的批处理工具：**sub_zh.csv → 台本 srt → 配音 → OGG**。
> A local, offline batch toolkit for subtitles & dubbing.

**English overview → [jump](#english-overview)**

---

## 简介

可一体化输入(包括拆解游戏自带字幕文件)，并逐句克隆配音成整轨音频、转 OGG —— 全流程在**本地**完成，
不联网、不上传。**单文件 exe**，放到任意位置即可运行。

- **字幕线**：csv 拆分 / 汉化 / 去括号 / 去标号 / 词表替换 / 查错 / 导出VO文本 / 查找缺失 / 提取未译
- **配音线**：IndexTTS 2.5（Apache-2.0）、GPT-SoVITS v2Pro（MIT）双后端；逐句克隆 + 情感控制
- **情感**：可用「同名原音频」当情感参考，或用 8 维情感向量（高兴/愤怒/悲伤/恐惧/反感/低落/惊讶/自然）
- **批量**：常驻 TTS 服务（模型只加载一次）、对照表批量配音、状态指示灯、紧急中止
- **提醒**：批次结束 → 本机提示音 + 手机 ntfy 推送

## 初衷

本工具**最初是为Ready or Not的一个汉化配音开发**。
故许多功能、设置对此高度优化

- **Mod 主页（Nexus Mods）**：<https://www.nexusmods.com/readyornot/mods/7675>
- **Mod 名称**：Chinese Or Not（中文与否）　**作者**：YYN0114
- **作者 B 站**：<https://space.bilibili.com/1800421262>

配音流程跑通之后，工具被抽离成通用版本：字幕处理、情感控制、批量配音等功能都可脱离该 Mod 单独使用。

## 环境要求

| 项 | 要求 |
| --- | --- |
| 系统 | Windows 10 / 11（64 位） |
| 显卡 | 建议 8GB 显存起（IndexTTS 本地推理） |
| 配音后端 | IndexTTS 2.5 模型根目录（含 `checkpoints\`）；可选 GPT-SoVITS |
| 音频转换 | ffmpeg.exe（wav → ogg） |

> 模型、ffmpeg 等第三方组件**不随本软件分发**，需自行安装。

## 安装 / 运行

1. 下载 `YYN0114配音工具(Lite).exe`，放到任意目录。
2. 双击运行。首次启动所有目录为空，会提示先设「工作区目录」。
3. 设好「工作区目录」后，其下 7 条子路径自动推导并创建：`source` / `srt` / `voices` / `output` / `votxt` / `dict.txt` / `ffmpeg\ffmpeg.exe`。
4. 「目录设置」里默认勾选 **简略模式**，只显示「工作区目录 + TTS 路径」；取消勾选可看到全部地址项。

配置保存在 `%APPDATA%\YYNTools\config_lite.json`；删除该文件即可恢复初始状态。

## 快速上手

```
① 目录设置 → 工作区目录 = 你想放所有产物的位置
② 点「ZH 的 csv 拆分」        → 得到 srt
③ 配音工具填：配音文件夹 / IndexTTS 根目录（音色目录、ffmpeg.exe 已由工作区自动推导）
④ 模型选 IndexTTS 2.5 → 选音色 → 点「开始」
⑤ 成品在 工作区\output\dub\{wav,ogg}\<角色名>\
```

完整操作见 **[使用说明.md](使用说明.md)**。

## 目录与产物

| 产物 | 位置 |
| --- | --- |
| 拆出的字幕 srt | `输出目录\<源文件夹名>\*.srt` |
| 台本 srt | `输出路径\script\<角色名>\` |
| 配音 srt / wav / ogg | `输出路径\dub\{srt,wav,ogg}\<角色名>\` |
| 导出VO文本 | `工作区目录\votxt\` |

## 许可

本软件以 **GNU GPL v3 或任何更新版本（GPL-3.0-or-later）** 发布，为自由软件：
可自由使用、修改与再分发；**分发衍生作品须同样以 GPL 开源**；按「现状」提供，不含任何担保。
许可全文见 [LICENSE](LICENSE)，或 <https://www.gnu.org/licenses/gpl-3.0.html>。

## 第三方组件

- **exe 内嵌（随包分发）**：Python 运行时（PSF-2.0）、Tcl/Tk（BSD 风格）、tkinterdnd2（MIT）、PyInstaller bootloader（GPL-2.0 + Bootloader 例外）。
- **不随包分发、需自行安装**：IndexTTS 2.5（Apache-2.0）、GPT-SoVITS（MIT）、ffmpeg（LGPL/GPL）。

详见 [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt)。

---

## English overview

**YYNDubTools-Lite** (YYN0114 Dubbing Toolkit) is a **local, offline batch toolkit** for subtitles and dubbing on Windows.
It turns a dialogue table (`sub_zh.csv`) into per-line SRTs, synthesizes cloned speech line by line into a
single audio track, and converts the result to OGG — everything runs on your own machine.

- **Subtitles**: CSV split, apply Chinese, strip parentheses, strip line numbers, dictionary replace,
  content check, export VO text, find missing, extract untranslated.
- **Dubbing**: IndexTTS 2.5 and GPT-SoVITS v2Pro backends; per-line voice cloning with emotion control
  (same-name reference audio, or an 8-dimension emotion vector).
- **Batch**: a resident TTS service (load the model once), comparison-table batch dubbing, a status LED,
  emergency abort, and end-of-batch alerts (local sound + phone push via ntfy).

**Requirements**: Windows 10/11 (64-bit), a GPU with ~8 GB VRAM recommended, IndexTTS 2.5 (or GPT-SoVITS)
installed locally, and ffmpeg for OGG output. Model weights and ffmpeg are **not bundled**.

**Origin**: this tool was originally built for the *Ready or Not* Chinese localization mod
[**Chinese Or Not**](https://www.nexusmods.com/readyornot/mods/7675) by YYN0114 — its per-line voice
dubbing pipeline is what the tool was designed for. It later became a general-purpose toolkit.

**License**: GNU GPL v3 or any later version. See [LICENSE](LICENSE).
**Third-party notices**: [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
**Full manual (Chinese)**: [使用说明.md](使用说明.md).
