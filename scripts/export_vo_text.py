#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
导出VO文本脚本：从CSV读取对话内容，按Key导出为单个文本文件

用途：将 CSV 中的对话导出为 <key>.txt，并清理内容含括号的无效条目。
输入：--csv-file 源 CSV（至少含 Key、Dialogue 列）。
输出：<key>.txt 写入输出目录；输出目录按 CSV 父目录名自动推导为 votxt/<父目录名>。

说明：
  参考 update_subtitles.py 的CSV读取逻辑，但不读取SRT、不处理时间轴，
  直接将每条对话导出为 <key>.txt 文件到 votxt 目录。
  输出目录按CSV父目录名自动推导（如 .../333/sub.csv → votxt/333/）。
  步骤2不根据无声文件列表排除，仅按输出文件内容是否包含 ( ) （ ） 删除。

使用方法：
  # 导出VO文本（输出目录按CSV父目录名自动推导）
  python export_vo_text.py --csv-file "<输出根>/<角色名>/sub_zh.csv"
  # → 输出到 votxt/<角色名>/

  # 仅执行步骤2（删除含括号文件）
  python export_vo_text.py --clean-only --output-dir "<目录>"
"""

import argparse
import csv
from pathlib import Path


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='从CSV读取对话，导出为<key>.txt文本文件到votxt目录',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 导出VO文本（输出到 votxt/<角色名>/）
  python export_vo_text.py --csv-file "OGGs/<角色名>/sub_zh.csv"

  # 仅执行步骤2（清理含括号文件）
  python export_vo_text.py --clean-only --output-dir "votxt/MethBiker"
        """
    )

    parser.add_argument(
        '--csv-file',
        type=str,
        help='源 CSV 文件路径（--clean-only 模式下不需要）'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        help='输出目录（默认：按CSV父目录名自动推导为 votxt/<父目录名>）'
    )

    parser.add_argument(
        '--key-col',
        type=str,
        default='Key',
        help='CSV 中 Key 列的列名（默认：Key）'
    )

    parser.add_argument(
        '--dialogue-col',
        type=str,
        default='Dialogue',
        help='CSV 中 Dialogue 列的列名（默认：Dialogue）'
    )

    parser.add_argument(
        '--clean-only',
        action='store_true',
        help='仅执行步骤2：删除含括号文件（不导出）'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只显示将要删除的文件，不实际删除'
    )

    return parser.parse_args()


def read_csv_file(csv_file_path, key_col, dialogue_col):
    """
    读取 CSV 文件并解析 Key 和 Dialogue 列

    Args:
        csv_file_path: CSV 文件路径
        key_col: Key 列名
        dialogue_col: Dialogue 列名

    Returns:
        dict: {key: dialogue}
    """
    data = {}

    with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            key = (row.get(key_col) or '').strip()
            dialogue = (row.get(dialogue_col) or '').strip()

            if key and dialogue:
                data[key] = dialogue

    return data


def contains_bracket(file_path):
    """
    检查文件内容是否包含括号字符（不根据列表排除，仅按内容判断）

    Args:
        file_path: 文件路径

    Returns:
        bool: 如果内容包含 ( ) （ ） 任意一个，返回 True
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        for char in '()（）':
            if char in content:
                return True
        return False

    except Exception as e:
        print(f'警告：读取文件失败 {file_path}: {e}')
        return False


def delete_bracket_files(directory, ext='.txt', dry_run=False):
    """
    删除内容包含括号的文件（步骤2）

    Args:
        directory: 目标目录
        ext: 要检查的文件扩展名（默认 .txt）
        dry_run: 是否只显示不实际删除

    Returns:
        int: 删除的文件数
    """
    target_dir = Path(directory)

    if not target_dir.exists() or not target_dir.is_dir():
        print(f'错误：目录不存在或不是有效的目录: {directory}')
        return 0

    deleted_count = 0

    print(f'步骤2: 正在扫描目录: {directory}')
    print('-' * 60)

    for file_path in target_dir.glob(f'*{ext}'):
        filename = file_path.name

        if contains_bracket(file_path):
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


def export_vo_text(csv_file, output_dir, key_col, dialogue_col):
    """
    导出VO文本（步骤1）

    Args:
        csv_file: CSV 文件路径
        output_dir: 输出目录
        key_col: Key 列名
        dialogue_col: Dialogue 列名

    Returns:
        int: 成功导出的文件数
    """
    print(f'步骤1: 正在读取 CSV 文件: {csv_file}')
    data = read_csv_file(str(csv_file), key_col, dialogue_col)
    print(f'找到 {len(data)} 条有内容的记录')

    print(f'\n正在导出文本文件（输出目录: {output_dir}）:')

    success_count = 0
    exists_count = 0
    error_count = 0

    for key, dialogue in data.items():
        output_path = output_dir / f'{key}.txt'

        if output_path.exists():
            print(f'{key}<已存在，跳过>')
            exists_count += 1
            continue

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(dialogue)
            success_count += 1
        except Exception as e:
            print(f'{key}<写入错误: {e}>')
            error_count += 1

    print(f'\n步骤1完成！')
    print(f'成功导出: {success_count} 个文件')
    print(f'已存在跳过: {exists_count} 个文件')
    print(f'错误跳过: {error_count} 个文件')

    return success_count


VOTXT_BASE = 'votxt'        # 未显式给 --output-dir 时的默认根目录（相对当前工作目录）


def main():
    args = parse_arguments()

    if args.output_dir:
        output_dir = Path(args.output_dir)
    elif args.csv_file:
        csv_parent_name = Path(args.csv_file).parent.name
        output_dir = Path(VOTXT_BASE) / csv_parent_name
        print(f'输出目录自动推导: {output_dir}')
    else:
        print('错误: 需要 --csv-file 或 --output-dir 参数')
        return 1

    if args.clean_only:
        delete_bracket_files(str(output_dir), '.txt', args.dry_run)
        return 0

    if not args.csv_file:
        print('错误: 非 --clean-only 模式下需要 --csv-file 参数')
        return 1

    csv_file = Path(args.csv_file)

    if not csv_file.exists():
        print(f'错误: CSV 文件不存在: {csv_file}')
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    export_vo_text(csv_file, output_dir, args.key_col, args.dialogue_col)

    print()
    delete_bracket_files(str(output_dir), '.txt', args.dry_run)

    print('\n全部完成！')

    return 0


if __name__ == '__main__':
    exit(main())
