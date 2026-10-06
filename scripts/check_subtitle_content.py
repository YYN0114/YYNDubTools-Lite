#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
字幕内容检查脚本：查找文件中的英文和括号批注

用途：扫描目录下 SRT 文件，定位可能未汉化（含英文字母）或带括号批注（可能为其他语种）的字幕。
输入：--target-dir 目标 SRT 文件目录。
输出：控制台打印统计与分类清单，不修改任何文件。

使用方法：
  python check_subtitle_content.py --target-dir <目标目录>
"""

import argparse
import os
from pathlib import Path


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='检查字幕文件内容中的英文和括号批注'
    )
    
    parser.add_argument(
        '--target-dir',
        type=str,
        required=True,
        help='目标 SRT 文件目录'
    )
    
    return parser.parse_args()


def main():
    args = parse_arguments()
    
    target_dir = Path(args.target_dir)
    
    if not target_dir.exists():
        print(f'错误: 目标目录不存在: {target_dir}')
        return 1
    
    CHECK_CHARS = 'abcdefghijklmnopqrstuvwxyz()'
    
    # 音效/受伤/死亡等非台词文件名的关键字：命中即跳过检查
    EXCLUDE_PREFIXES = [
        'death', 'pain', 'bleedoutbreath', 'incapacitated',
        'toxicgas', 'toxicgasdeath', 'gassed', 'bleedout_breath',
        'bark]stunned', 'bark]flashed', 'bark]gassed', 'bark]tased',
        'bark]incapidle', 'bark]bashed', 'bark]breathing', 'bark]hesitating'
    ]
    
    print(f'正在检查目录: {target_dir}')
    
    unlocalized = []
    other_lang = []
    
    for filename in os.listdir(target_dir):
        if not filename.endswith('.srt'):
            continue
        
        lower_name = filename.lower()
        excluded = False
        for prefix in EXCLUDE_PREFIXES:
            if prefix in lower_name:
                excluded = True
                break
        if excluded:
            continue
        
        filepath = target_dir / filename
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f'{filename}<读取错误: {e}>')
            continue
        
        content_lower = content.lower()
        
        for char in CHECK_CHARS:
            if char in content_lower:
                if char == '(' or char == ')':
                    other_lang.append(filename)
                else:
                    unlocalized.append(filename)
                break
    
    print(f'\n=== 统计 ===')
    print(f'未汉化数: {len(unlocalized)}')
    print(f'其他语种数: {len(other_lang)}')
    
    print(f'\n=== 未汉化文件 ===')
    for filename in unlocalized:
        print(f'{filename}<可能未汉化>')
    
    print(f'\n=== 其他语种批注文件 ===')
    for filename in other_lang:
        print(f'{filename}<可能为其他语言批注>')
    
    return 0


if __name__ == '__main__':
    exit(main())