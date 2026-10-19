[中文](需要你下载.md) | **English**

# Files You Need to Download (Model Setup Checklist)

> Applies to: a model download and placement helper checklist for a local AI localization setup (ComfyUI + IndexTTS 2.5 speech / Manga Image Translator image localization).

> Division of labor: **you only download + place files in the specified locations**; installation, configuration, scripts, docs, and verification are all handled by the local scripts.

---

## 1. Manual download required (automated method not reachable)

### 1. `detect-20241225.ckpt` — Text detection model (294.1 MB) ★ The only hard gap

**Why it must be manual**: This file exists only in the GitHub Release (beta-0.3, 2022);
on some networks the connection to the GitHub Release CDN (`objects.githubusercontent.com`) is reset/times out
(e.g. `RemoteDisconnected` / `WinError 10060`). GitHub's **git protocol** is usually reachable,
but **release asset downloads** may not work.

**Download URL (choose any; browser / IDM / Thunder all work)**

| Method | URL |
|---|---|
| Official direct link | `https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/detect-20241225.ckpt` |
| Release page | `https://github.com/zyddnys/manga-image-translator/releases/tag/beta-0.3` |
| ghproxy mirror 1 | `https://ghproxy.net/https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/detect-20241225.ckpt` |
| ghproxy mirror 2 | `https://gh-proxy.com/https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/detect-20241225.ckpt` |

**Where to put it** (create the directory if it does not exist; the file name must match exactly)

```
<workspace>\MangaImageTranslator\models\detection\detect-20241225.ckpt
```

**Verify**: the file size must be exactly **308,380,176 bytes** (294.09 MiB).
Once downloaded you can run the verify+place script (see Section 4); it checks the size and puts it in the correct location.

---

## 2. Other files to prepare (list)

| File | Size | Location / Source |
|---|---|---|
| ComfyUI Windows Portable (cu128) | 2.4 GB | `<workspace>\ComfyUI-IndexTTS\` |
| IndexTTS 2.5 full model (26 files) | 7.7 GB | `<workspace>\_shared\models\IndexTTS-2.5\` |
| `ocr_ar_48px.ckpt` | 194.8 MB | hf-mirror |
| `alphabet-all-v7.txt` | 0.2 MB | hf-mirror |
| `lama_large_512px.ckpt` | 195.1 MB | hf-mirror |
| `python-3.11.9-amd64.exe` | 25.0 MB | python.org |
| `ComfyUI_IndexTTS` node | — | `custom_nodes` |
| `comfyui-indextts25-t8` node | — | `custom_nodes` |
| manga-image-translator source | — | GitHub repository |

---

## 3. Optional (download to improve quality; not required to run)

### 3.1 Local translation LLM (EN→ZH, recommended)

> ⚠️ Important: **SakuraLLM is for 「Japanese→Chinese」 only and cannot do English→Chinese**; many online tutorials mislead you.
> For English→Chinese, use the Qwen series + llama.cpp / Ollama.

| Purpose | File | Size | URL |
|---|---|---|---|
| Main EN→ZH engine (good quality) | Qwen2.5-7B-Instruct **Q4_K_M GGUF** (2 shards) | ≈4.5 GB | `https://hf-mirror.com/Qwen/Qwen2.5-7B-Instruct-GGUF` |
| Lower-VRAM alternative | Qwen2.5-3B-Instruct Q4_K_M | ≈2.0 GB | `https://hf-mirror.com/Qwen/Qwen2.5-3B-Instruct-GGUF` |
| Pure-Python offline fallback (average quality) | `facebook/nllb-200-distilled-600M` | 2.35 GB | `https://hf-mirror.com/facebook/nllb-200-distilled-600M` |

### 3.2 Manga OCR (more accurate on handwriting/artistic text)

| Purpose | Size | URL |
|---|---|---|
| `kha-white/manga-ocr-base` | 423.6 MB | `https://hf-mirror.com/kha-white/manga-ocr-base` |

---

## 4. Placement and verification script (run this after downloading)

`<workspace>\_shared\scripts\place_manual.py` is provided:

```powershell
# Automatically find the file in the "Downloads" folder, verify the byte count, and copy it to the correct location
& <workspace>\ComfyUI-IndexTTS\python_embeded\python.exe `
  <workspace>\_shared\scripts\place_manual.py --from "$env:USERPROFILE\Downloads"
```

You can also specify a single file:

```powershell
& <workspace>\ComfyUI-IndexTTS\python_embeded\python.exe `
  <workspace>\_shared\scripts\place_manual.py `
  --file "<some directory>\detect-20241225.ckpt"
```

The script will:
1. Match by known file name and check the exact byte count;
2. Copy to the target directory (creating it automatically);
3. Print a ✅/❌ result; on failure it reports how many bytes are missing.

---

## 5. If GitHub is completely unreachable

Alternative: find a file with the same name on ModelScope or a domestic cloud drive; or enable a local proxy
(e.g. Clash and similar, common port `127.0.0.1:7897`; with the system proxy enabled the browser can download directly).
As long as the final `detect-20241225.ckpt` lands under
`<workspace>\MangaImageTranslator\models\detection\` and is 308,380,176 bytes, it is fine.
