[中文](Rust版使用手册.md) | [English](Rust版使用手册-EN.md)

# Y's批处理工具 · Rust 版 使用手册

> **适用版本**：Y's批处理工具（Rust 重写版）**v1.2.1**（高级 / 开发者授权）。
> 本手册只讲**怎么用**；编译、加固等内部技术细节不在公开范围内。
> 开源精简版（Lite）见 [使用说明.md](使用说明.md)；两版功能差异见 [版本功能对照表.md](版本功能对照表.md)。

---

## 一、它是什么

「Y's批处理工具」的 Rust 重写版：Ready or Not 字幕 / 配音批处理工具集。
**单文件 exe、无 Python 依赖**，放到任意位置就能运行。

---

## 二、功能总览

| 区块 | 功能 |
|---|---|
| 常用 | 一键版（查找缺失→汉化→去括号→去标号→提取未译）、ZH 的 csv 拆分、汉化字幕、去除括号、去除标号、导出VO文本、词表替换、检查错误 |
| 自动流程 | csv 拆 srt → 去括号 → 同名音频定情感 → IndexTTS 出 wav；列表视图（RON 角色下拉）、常驻 TTS、转换OGG、写入音色 |
| 无人值守模式 | 按「对照表.csv」批量配音（自动流程 × N 个角色文件夹）※仅**开发者**授权可见 |
| 配音工具 | 指定 srt 目录逐句配音（IndexTTS / GPT-SoVITS）、单独选音频、八向情感向量、试听、原声、一键配音 |
| 不常用工具 | 查找缺失、提取未译、校对VOtxt 数量、合并CSV、WAV 转 OGG、去语种后缀、VOerror 配音（两种模型） |
| 目录设置 | 工作区目录（自动推导子路径）、各模型根目录、简略模式 |

### 与旧版（Python）的关系

- 配置文件沿用 `%APPDATA%\YYNTools\config.json`，**字段名完全一致**，旧配置直接可用（无需迁移）。
- 文本工具的输出与 Python 版**逐字节一致**（已通过 11 项自动对拍）。
- IndexTTS 推理走常驻服务 `tts_resident.py`：**模型只加载一次**，之后每一批都直接复用。

---

## 三、使用方法

直接运行单文件 exe（`YsDubbingTool.exe`）即可，无需安装。

### 1) 首次配置（左栏「目录设置」）

1. **工作区目录**：所有产物与辅助文件的根。设置后自动创建并推导
   `VOtxt / VOerror / VOdub / translate / 词表.txt / ffmpeg\ffmpeg.exe`
2. **IndexTTS 根目录**：指向 `indexTTS2` 安装目录（内含 `.venv\Scripts\python.exe` 与 `checkpoints`）
3. **GPT-SoVITS 目录**：指向其安装目录（内含 `runtime\python.exe`、`wavs`、`temp.txt`）
4. **音色目录**：wav 音色库（IndexTTS 用）；选 GPT 模型时自动改读 `<GPT-SoVITS 目录>\wavs` + `temp.txt`

配音流程必需的外部环境（模型自带，**不由本工具分发**）：

- IndexTTS 2.5 / GPT-SoVITS 的本地安装与 `.venv` 解释器
- ffmpeg（WAV 转 OGG 用），路径在配置 `ffmpeg` 字段

### 2) 快速上手（最短路径）

```
① 目录设置 → 工作区目录 = 想放所有产物的位置
② 顶部 源目录 = 放 sub_zh.csv 与角色文件夹的目录（输出目录为 srt 输出根，默认随工作区推导）
③ 点「ZH 的 csv 拆分」 → 得到 srt
④ 「配音工具」填 配音文件夹 / 音色目录 / IndexTTS 根目录；模型选 IndexTTS 2.5 → 选音色
⑤ 点「开始」 → 出 wav，并自动转 OGG
```

### 3) 配置文件字段（`%APPDATA%\YYNTools\config.json`）

