[中文](Rust版使用手册.md) | **English**

# Y's Batch Toolkit — Rust Edition · User Manual

> **Applies to**: Y's Batch Toolkit (Rust rewrite) **v1.2.1** (Advanced / Developer authorization).
> This manual covers **how to use** the tool only; build and hardening internals are out of public scope.
> For the open-source Lite edition see [使用说明.md](使用说明.md); for a feature-by-feature comparison see [版本功能对照表.md](版本功能对照表.md) (Chinese).

---

## 1. What it is

The Rust rewrite of "Y's Batch Toolkit": a subtitle / dubbing batch toolkit built for *Ready or Not*.
**A single-file exe with no Python dependency** — it runs from any location you put it in.

---

## 2. Feature overview

| Section | Features |
|---|---|
| Common | One-click (find missing → apply Chinese → strip parentheses → strip line numbers → extract untranslated), ZH CSV split (ZH 的 csv 拆分), apply Chinese subtitles, strip parentheses, strip line numbers, export VO text, dictionary replace, content check |
| Auto flow | CSV → SRT split, strip parentheses, pick emotion from same-name audio, IndexTTS → wav; list view (RON role dropdown), resident TTS, convert to OGG, write voice |
| Unattended mode | Batch dubbing driven by `对照表.csv` (auto flow × N role folders) — **Developer** authorization only |
| Dubbing | Per-line dubbing from a given SRT directory (IndexTTS / GPT-SoVITS), pick audio individually, 8-dimension emotion vector, preview, original audio, one-click dub |
| Less-used tools | Find missing, extract untranslated, proofread VOtxt count, merge CSV, WAV → OGG, strip language suffix, VOerror dubbing (both models) |
| Directory settings | Workspace dir (auto-derives sub-paths), model root dirs, simple mode |

### Relationship to the previous Python edition

- The config file keeps the same path `%APPDATA%\YYNTools\config.json` with **identical field names** — an old config works as-is.
- Text-tool output is **byte-for-byte identical** to the Python edition (verified by 11 automated parity checks).
- IndexTTS inference runs through the resident service `tts_resident.py`: the model is loaded **once**, and every later batch reuses it.

---

## 3. Usage

Just run the single-file exe (`YsDubbingTool.exe`); no installation is needed.

### 1) First-time setup (left column "Directory settings (目录设置)")

1. **Workspace dir (工作区目录)**: the root for all output and helper files. Once set, it auto-creates and derives
   `VOtxt / VOerror / VOdub / translate / 词表.txt / ffmpeg\ffmpeg.exe`
2. **IndexTTS root (IndexTTS 根目录)**: point it at your `indexTTS2` installation (containing `.venv\Scripts\python.exe` and `checkpoints`)
3. **GPT-SoVITS dir (GPT-SoVITS 目录)**: point it at that installation (containing `runtime\python.exe`, `wavs`, `temp.txt`)
4. **Voice dir (音色目录)**: the wav voice library (used by IndexTTS); with the GPT model selected the tool instead reads `<GPT-SoVITS dir>\wavs` + `temp.txt`

External prerequisites for dubbing (shipped with the models, **not distributed by this tool**):

- A local IndexTTS 2.5 / GPT-SoVITS installation with its `.venv` interpreter
- ffmpeg (for WAV → OGG), path stored in the `ffmpeg` config field

### 2) Quick start (shortest path)

```
1. Directory settings → Workspace dir = where you want all output
2. Top: Source dir = the directory holding sub_zh.csv and the role folders
   (Output dir is the SRT output root and is derived from the workspace by default)
3. Click "ZH CSV split (ZH 的 csv 拆分)" → you get SRTs
4. In "Dubbing (配音工具)" fill Dubbing folder / Voice dir / IndexTTS root;
   pick Model = IndexTTS 2.5, then pick a voice
5. Click "Start (开始)" → wav files are produced and converted to OGG automatically
```

### 3) Config fields (`%APPDATA%\YYNTools\config.json`)

| Field | Meaning |
|---|---|
| workspace | Workspace root (changing it derives the 5 items below) |
| source / target | Source dir (holding ogg and sub_zh.csv) / SRT output root |
| votxt / voerror / vodub / translate / dict | Sub-paths derived from workspace |
| ffmpeg | Full path to ffmpeg.exe (derived from workspace) |
| temp_txt | GPT-SoVITS `temp.txt` (reference-text library) |
| gptsovits / itts_root | Installation roots of the two models |
| api_url | GPT-SoVITS api_v2 address (for VOerror dubbing; default 127.0.0.1:9880) |
| dub_in / dub_voice_dir / dub_out | Dubbing folder / voice dir / output path |
| dub_model | IndexTTS 2.5 or GPT-SoVITS v2Pro |
| dub_voice | Currently selected voice (display name) |
| dub_emo_on / dub_emo_weight | Emotion switch / strength (0–1) |
| dub_emo8_on / dub_e8_* | 8-dimension vector switch / per-dimension values (happy angry sad fear disgust low surprise neutral) |
| dub_emo_ref | Refer to original voice (use same-name original audio as emotion reference) |
| dub_pick_on / dub_pick_files | Pick-audio-individually switch / selected file list (`\|` separated) |
| dub_voice_order | Voice order table path (PD group pinned on top, the rest sorted by the table) |
| auto_in / auto_root_in | Auto-flow input dir / unattended master input root |
| auto_emo_weight / auto_resident | Auto-flow emotion strength / resident TTS switch |
| ron_dir / ron_opt | Pending-dubbing root / list-view switch |
| simple_mode | Simple mode (address bar keeps only workspace + TTS paths) |

### 4) Helper files in the workspace (created or read by the tool)

| File | Purpose |
|---|---|
| 对照表.csv | Role → voice mapping (3 columns: role, voice, old voice). Written automatically when Auto flow hits "Start"; Unattended mode batches over it |
| 列表视图表名.csv | Two columns "folder name, display name" — shown in the list-view dropdown as the level's translated name (optional; without it only folder names are shown) |
| 词表.txt | Dictionary replacement rules, one `"old","new"` pair per line |
| sound-askuser.wav | Completion chime (auto-generated from embedded resources when missing) |
| progress.json / run.log | Dubbing batch progress (in the auto-flow output dir, read by the monitor window) |
| suspicious.csv | Appended log of suspicious entries found during dubbing QC |

---

## 4. Directories and output

| Output | Location |
|---|---|
| Split subtitle SRTs | `<output dir>\<source folder name>\*.srt` |
| Script (台本) SRTs | `<output path>\台本\<role name>\` |
| Dubbed srt / wav / ogg | `<output path>\dub\{srt,wav,ogg}\<role name>\` |
| Unattended-mode output | `<output path>\Auto\<role name>\` |
| Workspace helper dirs | `<workspace>\VOtxt\ · VOerror\ · VOdub\ · translate\` |
| Run log | The "Log (日志)" pane at the bottom of the UI |

> `<role name>` is the **folder name** of the dubbing folder (or of the directory holding the selected audio), not a full path.
> `<output path>` (config key `dub_out`) defaults to `<workspace>\output`.

---

## 5. External dependencies and licensing

- This tool **does not bundle or distribute** any model weights or ffmpeg; install them yourself and comply with their licenses.
- Third-party components: IndexTTS 2.5 (Apache-2.0), GPT-SoVITS v2Pro (MIT), ffmpeg (LGPL / GPL).
- **Lite (this repository)** is released under GPL-3.0-or-later; the Rust edition described here is the
  **Advanced / Developer** authorization build — see [版本功能对照表.md](版本功能对照表.md) for the differences.
