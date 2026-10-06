#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
删除内容仅包含括号的字幕文件

用途：清理只含括号批注（如「（脚步声）」）而无实际台词的字幕文件。
输入：--dir 目标目录；--ext 要检查的文件扩展名（默认 .srt）。
输出：删除符合条件的文件并打印统计；配合 --dry-run 仅预览、不实际删除。

使用方法：
  python delete_by_content.py --dir "recogn/dlc4/mlo1"
"""

import argparse
import re
from pathlib import Path


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='删除内容仅包含括号的字幕文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python delete_by_content.py --dir "recogn/dlc4/mlo1"
        """
    )
    
    parser.add_argument(
        '--dir',
        type=str,
        required=True,
        help='目标目录'
    )
    
    parser.add_argument(
        '--ext',
        type=str,
        default='.srt',
        help='要检查的文件扩展名（默认 .srt）'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只显示将要删除的文件，不实际删除'
    )
    
    return parser.parse_args()


def is_only_bracket_content(file_path):
    """
    检查文件内容是否只包含括号内的内容
    
    Args:
        file_path: 文件路径
    
    Returns:
        bool: 如果内容只包含括号内的内容，返回 True
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
            # 匹配形如「（...）」「（...）。」的纯括号内容（忽略时间轴）

            # 先移除所有时间轴行
            lines = content.split('\n')
            text_lines = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # 如果包含 --> 就是时间轴，跳过
                if '-->' in line:
                    continue
                text_lines.append(line)
            
            # 检查剩下的内容是否只包含括号格式
            if not text_lines:
                return False
            
            # 检查每一行文本是否符合括号格式
            for text_line in text_lines:
                # 模式1： （...）
                # 模式2： （...）。
                pattern = r'^（.*）\。?$'
                if not re.match(pattern, text_line):
                    return False
            
            return True
    
    except Exception as e:
        print(f'警告：读取文件失败 {file_path}: {e}')
        return False


def delete_by_bracket_content(directory, extension, dry_run):
    """
    删除内容仅包含括号的文件
    
    Args:
        directory: 目标目录
        extension: 要检查的文件扩展名
        dry_run: 是否只显示将要删除的文件，不实际删除
    """
    target_dir = Path(directory)
    
    if not target_dir.exists() or not target_dir.is_dir():
        print(f'错误：目录不存在或不是有效的目录: {directory}')
        return 0
    
    deleted_count = 0
    
    print(f'正在扫描目录: {directory}')
    print('-' * 60)
    
    for file_path in target_dir.glob(f'*{extension}'):
        filename = file_path.name
        
        if is_only_bracket_content(file_path):
            if dry_run:
                print(f'[模拟删除] {filename}')
            else:
                print(f'正在删除: {filename}')
                file_path.unlink()
            deleted_count += 1
    
    print('-' * 60)
    if dry_run:
        print(f'模拟删除操作完成，共有 {deleted_count} 个文件将被删除')
    else:
        print(f'操作完成，共删除 {deleted_count} 个文件')
    
    return deleted_count


def main():
    args = parse_arguments()
    delete_by_bracket_content(args.dir, args.ext, args.dry_run)
    return 0


if __name__ == '__main__':
    exit(main())
