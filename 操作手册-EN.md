[中文](操作手册.md) | **English**

# Local AI Game Dubbing + Image Localization — Operations Manual

> Applies to: the YYN local AI localization kit (ComfyUI + IndexTTS 2.5 voice dubbing, Manga Image Translator image localization).

Workspace: custom | GPU: ≥8GB VRAM | Fully local operation

---

## 0. Quick overview of the two environments

| Purpose | Directory | Launch | Port |
|---|---|---|---|
| **English game → Chinese dubbing** | `<workspace>\ComfyUI-IndexTTS\` | double-click `start_comfyui.bat` | **8190** |
| **Image text EN→ZH** | `<workspace>\MangaImageTranslator\` | `batch_translate.bat <directory>` | none (command line) |

> ⚠️ **With 8GB VRAM you must run them serially**: do not run ComfyUI and Manga Image Translator at the same time.
> Finish one, close it, then run the other.

---

## 1. Voice dubbing: ComfyUI + IndexTTS 2.5

### 1.1 Launch

Double-click `<workspace>\ComfyUI-IndexTTS\start_comfyui.bat`

Open **http://127.0.0.1:8190** in the browser

> Port 8190 is used to avoid 8188, which is common for the "HuiShi(绘世)" bundle; the two can coexist without interfering.

### 1.2 Node locations

Menu path: **`T8star-Aix` → `Audio` → `IndexTTS 2.5`** (**23** nodes in total)

Core nodes:

| Node | Function |
|---|---|
| `IndexTTS 2.5 Model Loader(模型加载器)` | Loads the model; for 8GB use `precision=float16`, `reference_device=cpu` |
| `IndexTTS 2.5 Voice Generation(语音生成)` | Single-sentence generation |
| `IndexTTS 2.5 Emotion Control(情感控制)` | Switches among four emotion modes (see 1.4) |
| `IndexTTS 2.5 Batch Dialogue / SRT(批量台词 / SRT)` | Parses one-line-per-sentence scripts |
| `IndexTTS 2.5 Multi-Role / SRT Generation(多角色 / SRT 生成)` | Batch generation, outputs per-sentence audio |
| `IndexTTS 2.5 Reference Audio Quality Check(参考音频质量检测)` | Reference-audio health check |

### 1.3 Ready-made workflows (33 sets)

Located at `ComfyUI\custom_nodes\comfyui-indextts25-t8\example_workflows\`

- `ui\*.json` — drag into the ComfyUI UI and use directly
- `api\*.json` — for script/API calls

**The most relevant ones**:

| File | Purpose |
|---|---|
| `ui\28_low_vram_fp16.json` | ★ Low-VRAM configuration **dedicated to 8GB VRAM** |
| `ui\31_per_line_emotion.json` | ★ **Per-sentence emotion** batch |
| `ui\12_batch_dialogue_json.json` | Batch dialogue JSON mode |
| `ui\05_emotion_text.json` | Natural-language emotion description |
| `ui\04_emotion_vector.json` | Eight-dimensional emotion vector |
| `ui\03_emotion_reference_audio.json` | Emotion reference audio |
| `ui\13_srt_multi_role.json` | SRT multi-role |

### 1.4 Emotion control (all four modes supported)

Use the `IndexTTS 2.5 Emotion Control(情感控制)` node and switch `mode`:

| mode | Description | Corresponding parameter |
|---|---|---|
| `text` | Natural-language description, e.g. "fearfully, voice trembling" | `emo_text` |
| `vector` | Eight-dimensional vector, each 0~1 | eight-dim emotion vector |
| `reference_audio` | Emotion reference audio | `emo_audio_prompt` |
| `speaker` | Directly follows the cloned timbre (saves the most VRAM) | — |

**Eight dimensions (order)**: `[happy(高兴), angry(愤怒), sad(悲伤), afraid(恐惧), disgusted(厌恶), melancholic(低落), surprised(惊讶), calm(自然)]`

> ⚠️ **API call note**: `Emotion Control(情感控制)` is a DynamicCombo node; when submitting via the API,
> the parameters inside the mode must be prefixed with `mode.`, e.g. `mode.emotion_text`, `mode.strength`.
> `tts_batch.py` already handles this automatically.

### 1.5 Batch voice generation (script method, recommended)

```powershell
# Start ComfyUI first (open another window, or just double-click the bat)
# 1) Dry run, check script parsing and environment
& <workspace>\ComfyUI-IndexTTS\python_embeded\python.exe `
  <workspace>\_shared\tts\tts_batch.py `
  --script <workspace>\_shared\tts\script_example.txt `
  --voice "your_reference_audio.wav" --dry-run

# 2) Generate 5 test clips
& ...\python.exe ...\tts_batch.py --script ...\script_example.txt `
  --voice "your_reference_audio.wav" --limit 5

