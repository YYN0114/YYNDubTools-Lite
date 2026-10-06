#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
字幕匹配检查脚本：交叉比对 CSV 文件和目标目录中的 SRT 文件，找出缺失项

用途：核对 CSV 记录与 SRT 文件是否一一对应，定位两边的缺失。
输入：--csv-file 源 CSV 文件；--target-dir 目标 SRT 目录；--key-col Key 列名。
输出：控制台打印两侧缺失清单（A. CSV 有而目录缺失；B. 目录有而 CSV 缺失），不修改文件。

使用方法：
  python find_missing_subtitles.py --csv-file <csv文件路径> --target-dir <目标目录>
"""

import argparse
import csv
import os
from pathlib import Path


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='交叉比对 CSV 文件和目标目录中的 SRT 文件，找出缺失项',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--csv-file',
        type=str,
        required=True,
        help='源 CSV 文件路径'
    )
    
    parser.add_argument(
        '--target-dir',
        type=str,
        required=True,
        help='目标 SRT 文件目录'
    )
    
    parser.add_argument(
        '--key-col',
        type=str,
        default='Key',
        help='CSV 中 Key 列的列名（默认：Key）'
    )
    
    parser.add_argument(
        '--strict',
        action='store_true',
        help='启用严格模式（区分大小写）'
    )
    
    return parser.parse_args()


def main():
    args = parse_arguments()
    
    csv_file = Path(args.csv_file)
    target_dir = Path(args.target_dir)
    
    if not csv_file.exists():
        print(f'错误: CSV 文件不存在: {csv_file}')
        return 1
    
    if not target_dir.exists():
        print(f'错误: 目标目录不存在: {target_dir}')
        return 1
    
    # 音效/受伤/死亡等非台词文件名的关键字：命中即跳过
    EXCLUDE_PREFIXES = [
        'death', 'pain', 'bleedoutbreath', 'incapacitated',
        'toxicgas', 'toxicgasdeath', 'gassed', 'bleedout_breath',
        'bark]stunned', 'bark]flashed', 'bark]gassed', 'bark]tased',
        'bark]incapidle', 'bark]bashed', 'bark]breathing', 'bark]hesitating'
    ]
    
    print(f'正在读取 CSV 文件: {csv_file}')
    csv_keys = set()
    with open(csv_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get(args.key_col) or '').strip()
            if key:
                lower_key = key.lower()
                
                excluded = False
                for prefix in EXCLUDE_PREFIXES:
                    if prefix in lower_key:
                        excluded = True
                        break
                if excluded:
                    continue
                
                if not args.strict:
                    key = lower_key
                csv_keys.add(key)
    
    print(f'正在读取目标目录: {target_dir}')
    dir_keys = set()
    for filename in os.listdir(target_dir):
        if filename.endswith('.srt'):
            key = filename[:-4]
            lower_key = key.lower()
            
            excluded = False
            for prefix in EXCLUDE_PREFIXES:
                if prefix in lower_key:
                    excluded = True
                    break
            if excluded:
                continue
            
            if not args.strict:
                key = lower_key
            dir_keys.add(key)
    
    print(f'\n=== 统计 ===')
    print(f'CSV 中有内容的记录: {len(csv_keys)} 条')
    print(f'目标目录中 SRT 文件: {len(dir_keys)} 个')
    
    csv_missing_in_dir = sorted(csv_keys - dir_keys)
    dir_missing_in_csv = sorted(dir_keys - csv_keys)
    
    print(f'\n=== A. CSV 中有但目录中缺失的 Key ===')
    print(f'共 {len(csv_missing_in_dir)} 个')
    if csv_missing_in_dir:
        for key in csv_missing_in_dir[:50]:
            print(f'  {key}')
        if len(csv_missing_in_dir) > 50:
            print(f'  ... 还有 {len(csv_missing_in_dir) - 50} 个')
    
    print(f'\n=== B. 目录中有但 CSV 中缺失的文件 ===')
    print(f'共 {len(dir_missing_in_csv)} 个')
    if dir_missing_in_csv:
        for key in dir_missing_in_csv[:50]:
            print(f'  {key}.srt')
        if len(dir_missing_in_csv) > 50:
            print(f'  ... 还有 {len(dir_missing_in_csv) - 50} 个')
    
    return 0


if __name__ == '__main__':
    exit(main())