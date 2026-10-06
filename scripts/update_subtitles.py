#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
字幕更新脚本：将 CSV 文件中的对话内容写入对应的 SRT 字幕文件

用途：按 Key 把 CSV 台词写回同名 SRT，保留并智能复用原时间轴。
输入：--csv-file 源 CSV；--target-dir 目标 SRT 目录；--key-col / --dialogue-col 列名。
输出：就地重写命中的 SRT 文件（不改时间戳），并打印成功/跳过统计。

使用方法：
  python update_subtitles.py --csv-file <csv文件路径> --target-dir <目标目录> [--key-col <Key列名>] [--dialogue-col <Dialogue列名>]
"""

import argparse
import csv
import os
import re
from pathlib import Path


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='将 CSV 文件中的对话内容写入对应的 SRT 字幕文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 基本用法（使用默认列名）
  python update_subtitles.py --csv-file "OGGs/DLC/DLC4/TowerMLO_01/sub_zh.csv" --target-dir "recogn/dlc4/mlo1"
  
  # 指定列名
  python update_subtitles.py --csv-file "path/to/file.csv" --target-dir "path/to/srt" --key-col "Key" --dialogue-col "Chinese"
        """
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
        '--dialogue-col',
        type=str,
        default='Dialogue',
        help='CSV 中 Dialogue 列的列名（默认：Dialogue）'
    )
    
    parser.add_argument(
        '--max-sentence-length',
        type=int,
        default=30,
        help='单个字幕的最大字符数（默认：30）'
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


def is_parentheses_only(text):
    """
    检查文本是否只包含括号内容
    
    Args:
        text: 待检查文本
    
    Returns:
        bool: 如果只包含括号内容返回True
    """
    pattern = r'^（[^）]*）\.$'
    return bool(re.match(pattern, text.strip()))


def split_sentences_smart(text, max_length=30):
    """
    智能短句功能：将文本分割成多个句子，处理逗号和省略号
    
    Args:
        text: 原始文本
        max_length: 单个句子的最大长度
    
    Returns:
        list: 分割后的句子列表
    """
    if not text:
        return []
    
    text = text.strip()
    
    # 检查是否只包含括号内容
    if is_parentheses_only(text):
        return [text]
    
    # 定义分句标点符号（包括省略号）
    punctuation_pattern = r'([。！？!?……])'
    
    # 首先在标点符号处分割
    parts = re.split(punctuation_pattern, text)
    
    sentences = []
    
    for i in range(0, len(parts), 2):
        part = parts[i]
        if i + 1 < len(parts):
            part += parts[i + 1]
        
        part = part.strip()
        if not part:
            continue
        
        sentences.append(part)
    
    # 如果只有一个句子但包含逗号，检查是否需要在逗号处分句
    if len(sentences) == 1:
        sentence = sentences[0]
        # 检查句号前的逗号数量
        if '。' in sentence:
            before_period = sentence.split('。')[0]
            comma_count = before_period.count('，') + before_period.count(',')
            
            # 如果逗号较多（3个或以上），在最后一个逗号处分句
            if comma_count >= 3:
                # 找到最后一个逗号的位置
                last_comma_pos = max(before_period.rfind('，'), before_period.rfind(','))
                if last_comma_pos != -1:
                    part1 = sentence[:last_comma_pos + 1].strip()
                    part2 = sentence[last_comma_pos + 1:].strip()
                    sentences = [part1, part2]
    
    return sentences


def merge_timecodes(timecodes):
    """
    合并时间轴：只保留两条时间轴
    
    Args:
        timecodes: 原始时间轴列表
    
    Returns:
        list: 合并后的时间轴列表
    """
    if len(timecodes) <= 2:
        return timecodes
    
    # 取第一个时间轴的开始时间和倒数第二个时间轴的结束时间
    first_start = timecodes[0].split('-->')[0].strip()
    
    # 取倒数第二个时间轴的结束时间
    if len(timecodes) >= 2:
        last_end = timecodes[-2].split('-->')[1].strip()
    else:
        last_end = timecodes[-1].split('-->')[1].strip()
    
    # 取最后一个时间轴
    last_timecode = timecodes[-1]
    
    return [f'{first_start} --> {last_end}', last_timecode]


def update_srt_file(srt_path, dialogue, max_sentence_length=30):
    """
    更新单个 SRT 文件的内容，保留时间戳
    
    Args:
        srt_path: SRT 文件路径
        dialogue: 新的对话内容
        max_sentence_length: 单个字幕的最大长度
    """
    if not os.path.exists(srt_path):
        print(f'  警告: 文件不存在，跳过: {srt_path}')
        return False
    
    # 读取原始 SRT 文件
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 解析 SRT，保留时间戳
    lines = content.strip().split('\n')
    timecodes = []
    
    i = 0
    while i < len(lines):
        if '-->' in lines[i]:
            timecodes.append(lines[i].strip())
            # 跳过字幕文本直到空行
            i += 1
            while i < len(lines) and lines[i].strip():
                i += 1
        i += 1
    
    # 检查是否只包含括号内容
    if is_parentheses_only(dialogue):
        # 只保留一个时间轴，内容是完整的括号内容
        sentences = [dialogue]
        use_timecodes = [timecodes[0]] if timecodes else []
    else:
        # 智能分割对话内容
        sentences = split_sentences_smart(dialogue, max_sentence_length)
        
        # 如果有多个时间轴，只保留前两条（合并时间）
        if len(timecodes) > 2:
            use_timecodes = merge_timecodes(timecodes)
        else:
            use_timecodes = timecodes
        
        # 调整句子数量以匹配时间轴数量
        if len(sentences) > len(use_timecodes):
            sentences = sentences[:len(use_timecodes)]
        elif len(sentences) < len(use_timecodes):
            while len(sentences) < len(use_timecodes):
                sentences.append('')
    
    # 生成新的 SRT 内容（不包含数字标号）
    new_content = []
    for timecode, sentence in zip(use_timecodes, sentences):
        new_content.append(timecode)
        new_content.append(sentence)
        new_content.append('')  # 空行分隔
    
    # 写入文件
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_content))
    
    return True


def main():
    args = parse_arguments()
    
    csv_file = Path(args.csv_file)
    target_dir = Path(args.target_dir)
    
    # 检查文件是否存在
    if not csv_file.exists():
        print(f'错误: CSV 文件不存在: {csv_file}')
        return 1
    
    if not target_dir.exists():
        print(f'错误: 目标目录不存在: {target_dir}')
        return 1
    
    print(f'正在读取 CSV 文件: {csv_file}')
    data = read_csv_file(str(csv_file), args.key_col, args.dialogue_col)
    print(f'找到 {len(data)} 条有内容的记录')
    
    success_count = 0
    skipped_count = 0
    
    print(f'\n正在更新 SRT 文件（目标目录: {target_dir}）:')
    for key, dialogue in data.items():
        srt_filename = f'{key}.srt'
        srt_path = target_dir / srt_filename
        
        print(f'处理: {key}')
        if update_srt_file(str(srt_path), dialogue, args.max_sentence_length):
            success_count += 1
        else:
            skipped_count += 1
    
    print(f'\n完成！')
    print(f'成功更新: {success_count} 个文件')
    print(f'跳过: {skipped_count} 个文件')
    
    return 0


if __name__ == '__main__':
    exit(main())
