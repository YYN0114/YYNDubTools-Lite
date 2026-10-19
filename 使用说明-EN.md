[中文](使用说明.md) | **English**

# YYN0114 Dubbing Toolkit (Lite) — User Manual

> A batch tool for subtitles and dubbing: **sub_zh.csv → script srt → dubbing → OGG**, plus handy subtitle-processing buttons.
> A single-file exe — it runs from any location you put it in; settings are stored in `%APPDATA%\YYNTools\config_lite.json`.
> This repository is the **open-source Lite edition**, released under **GPL-3.0 or later** (see "八、License and Third-Party Components" at the end).
>
> In this document all directories are written in the **`<placeholder>`** form, e.g. `<workspace>\voices`;
> `<workspace>` = the directory you filled in under "Workspace dir"; `<source dir>` / `<output dir>` / `<output path>` / `<dubbing folder>` / `<GPT-SoVITS dir>` / `<IndexTTS root>` likewise all refer to the value you filled in on the UI.
> `<source folder name>` / `<role name>` = the **folder name** of the corresponding folder, not the full path.

---

## 一、First use: set the paths

### 1) The two boxes at the top (most used)

| Name | What to fill in |
| --- | --- |
| **Source dir (源目录)** | The directory that holds `sub_zh.csv` (the line table) and the role folders. The program reads **`<source dir>\sub_zh.csv`** |
| **Output dir (输出目录)** | The output root for srt. Files are actually written to **`<output dir>\<source folder name>\xxx.srt`** |

> The source dir may be a single role folder; `sub_zh.csv` is inside it.
> These two items are by default auto-derived from "Workspace dir" (see below); you can also change them manually, but **changing "Workspace dir" once more will overwrite them**.

### 2) The left column "▸ Directory Settings (address bar) (目录设置（地址栏）)" (collapsed by default; click the title to expand)

> **On first launch all directories are empty**, and a dialog pops up reminding you to set them. **You must at least set "Workspace dir" first**, otherwise nothing can run.

**"Simply mode (简略模式)" checkbox (on by default, at the top of this panel)**: when checked, this panel shows only the three rows **Workspace dir (工作区目录) / GPT-SoVITS dir (GPT-SoVITS 目录) / IndexTTS root (IndexTTS 根目录)**; the other address items (Voice dir (音色目录), Output path (输出路径), Voice order table (音色顺序表), Pending dubbing dir (待配音目录), Mobile push topic (手机推送主题)) are hidden automatically.
Hiding only means not showing — **the configuration values are kept as usual and the functions still take effect**; unchecking restores them exactly as they were.

**Workspace dir** is the one and only master switch for directories (recommended: `%USERPROFILE%\YYNtools`). Change it in one place, and the 7 sub-paths below are immediately recomputed and their directories are created automatically:

| Derived from workspace | Actual path | Used for |
| --- | --- | --- |
| Source dir | `<workspace>\source` | "Source dir" at the top |
| Output dir | `<workspace>\srt` | "Output dir" at the top |
| Voice dir | `<workspace>\voices` | Voice dropdown scanning (see "四、Voices") |
| Output path | `<workspace>\output` | Dubbing outputs |
| votxt | `<workspace>\votxt` | Export VO text |
| dict.txt | `<workspace>\dict.txt` | Word-list replacement |
| ffmpeg.exe | `<workspace>\ffmpeg\ffmpeg.exe` | wav → ogg |

The rest must be filled in manually (external tools / input directories, not part of the workspace) — among them "Voice order table / Pending dubbing dir / Mobile push topic" are **hidden by default in Simply mode**, and become visible after unchecking "Simply mode":