| 字段 | 说明 |
|---|---|
| workspace | 工作区根目录（改它自动推导下列 5 项） |
| source / target | 源目录（含 ogg 与 sub_zh.csv）/ srt 输出根目录 |
| votxt / voerror / vodub / translate / dict | 由 workspace 推导的子路径 |
| ffmpeg | ffmpeg.exe 完整路径（由 workspace 推导） |
| temp_txt | GPT-SoVITS 的 temp.txt（参考文本库） |
| gptsovits / itts_root | 两个模型的安装根目录 |
| api_url | GPT-SoVITS api_v2 地址（VOerror 配音用，默认 127.0.0.1:9880） |
| dub_in / dub_voice_dir / dub_out | 配音文件夹 / 音色目录 / 输出路径 |
| dub_model | IndexTTS 2.5 或 GPT-SoVITS v2Pro |
| dub_voice | 当前音色（显示名） |
| dub_emo_on / dub_emo_weight | 情感开关 / 强度（0~1） |
| dub_emo8_on / dub_e8_* | 八向向量开关 / 各维数值（happy angry sad fear disgust low surprise neutral） |
| dub_emo_ref | 按原音色参考（同名原音频作情感参考） |
| dub_pick_on / dub_pick_files | 单独选音频开关 / 所选文件清单（\| 分隔） |
| dub_voice_order | 音色顺序表路径（PD 组置顶，其余按表排序） |
| auto_in / auto_root_in | 自动流程输入目录 / 无人值守主输入根 |
| auto_emo_weight / auto_resident | 自动流程情感强度 / 常驻 TTS 开关 |
| ron_dir / ron_opt | 待配音目录根 / 列表视图开关 |
| simple_mode | 简略模式（地址栏只留工作区 + TTS 路径） |

### 4) 工作区里的辅助文件（本工具生成或读取）

| 文件 | 作用 |
|---|---|
| 对照表.csv | 角色名→音色映射（三列：角色名,音色名,旧音色）。自动流程点「开始」自动写入；无人值守模式按它批量跑 |
| 列表视图表名.csv | 两列「文件夹名,显示名」，列表视图下拉显示关卡译名（可选，无则只显示文件夹名） |
| 词表.txt | 词表替换规则，每行 `"旧","新"` |
| sound-askuser.wav | 完成提示音（缺失时自动从内嵌资源生成） |
| progress.json / run.log | 配音批次进度（自动流程输出目录下，监视窗口读取） |
| suspicious.csv | 配音质检可疑条目追加记录 |

---

## 四、目录与产物

| 产物 | 位置 |
|---|---|
| 拆出的字幕 srt | `<输出目录>\<源文件夹名>\*.srt` |
| 台本 srt | `<输出路径>\台本\<角色名>\` |
| 配音 srt / wav / ogg | `<输出路径>\dub\{srt,wav,ogg}\<角色名>\` |
| 无人值守模式产物 | `<输出路径>\Auto\<角色名>\` |
| 工作区辅助目录 | `<工作区>\VOtxt\ · VOerror\ · VOdub\ · translate\` |
| 运行日志 | 软件底部「日志」区 |

> 「角色名」= 配音文件夹（或所选音频所在目录）的**文件夹名**，不是完整路径。
> 「输出路径」（配置项 `dub_out`）默认 = `<工作区>\output`。

---

## 五、外部依赖与许可

- 本工具**不捆绑、不分发**任何模型权重与 ffmpeg；请自行安装并单独遵守其许可。
- 依赖的第三方组件：IndexTTS 2.5（Apache-2.0）、GPT-SoVITS v2Pro（MIT）、ffmpeg（LGPL / GPL）。
- **Lite（本仓库）** 以 GPL-3.0-or-later 发布；本手册描述的 Rust 版为**高级 / 开发者**授权版本，
  两者的功能差异见 [版本功能对照表.md](版本功能对照表.md)。
