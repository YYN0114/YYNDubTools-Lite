#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# YYN0114配音工具(Lite) —— 字幕 / 配音批处理工具（内嵌脚本）
# Copyright (C) 2026 ENOCH0114
#
# 本程序为自由软件：可依据 GNU 通用公共许可证（GPL）第 3 版或任何更新版本
# 重新分发和 / 或修改；按「现状」提供，不含任何担保。
# 许可全文见随附 LICENSE，或 <https://www.gnu.org/licenses/gpl-3.0.html>。
"""
WAV转OGG脚本：批量转换为单声道OGG

用途：递归把输入目录下的 .wav 批量转成单声道 OGG Vorbis。
输入：--input-dir 输入目录（递归收集 .wav）。
输出：--output-dir 指定则按原目录结构写入其中，否则生成在源 wav 同目录。

说明：
  - 输出为单声道OGG Vorbis（采样率与源文件一致）
  - 跳过已存在的ogg文件
  - 注：OGG Vorbis为有损格式，内部使用浮点处理，"16位"概念不适用；
       品质由-q:a参数控制（0-10，3为默认，约等效于112kbps）

使用方法：
  python wav_to_ogg.py --input-dir "<输入目录>" [--output-dir "<输出目录>"]
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# ffmpeg 可执行文件路径；留空 = 自动在系统 PATH 中查找。
# GUI 运行时会注入「目录设置」里填写的绝对路径。
FFMPEG_PATH = ''

# 上一次转换的统计（供 GUI 组装完成提醒，如「成功 x / 跳过 y / 失败 z」）
LAST_STATS: dict = {}


def convert_wav_to_ogg(ffmpeg, wav_path, ogg_path):
    """调用ffmpeg将wav转为单声道OGG Vorbis
    返回 (成功, 错误信息)
    """
    cmd = [
        ffmpeg,
        '-y',               # 覆盖输出
        '-i', str(wav_path),
        '-ac', '1',         # 单声道
        '-c:a', 'libvorbis',  # OGG Vorbis编码
        '-q:a', '3',        # 音质（0-10，3为默认，约等效112kbps）
        str(ogg_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return (True, '')
        return (False, result.stderr.decode('utf-8', errors='replace').strip()[-500:])
    except Exception as e:
        return (False, str(e))


def main():
    parser = argparse.ArgumentParser(description='WAV转OGG（单声道）')
    parser.add_argument('--input-dir', type=str, required=True,
                        help='输入目录（递归处理所有.wav）')
    parser.add_argument('--output-dir', type=str, default='',
                        help='输出目录（不指定则生成在wav同目录）')
    args = parser.parse_args()

    global LAST_STATS
    LAST_STATS = {}                      # 先清空，避免上一次的统计残留被误读

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f'错误: 输入目录不存在: {input_dir}')
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    # ffmpeg 取用顺序：显式配置的路径 → 系统 PATH 中的 ffmpeg
    ffmpeg = FFMPEG_PATH or shutil.which('ffmpeg') or ''
    if not ffmpeg or not Path(ffmpeg).exists():
        print(f'错误: 找不到 ffmpeg（请指定路径，或把它加入系统 PATH）: {ffmpeg or "未找到"}')
        return 1

    # 递归收集wav
    wav_files = sorted(input_dir.rglob('*.wav'))
    if not wav_files:
        print(f'未找到wav文件: {input_dir}')
        return 0

    print(f'ffmpeg: {ffmpeg}')
    print(f'输入目录: {input_dir}')
    print(f'输出模式: {"指定输出目录 " + str(output_dir) if output_dir else "与源文件同目录"}')
    print(f'找到 {len(wav_files)} 个wav文件')
    print('=' * 60)

    total = 0
    success = 0
    skip = 0
    fail = 0

    for wav_path in wav_files:
        total += 1

        # 计算输出路径（保留子目录结构）
        if output_dir:
            rel = wav_path.relative_to(input_dir)
            ogg_path = output_dir / rel.with_suffix('.ogg')
            ogg_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            ogg_path = wav_path.with_suffix('.ogg')

        # 跳过已存在
        if ogg_path.exists():
            skip += 1
            continue

        ok, err = convert_wav_to_ogg(ffmpeg, wav_path, ogg_path)
        if ok:
            success += 1
            if total % 50 == 0 or total == len(wav_files):
                print(f'  [{total}/{len(wav_files)}] {wav_path.name} -> OK')
        else:
            fail += 1
            print(f'  [FAIL] {wav_path}: {err[:200]}')

    LAST_STATS = {"total": total, "success": success, "skip": skip, "fail": fail}

    print('=' * 60)
    print(f'总计: {total}  成功: {success}  跳过: {skip}  失败: {fail}')
    if output_dir:
        print(f'输出目录: {output_dir}')
    print('=' * 60)

    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
