#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
删除字幕文件的数字标号

用途：批量去掉 SRT 中纯数字的序号行。
输入：--target-dir 目标 SRT 文件目录。
输出：就地重写目录下所有 .srt 文件（删除纯数字行），并打印处理统计。

使用方法：
  python remove_line_numbers.py --target-dir "recogn/dlc4/mlo1"
"""

import argparse
import os
from pathlib import Path


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='删除字幕文件的数字标号',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python remove_line_numbers.py --target-dir "recogn/dlc4/mlo1"
        """
    )
    
    parser.add_argument(
        '--target-dir',
        type=str,
        required=True,
        help='目标 SRT 文件目录'
    )
    
    return parser.parse_args()


def remove_line_numbers_from_file(file_path):
    """从单个文件中删除数字标号行"""
    if not file_path.exists():
        print(f'  警告: 文件不存在，跳过: {file_path}')
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        line = line.rstrip('\n')
        
        # 如果是纯数字行，则跳过
        if line.strip().isdigit():
            continue
        
        new_lines.append(line)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines) + '\n')
    
    return True


def remove_line_numbers(target_dir):
    """批量删除目录中所有 SRT 文件的数字标号"""
    target_path = Path(target_dir)
    
    if not target_path.exists():
        print(f'错误: 目标目录不存在: {target_dir}')
        return 0
    
    print(f'正在处理目录: {target_dir}')
    
    success_count = 0
    skipped_count = 0
    
    for file_path in target_path.glob('*.srt'):
        print(f'处理: {file_path.name}')
        if remove_line_numbers_from_file(file_path):
            success_count += 1
        else:
            skipped_count += 1
    
    print(f'\n完成！')
    print(f'成功处理: {success_count} 个文件')
    print(f'跳过: {skipped_count} 个文件')
    
    return success_count


def main():
    args = parse_arguments()
    remove_line_numbers(args.target_dir)
    return 0


if __name__ == '__main__':
    exit(main())