| Name | What to fill in | Used for |
| --- | --- | --- |
| **Voice order table (音色顺序表)** | A txt with one voice file name per line, used to fix the order in the dropdown. See "四、Voices" for details. **May be left empty** | Voice ordering |
| **GPT-SoVITS dir (GPT-SoVITS 目录)** | The GPT-SoVITS installation root (it must contain `temp.txt` and `api.bat` below it) | Used when selecting a GPT model |
| **IndexTTS root (IndexTTS 根目录)** | The IndexTTS2 model root, which must contain `checkpoints\` below it | IndexTTS dubbing |
| **Pending dubbing dir (待配音目录)** | The **root directory** of a batch of folders pending dubbing (with a bunch of folders below it). Used when "List view" is checked | Quickly switch dubbing folder |
| **Mobile push topic (手机推送主题)** | The channel name of ntfy.sh (subscribe to the same channel in the ntfy App on your phone). **Empty = no phone push**, only the local notification sound | Phone reminder when a batch finishes |

> **Dubbing folder** has already been moved to the left column "▸ Dubbing Tools" area (next to the "List view" checkbox); you can browse / drag in / type it directly.

**To run IndexTTS dubbing, at least these 3 must have values**: `Dubbing folder`, `Voice dir` (already automatic), `IndexTTS root`; to get OGG you also need to put ffmpeg at `<workspace>\ffmpeg\ffmpeg.exe`.

---

## 二、Main flow A: from csv to finished subtitles (srt)

1. Fill in **Source dir** (containing `sub_zh.csv`) and **Output dir** at the top.
2. In the right column, click **"Separate ZH csv (ZH 的 csv 拆分) (sub_zh.csv → multiple srt)"**
   - It will: split `sub_zh.csv` by Key into multiple srt → **automatically remove parentheses**
   - Output: `<output dir>\<source folder name>\*.srt`
3. If needed, click the single-step buttons (you can click them repeatedly; nothing is generated twice):
   - **Chinese-ify subtitles (汉化字幕)**: fill the Chinese into the srt according to the csv
   - **Remove parentheses (去除括号)**: delete lines that contain only parenthesized content
   - **Remove numbering (去除标号)**: strip the line numbers at the start of lines
   - **Word-list replacement (词表替换)**: perform replacement using `<workspace>\dict.txt`
   - **Check errors (检查错误)**: scan the content for problems and print the results in the log
   - **Export VO text (导出VO文本)**: export to `<workspace>\votxt\`
4. To do it all in one step, click **"★ One-click / auto-troubleshoot, import & Chinese-ify (★ 一键版 / 自动排障、导入汉化)"**
   - The internal order is fixed: **Find missing (查找缺失) → Chinese-ify subtitles → remove parentheses → remove numbering → Extract untranslated (提取未译)**

---

## 三、Main flow B: from srt to finished dubbing (wav + ogg)

1. In the left column "▸ Dubbing Tools (配音工具)" area, from top to bottom:
   - **▸ Model (模型)** (pinned at the top, collapsed by default, click the title to expand): use the **Model** dropdown to choose `IndexTTS 2.5` (the GPT model requires your own API service)
   - **Voice (音色)**: choose a voice from the dropdown (**how to add voices, see "四、Voices"**); at the right of the row, **"Original audio (原声)"** = directly play the reference audio of that voice; **"Preview (试听)"** = synthesize one sentence with that voice and play it (with no emotion added)
2. Fill in **Dubbing folder** (the directory containing the srt files to dub — the one produced in step 2).
   - You can click "Browse (浏览)" to pick a directory / drag it in / type it manually;
   - If **Pending dubbing dir** is already set (in "Directory Settings"), you can check **"List view (列表视图)"**: the dubbing folder turns into a folder dropdown showing only folder names; pick one and the path is filled in (click "Refresh (刷新)" to rescan).
3. Adjust emotion (optional, IndexTTS only) — the "▸ Emotion (only effective for IndexTTS) (▸ 情绪（仅 IndexTTS 有效）)" sub-panel:
   - Turning off the checkbox at the very top of the sub-panel = add no emotion at all; turning it on lets you control the intensity with the "Emotion intensity (情感强度)" slider
     - `0` = fully keep the voice's own emotion; `1` = fully apply the eight-direction vector below
   - **Refer to original voice (按原音色参考)** (top of the emotion sub-panel): when checked, look in each srt's own directory for an **ogg/wav/mp3/flac with the same name** to use as the emotion reference; if not found, fall back to the "eight-direction" vector
   - **Eight directions (八向)**: Happy / Angry / Sad / Fearful / Disgusted / Depressed / Surprised / Neutral (高兴 / 愤怒 / 悲伤 / 恐惧 / 反感 / 低落 / 惊讶 / 自然), 8 sliders 0~1
     - Actual value = slider × the "Emotion intensity" above
4. **Resident mode (常驻模式)** (on by default, IndexTTS only):
   - Checked = start a resident TTS service when dubbing so that **the model is loaded only once** and is not shut down after a run → the next batch opens instantly
   - Unchecked = load it yourself each time and release it after the run
   - The adjacent **"Close TTS (关闭TTS)"** = manually close the resident service and free VRAM
5. **Status indicator light (状态指示灯)** (inside "Dubbing Tools" in the left column, refreshes every 5 seconds):
   - Gray = everything normal; Orange = the service is loading the model; Red = emotion is 0 or <0.5 / resident mode is checked but the service is not running / the last batch had skips or failures
   - The text below shows: emotion value, resident status, last-batch processing statistics
6. Click **"Start (开始)"**
   - Flow: dubbing → produce wav → **automatically convert to OGG**
   - When the emotion intensity is below 0.5, a confirmation dialog appears first (clicking "Cancel" means it won't run)

### Only want to dub a few audio files? Use "Select audio individually (单独选音频)"

1. Check **"Select audio individually (单独选音频) (OGG/WAV; when checked, it overrides 'Dubbing folder')"**
2. Click **"Select files (选择文件)"** → multi-select audio (may span directories)
   - Requirements: **the directory where the selected audio files live must contain `sub_zh.csv`**, and the audio file names must equal the Keys in the csv
   - When selecting across directories, the script and the outputs are all stored under the **role name of the first directory**
3. Click **"Start"**
   - Flow: split csv (only the selected ones) → remove parentheses → dub → convert to OGG
   - This feature **supports IndexTTS only**
4. To cancel, click the adjacent **"Clear (清空)"** and uncheck the box.

---

## 四、Voices: how to add and how to order

> Each item in the dropdown = one reference audio scanned from the "Voice dir".
> **Adding a voice = dropping a file into the voice dir**; this tool has **no** "New voice" UI button, nor a "Refresh voices" button.

### 1) IndexTTS 2.5 (default)

- The voice dir defaults to **`<workspace>\voices`** (it points here automatically once "Workspace dir" is set; the directory is created automatically).
- Just put **`.wav` reference audio** into it; **subfolder grouping is supported**:
  - Scanning is **recursive**: `.wav` files at **all levels** under `<workspace>\voices` are scanned (`.ogg` / `.mp3` / `.flac` do not count).
  - The dropdown shows the **path relative to the voice dir**:
    - Placed directly at the root → `低沉中男.wav`
    - Placed in a subfolder → `PD\低沉中男.wav`
- **Ordering rules** (from first to last):
  1. **Voices in the `PD` subfolder always come first** (judged by the first-level folder name, case-insensitive);
  2. Then by the order listed in the **"Voice order table"**;
  3. Those not listed in the order table are placed last, in the raw scanned order.
- **"Voice order table"** (optional; filled in under "▸ Directory Settings"): a txt with **one voice file name per line**, used to fix the dropdown order.
  - Just write the **file name stem** (e.g. a line `低沉中男`); the suffix and letter case are not case-sensitive;
  - Content after `#` on a line is ignored (it can serve as a comment);
  - Empty = no ordering (raw order, apart from PD pinned at the top).