# 3) Full 100~200 clips
& ...\python.exe ...\tts_batch.py `
  --script script_full.txt --voice "your_reference_audio.wav" `
  --out "<output dir>\voice_zh" --precision float16 --reference-device cpu `
  --template "{index:04d}_{role}" --overwrite
```

**Script format** (one line per sentence):
```
role|Chinese line|language|duration factor|per-sentence emotion
```

**Per-sentence emotion syntax**:
```
text:fearfully, voice trembling;strength=0.9
vector:0,0.8,0,0,0,0,0,0;strength=0.85
speaker
(blank = follow the timbre)
```

**Naming template** `--template` placeholders: `{index}` `{role}` `{lang}`
Example: `--template "{index:04d}_{role}"` → `0001_主角.wav`

**Output**: uniformly converted to **16-bit PCM WAV / 22050Hz mono**
(ComfyUI natively saves FLAC; the script transcodes it, so game engines can use it directly)

### 1.6 Using an LLM as a "director" to auto-label emotion

See `<workspace>\_shared\tts\LLM导演提示词模板.md`

Flow: **English lines → local LLM(Qwen2.5) → one-line-per-sentence Chinese script → tts_batch.py → batch Chinese speech**

> ⚠️ **Do not use SakuraLLM**: it only supports 「Japanese→Chinese」 and cannot do Chinese dubbing of English games.
> Use `Qwen2.5-7B-Instruct` (Ollama or llama.cpp) instead; translation + emotion labeling in one pass.

---

## 2. Image localization: Manga Image Translator

### 2.1 Environment

