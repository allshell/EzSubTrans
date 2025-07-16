# subtitle_parser.py
import pysubs2
import os
from typing import List, Tuple, Optional

class SubtitleHandlingError(Exception):
    pass

def load_subtitles(filepath: str) -> Tuple[pysubs2.SSAFile, List[str]]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"未找到输入文件: {filepath}")
    try:
        subs = pysubs2.load(filepath)
        texts = [line.text for line in subs]
        return subs, texts
    except Exception as e:
        raise SubtitleHandlingError(f"加载字幕文件 {filepath} 时出错: {e}") from e

def save_subtitles(subs: pysubs2.SSAFile, output_path: str, translated_texts: List[str], original_num_lines: Optional[int] = None):
    if original_num_lines is None:
        original_num_lines = len(subs)

    if len(translated_texts) < original_num_lines:
        print(f"警告: 翻译字幕行数 ({len(translated_texts)}) 少于原始行数 ({original_num_lines})，使用占位符填充。")
        translated_texts += ["⚠️[翻译缺失]"] * (original_num_lines - len(translated_texts))
    elif len(translated_texts) > original_num_lines:
        print(f"警告: 翻译字幕行数 ({len(translated_texts)}) 超出原始行数 ({original_num_lines})，截断。")
        translated_texts = translated_texts[:original_num_lines]

    for i, line in enumerate(subs):
        if i < len(translated_texts):
             line.text = translated_texts[i]
        else:
             line.text = "⚠️[索引超出]"

    try:
        subs.save(output_path)
        print(f"字幕成功保存至 {output_path}")
    except Exception as e:
        raise SubtitleHandlingError(f"保存字幕文件 {output_path} 时出错: {e}") from e