### 2) GPT-SoVITS (optional, requires your own API service)

When a GPT model is selected, voices **do not use the wav directory**; instead **`<GPT-SoVITS dir>\temp.txt`** is read:

- The "Voice dir" then defaults to **`<GPT-SoVITS dir>\wavs`** (for reference list display only);
- Each line of `temp.txt` is one voice, divided into three segments by `#`:

  ```
  relative path#reference text#language
  ```

  - Segment 1 `relative path` (相对路径): the audio path relative to **`<GPT-SoVITS dir>`**, e.g. `wavs\低沉中男.wav`;
  - Segment 2 `reference text` (参考文本): the **text content** corresponding to this audio;
  - Segment 3 `language` (语种): may be left empty;
  - **Lines that only have a path and no reference text (segment 2 empty) are ignored** and will not appear in the dropdown;
  - Lines starting with `#` are comments.

### 3) How do I add voices in Simply mode?

**Just drop files as usual — Simply mode only hides those rows; the values are unchanged and the functions work as usual.**

- Simply mode is on by default; in that state "Directory Settings" keeps only the three rows **Workspace dir / GPT-SoVITS dir / IndexTTS root**;
  "Voice dir / Output path / Voice order table / Pending dubbing dir / Mobile push topic" are hidden, but **the configuration is kept as usual and the functions still take effect**.
- So as before:
  - IndexTTS → drop `.wav` into **`<workspace>\voices`**;
  - GPT-SoVITS → directly edit **`<GPT-SoVITS dir>\temp.txt`**.
- To **see or hand-edit** "Voice dir" and "Voice order table": uncheck the **"Simply mode" checkbox** at the top of "Directory Settings" and the two rows come back; checking it again afterwards makes no difference (the values are kept).

### 4) Newly added audio doesn't appear in the dropdown?

The dropdown only rescans at three moments: **① After changing "Voice dir", press Enter or click elsewhere ② Switching the "Model" dropdown ③ Restarting the software**.
The easiest way is to **switch the "Model" dropdown and switch back**. (The software has **no** "Refresh voices" button.)

---

## 五、Where the outputs are (path summary table)

