#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
词表替换脚本：根据词表文件（默认 dict.txt）批量替换字幕文件中的特定文本

用途：按词表规则逐条替换 SRT 中的文本。
输入：--target-dir 目标 SRT 目录；--dict-file 词表文件（默认 dict.txt），每行格式 "旧文本","新文本"。
输出：就地改写命中的 SRT 文件，并打印替换规则与统计。

使用方法：
  python replace_by_dict.py --target-dir <目标目录>
"""

import argparse
import os
import re
from pathlib import Path


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='根据词表文件（默认 dict.txt）批量替换字幕文件中的特定文本'
    )
    
    parser.add_argument(
        '--target-dir',
        type=str,
        required=True,
        help='目标 SRT 文件目录'
    )
    
    parser.add_argument(
        '--dict-file',
        type=str,
        default='dict.txt',
        help='词表文件路径（默认：dict.txt）'
    )
    
    return parser.parse_args()


def load_dict(dict_file):
    replacements = []
    
    if not os.path.exists(dict_file):
        print(f'警告: 词表文件不存在: {dict_file}')
        return replacements
    
    with open(dict_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            line = line.replace('”', '"').replace('“', '"').replace('""', '"')
            parts = re.match(r'^"([^"]+)","([^"]+)"$', line)
            if parts:
                old_text = parts.group(1)
                new_text = parts.group(2)
                replacements.append((old_text, new_text))
            else:
                print(f'警告: 词表格式错误: {line}')
    
    return replacements


def main():
    args = parse_arguments()
    
    target_dir = Path(args.target_dir)
    dict_file = args.dict_file
    
    if not target_dir.exists():
        print(f'错误: 目标目录不存在: {target_dir}')
        return 1
    
    replacements = load_dict(dict_file)
    
    if not replacements:
        print('错误: 词表为空或加载失败')
        return 1
    
    print(f'词表加载成功，共 {len(replacements)} 条替换规则')
    for old_text, new_text in replacements:
        print(f'  "{old_text}" -> "{new_text}"')
    
    print(f'\n正在处理目录: {target_dir}')
    
    modified_count = 0
    total_count = 0
    
    for filename in os.listdir(target_dir):
        if not filename.endswith('.srt'):
            continue
        
        total_count += 1
        filepath = target_dir / filename
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f'{filename}<读取错误: {e}>')
            continue
        
        modified = False
        for old_text, new_text in replacements:
            if old_text in content:
                content = content.replace(old_text, new_text)
                modified = True
        
        if modified:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                modified_count += 1
                print(f'{filename}<已替换>')
            except Exception as e:
                print(f'{filename}<写入错误: {e}>')
    
    print(f'\n=== 统计 ===')
    print(f'处理文件数: {total_count}')
    print(f'修改文件数: {modified_count}')
    
    return 0


if __name__ == '__main__':
    exit(main())