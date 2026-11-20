# 语言包（Language packs）

「关于 → 多语言」面板里，**中文（简体）** 和 **English** 是内置的（就是源码里 `tr!("中文", "English")` 那两条字面量，切换不下载任何东西）。

其余语言靠这里生成的 JSON 语言包：

| 文件 | 语言 | 状态 |
| --- | --- | --- |
| `zh-tw.json` | 繁體中文 | 317 条，`_zh_source.json` 经 OpenCC（s2twp）自动转换 |
| `ja.json` | 日本語 | 317 条，机器翻译初版 |
| `ko.json` | 한국어 | 317 条，机器翻译初版 |
| `ru.json` | Русский | 317 条，机器翻译初版 |
| `fr.json` | Français | 317 条，机器翻译初版 |
| `es.json` | Español | 317 条，机器翻译初版 |
| `en.json` | English | 只是清单（英文=英文），不用上传 |

机翻初版留着明显的生硬感，术语（配音 / 原声 / 台本 / 手动）建议由懂行的人再润一遍；
只改某几条也可以，改完直接把 json 传回服务器，客户端下次启动就生效，不用发新版本。

## 格式

```json
{
  "Start auto flow": "自動フローを開始",
  "Pack mod": "MOD 梱包"
}
```

**key 是英文原文**，也就是 `tr!` 的第二个参数。这样：

- 源码不用改：`tr!("中文", "English")` 照旧写，运行时按当前语言决定取哪条；
- 语言包可以只翻一部分，缺的条目自动回退英文；
- 新增文案不会让旧语言包失效。

## 怎么生成 / 更新

```bash
# 1. 从源码抽出所有文案，写 lang/en.json（清单）与 lang/_zh_source.json（英中对照）
python tools/extract_i18n.py

# 2. 繁中全自动
python - <<'PY'
import json, opencc
cc = opencc.OpenCC('s2twp')
src = json.load(open('lang/_zh_source.json', encoding='utf-8'))
json.dump({k: cc.convert(v) for k, v in src.items()},
          open('lang/zh-tw.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
```

`s2twp` 是「简体 → 繁体（含台湾用语）」，要纯字形转换用 `s2t`。

其他语种按 `key 英文原文 → 译文` 直接填即可。

## 怎么分发

客户端**自带**这两个路径的读取逻辑：

- 语言包目录：`%APPDATA%\YYNTools\lang\<code>.json`
- 下载地址：`<lang_pack_base>/<code>.json`

`lang_pack_base` 是配置键，留空时用 `src/i18n.rs` 里的 `DEFAULT_PACK_BASE`
（当前是 `http://203.195.197.239/lang`）。

所以把本目录下要发布的 `xx.json` 传到服务器的这个路径下就能被自动下载：

```
http://203.195.197.239/lang/zh-tw.json
http://203.195.197.239/lang/ja.json
http://203.195.197.239/lang/ko.json
http://203.195.197.239/lang/ru.json
http://203.195.197.239/lang/fr.json
http://203.195.197.239/lang/es.json
http://203.195.197.239/lang/pt.json
```

面板上没下载的语言会显示 `↓`，第一次点击时自动下载并切换。
已下载的会直接切换（文件就在 `%APPDATA%\YYNTools\lang\`）。

## 注意

- 目录名（`Auto` / `手动` / `原声` / `台本` / `dub` / `ogg` / `VO_PC` 等）是**真实磁盘结构**，译文里不要翻它们，否则界面显示的路径和实际对不上。
- 占位符（`%ROLE%`、`<工作区>`、`<timestamp>`、`{}`）原样保留。
- 带参数的行（`trf!`）只支持中英；其他语言回退英文。
