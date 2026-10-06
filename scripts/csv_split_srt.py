#!/usr/bin/env python
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""把 sub_zh.csv（Key,Dialogue,Context）批量拆成单个文本文件，每个 Key 一个文件。

用途：把 CSV 台词导出为一行一句的纯文本，可直接喂给 ``srt_cli_clone.py`` 做配音。
输入：--csv 指定的源 CSV（表头 Key,Dialogue,...）。
输出：--out 目录下每个 Key 一个文件（默认后缀 .srt）；空行、空 Key 自动忽略；不修改源 CSV。

示例
----
python csv_split_srt.py ^
  --csv "<工作区>\\<角色名>\\sub_zh.csv" ^
  --out  "<工作区>\\<角色名>\\srt"
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

ILLEGAL = re.compile(r'[\\/:*?"<>|]')


def main() -> int:
    ap = argparse.ArgumentParser(description="sub_zh.csv -> 每个 Key 一个文本文件")
    ap.add_argument("--csv", required=True, help="源 CSV（Key,Dialogue,Context）")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--ext", default="srt", choices=["srt", "txt"], help="输出后缀")
    ap.add_argument("--overwrite", action="store_true", help="覆盖已存在文件")
    ap.add_argument("--only-list", default=None,
                    help="只拆清单内的 Key（每行一个，按去扩展名匹配，可用 # 注释）")
    args = ap.parse_args()

    src = Path(args.csv)
    if not src.is_file():
        print(f"源 CSV 不存在: {src}", file=sys.stderr)
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    want: set[str] | None = None
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

    raw = src.read_bytes().decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(raw)))
    if rows and [c.strip().lower() for c in rows[0][:2]] == ["key", "dialogue"]:
        rows = rows[1:]

    written = skipped_empty = skipped_exists = skipped_out = 0
    seen: set[str] = set()
    dup: list[str] = []
    bad_char: list[str] = []

    for row in rows:
        if len(row) < 2:
            skipped_empty += 1
            continue
        key, text = row[0].strip(), row[1].strip()
        if not key or not text:
            skipped_empty += 1
            continue
        if want is not None and key.lower() not in want:
            skipped_out += 1
            continue
        if ILLEGAL.search(key):
            bad_char.append(key)
            key = ILLEGAL.sub("_", key)
        if key in seen:
            dup.append(key)
        seen.add(key)

        target = out_dir / f"{key}.{args.ext}"
        if target.exists() and not args.overwrite:
            skipped_exists += 1
            continue
        target.write_text(text + "\n", encoding="utf-8")
        written += 1

    print(f"源 CSV 行数(不含表头): {len(rows)}")
    print(f"已写出 {written} 个 .{args.ext}  ->  {out_dir}")
    print(f"跳过空行/空台词 {skipped_empty} / 已存在 {skipped_exists} / 不在清单内 {skipped_out}")
    if want is not None:
        miss = want - {p.stem.lower() for p in out_dir.glob(f"*.{args.ext}")}
        if miss:
            print(f"清单里 {len(miss)} 个 Key 在 CSV 里找不到: {sorted(miss)[:5]}", file=sys.stderr)
    if dup:
        print(f"警告: 重复 Key {len(dup)} 个: {dup[:5]}", file=sys.stderr)
    if bad_char:
        print(f"警告: Key 含非法字符已替换 {len(bad_char)} 个: {bad_char[:5]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