| Output | Location |
| --- | --- |
| Split subtitle srt | `<output dir>\<source folder name>\*.srt` |
| Script srt | `<output path>\script\<role name>\` |
| Dubbing srt | `<output path>\dub\srt\<role name>\` |
| Dubbing wav | `<output path>\dub\wav\<role name>\` |
| Final ogg | `<output path>\dub\ogg\<role name>\` |
| Exported VO text | `<workspace>\votxt\` |
| Run log | The "Log (日志)" area at the bottom of the software |

> "Role name" = the folder name of the dubbing folder (or of the directory containing the selected audio).
> "Output path" defaults to `<workspace>\output`.

---

## 六、Cautions

- **Don't modify the original files**: Chinese-ify / remove parentheses / remove numbering / word-list replacement all **overwrite the srt in place**; back up first before running.
- **Before dubbing, close anything that eats VRAM** (games, AI drawing/rendering, etc.), otherwise they may compete for VRAM and cause failures.
- **To stop midway**: click **"Emergency abort (紧急中止)"** above the log area; you must **click twice** (the first click changes it to "Confirm again (再次确定)"; only the second click really stops it). After aborting, this task will not produce any more output; **the resident TTS service is unaffected** and can be reused immediately next time.
- **Settings file**: `%APPDATA%\YYNTools\config_lite.json`. To restore the initial state, just delete this file.
- **First launch**: all directories are empty by default and a dialog reminds you; at least set "Workspace dir" first, and its subdirectories are created automatically.
- **Phone push**: the phone is pushed to only if you fill in "Mobile push topic" (an ntfy.sh channel name) in "Directory Settings"; if left empty, only the local notification sound plays.
- **When using a GPT-SoVITS model**: first start `<GPT-SoVITS dir>\api.bat`, and in that directory provide voice reference text via `temp.txt` (for the format see "四、Voices", section 2).
- **Grayed-out UI buttons**: while a task is running all buttons are temporarily disabled and recover automatically when it finishes.
- **Closing the window**: while a task is running a confirmation dialog appears first; "Cancel (取消)" means don't close; clicking "OK (force quit) (确定（强制退出）)" ends the dubbing sub-process first and then closes. If **the resident TTS is still running** at that point, a three-way choice pops up: **OK (确定)** = close both the exe and the service (free VRAM) / **UI only (仅UI)** = close only the exe and keep the service (opens instantly next time) / **Cancel (取消)** = don't close.

---

## 七、Get started in one minute (shortest path)

```
① "Workspace dir (工作区目录)" in "Directory Settings" = where you want all outputs (empty on first launch, must be set first)
   Once set, it is auto-derived:
   Top "Source dir" = <workspace>\source
   Top "Output dir" = <workspace>\srt
② Click "Separate ZH csv (ZH 的 csv 拆分)" → you get srt (in <output dir>\<source folder name>\)
③ In the left column "Dubbing Tools" area fill "Dubbing folder" = the directory above (or use the "List view (列表视图)" dropdown to pick quickly)
   "Voice dir (音色目录)" = default <workspace>\voices (dropping .wav here adds voices, see "四、Voices")
   "IndexTTS root (IndexTTS 根目录)" = IndexTTS2 model root
   "ffmpeg.exe" = <workspace>\ffmpeg\ffmpeg.exe (already auto-derived, no need to type)
④ Dubbing Tools: select model IndexTTS 2.5 → select a voice → click "Start (开始)"
⑤ Outputs are in <workspace>\output\dub\{wav,ogg}\<role name>\
```

---

## 八、License and Third-Party Components

### 1) Open-source license

- This software is released under the **GNU GPL v3 or any later version (GPL-3.0-or-later)** as free software: you may freely use, modify and redistribute it; **distributing derivative works must likewise be open-sourced under the GPL**; it is provided "as is", **without any warranty**.
- Full license text: the accompanying `LICENSE` file, or <https://www.gnu.org/licenses/gpl-3.0.html>.
- This repository is the **open-source Lite edition**; for the fuller-featured full version, see the release page.

### 2) Third-party components embedded in the exe (distributed with the package)

| Component | License |
| --- | --- |
| Python runtime | PSF-2.0 |
| Tcl/Tk (tkinter UI library) | BSD-style |
| tkinterdnd2 (drag-and-drop support) | MIT |
| PyInstaller bootloader | GPL-2.0 + Bootloader exception |

### 3) Components not distributed with the package, to be installed separately

| Component | License | Purpose |
| --- | --- | --- |
| IndexTTS 2.5 | Apache-2.0 | Dubbing backend |
| GPT-SoVITS v2Pro | MIT | Dubbing backend (optional) |
| ffmpeg | LGPL / GPL | wav → ogg |

> This software **does not bundle or distribute** any model weights; please install the above components yourself and comply with their licenses separately.
> For the full statement see `THIRD-PARTY-NOTICES.txt`.

### 4) About the notification sound

The local notification sound played when a batch finishes uses the `sound-askuser.wav` **distributed with the exe** (released at runtime into `%APPDATA%\YYNTools\dub_scripts\`);
if this file is missing, it automatically falls back to the system default sound (`winsound.MessageBeep()`), without affecting the flow.
