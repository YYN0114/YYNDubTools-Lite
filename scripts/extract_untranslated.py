#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
字幕提取未译脚本：将未汉化的字幕文件移动到未译文件夹

用途：挑出目录中含英文字母（视为未汉化）的 SRT 文件并集中隔离。
输入：--target-dir 目标 SRT 文件目录。
输出：把符合条件且未排除的 SRT 移动到 <目标目录>/未译 子目录。

使用方法：
  python extract_untranslated.py --target-dir <目标目录>
"""

import argparse
import os
import shutil
from pathlib import Path


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='将未汉化的字幕文件移动到未译文件夹'
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
    output_dir = target_dir / '未译'
    
    if not target_dir.exists():
        print(f'错误: 目标目录不存在: {target_dir}')
        return 1
    
    CHECK_CHARS = 'abcdefghijklmnopqrstuvwxyz'
    
    # 音效/受伤/死亡等非台词文件名的关键字：命中即跳过
    EXCLUDE_PREFIXES = [
        'death', 'pain', 'bleedoutbreath', 'incapacitated',
        'toxicgas', 'toxicgasdeath', 'gassed', 'bleedout_breath',
        'bark]stunned', 'bark]flashed', 'bark]gassed', 'bark]tased',
        'bark]incapidle', 'bark]bashed', 'bark]breathing', 'bark]hesitating'
    ]
    
    print(f'正在检查目录: {target_dir}')
    
    unlocalized = []
    
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
                unlocalized.append(filename)
                break
    
    print(f'\n=== 统计 ===')
    print(f'未汉化数: {len(unlocalized)}')
    
    if unlocalized:
        output_dir.mkdir(exist_ok=True)
        print(f'\n正在移动文件到: {output_dir}')
        for filename in unlocalized:
            src = target_dir / filename
            dst = output_dir / filename
            
            if dst.exists():
                print(f'{filename}<已存在，跳过>')
                continue
            
            shutil.move(str(src), str(dst))
            print(f'{filename}<已移动>')
    else:
        print('\n没有需要移动的文件')
    
    return 0


if __name__ == '__main__':
    exit(main())