- Dedicated **Python 3.11.9** (`<workspace>\python311\`); **you cannot use the system Python 3.13**
- Separate venv: `<workspace>\MangaImageTranslator\venv\`
- torch **2.5.1+cu121**, CUDA available

### 2.2 Batch translation

```powershell
# Basic usage (outputs to <input directory>-translated)
<workspace>\MangaImageTranslator\batch_translate.bat "<screenshot dir>"

# Specify the output directory
<workspace>\MangaImageTranslator\batch_translate.bat "<screenshot dir>" "<output dir>"
```

Supports **recursive subdirectories**; 100~200 images is the design use case.

### 2.3 Translation backend

Default **`qwen2`** — the built-in local backend, using `Qwen/Qwen2-1.5B-Instruct` (3.09GB),
loaded with 4-bit quantization, fits 8GB VRAM.

To change the backend: edit the `translator.translator` field in `config\en2zh-local.json`.
Possible values (partial): `qwen2` / `nllb` / `m2m100_hf` / `custom_openai` / `none`.

| Backend | VRAM | Quality | Notes |
|---|---|---|---|
| `qwen2`(default) | low(4bit) | ★★★ | Preconfigured, works out of the box |
| `custom_openai` | low | ★★★★ | Point to a larger model via Ollama/llama.cpp |
| `nllb` | medium | ★★ | ⚠️ hf-mirror's Xet service returns 401, so the weights fail to download |
| `none` | none | — | OCR only, no translation; for testing the flow |

**Want a larger model (optional)**: you can use a local Ollama (example: `<Ollama dir>\ollama.exe`).
Change the config to:

```json
"translator": {
  "translator": "custom_openai",
  "target_lang": "CHS",
  "chatgpt_config": {
    "custom_openai": {
      "api_base": "http://127.0.0.1:11434/v1",
      "model": "gemma4:e4b",
      "api_key": "local"
    }
  }
}
```

### 2.4 Model list

| Purpose | Location | Size |
|---|---|---|
| Text detection | `models\detection\detect-20241225.ckpt` | 308,380,176 B |
| OCR | `models\ocr\ocr_ar_48px.ckpt` | 204,290,192 B |
| OCR charset | `models\ocr\alphabet-all-v7.txt` | 186,651 B |
| Image inpainting | `models\inpainting\lama_large_512px.ckpt` | 204,544,673 B |
| Translation | `models\hfhome\hub\models--Qwen--Qwen2-1.5B-Instruct` | 3.09 GB |

### 2.5 Known pitfalls

| Pitfall | Description | Handling |
|---|---|---|
| **CLI has no `--translator`/`--target-lang`** | Removed in this version; everything goes through the config file | Edit `config\en2zh-local.json` |
| **`--config-file` is a subcommand argument** | Must come after `local` | `local -i ... --config-file ...` |
| **qwen2's `_load()` does not pass `cache_dir`** | Upstream bug; it looks in the default HF cache | Point `HF_HOME` at `models\hfhome` (the bat already sets it) |
| **qwen2 loads fp32 by default** | On 8GB machines it reports `os error 1455 page file too small` | Patched to default to 4bit (`DSH_QWEN2_4BIT=1`) |
| **`psutil` missing** | The repo's `requirements.txt` omits it; batch mode crashes without it | Install it |
| **`pydensecrf`** | sdist only; requires MSVC compilation | Install 1.0 |
| **`dbconvnext` detector** | Broken on the upstream main branch (empty URL) | Do not choose it |
| **SakuraLLM** | **Japanese→Chinese only**; unusable for EN→ZH | Use qwen2 |
| **`.bat` Chinese garbled text** | cmd.exe parses as GBK; UTF-8 Chinese breaks it | Launch/batch scripts use **ASCII prompts only**; Chinese notes live in this manual |
| **nllb mirror 401** | hf-mirror's Xet service is unauthorized | Use qwen2; or with a proxy set `HF_ENDPOINT=https://huggingface.co` |

---

## 3. Common errors quick reference

| Error | Cause | Solution |
|---|---|---|
| ComfyUI `WinError 10048` | Port already in use | Change `PORT` in `start_comfyui.bat` |
| `No module named 'indextts.utils.maskgct_utils'` | Two IndexTTS node sets namespace-conflict | The billwuhao node was renamed to `.disabled`; do not enable it together with the t8 node |
| `No module named 'psutil'` | MIT repo bug | `venv\Scripts\python.exe -m pip install psutil` |
| `os error 1455 page file too small` | Qwen2 fp32 loading blows memory | Confirm `DSH_QWEN2_4BIT=1` (the bat already sets it) |
| `We couldn't connect to huggingface.co` | `HF_HOME` not set; qwen2 cannot find the model | Use `batch_translate.bat` (it sets all environment variables) |
| ComfyUI out of VRAM | 8GB running full precision | Use `ui\28_low_vram_fp16.json`; `precision=float16` + `reference_device=cpu` |
| Poor translation quality | Using the small 1.5B model | Change `custom_openai` to a larger model via Ollama |
| ComfyUI output is `.flac` not `.wav` | SaveAudio's native format | `tts_batch.py` auto-converts to WAV; manual export requires your own transcode |

---

## 4. Directory index

```
<workspace>\
├─ ComfyUI-IndexTTS\                    # ① dubbing environment
│   ├─ start_comfyui.bat                #    ★ launch (port 8190)
│   ├─ ComfyUI\models\TTS\IndexTTS-2.5\ #    model (7.9GB)
│   └─ ComfyUI\custom_nodes\
│       ├─ comfyui-indextts25-t8\       #    ★ main node + 33 workflows
│       └─ ComfyUI_IndexTTS.disabled\   #    alternative node (disabled to avoid conflicts)
├─ MangaImageTranslator\                # ② image localization
│   ├─ batch_translate.bat              #    ★ batch entry point
│   ├─ config\en2zh-local.json          #    config (backend/language/precision)
│   ├─ models\
│   │   ├─ detection\ ocr\ inpainting\  #    detection/OCR/inpainting models
│   │   └─ hfhome\hub\                  #    Qwen2 translation model
│   └─ venv\                            #    standalone Python 3.11 environment
├─ python311\                           # dedicated MIT Python 3.11.9
├─ testdata\                            # test images and outputs
├─ output\                              # voice output (tts / tts_emotion / ...)
└─ _shared\
    ├─ tts\tts_batch.py                 # ★ voice batch script
    ├─ tts\LLM导演提示词模板.md          # ★ LLM emotion-labeling prompt
    ├─ tts\script_example.txt / .json   #    example script (10 entries)
    ├─ scripts\                          #    download/verify/test tools
    └─ docs\                             #    handover docs
```
