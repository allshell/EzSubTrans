# subtitle_parser.py
import pysubs2
import os
from typing import List, Tuple, Optional

class SubtitleHandlingError(Exception):
    # 自定义字幕解析/保存错误的例外情况
    pass

def load_subtitles(filepath: str) -> Tuple[pysubs2.SSAFile, List[str]]:#从文件中加载字幕
    """
    参数:
        filepath: 字幕文件路径 (.ass 或 .srt)
    返回:
        包含已加载 pysubs2 对象和文本行列表的元组
    引发:
        SubtitleHandlingError: 如果文件无法加载或无效
        FileNotFoundError: 如果文件不存在
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"未找到输入文件: {filepath}")
    try:
        subs = pysubs2.load(filepath)
        texts = [line.text for line in subs]
        return subs, texts
    except Exception as e:
        # 广谱异常捕捉，应对 pysubs2 的各种可能错误
        raise SubtitleHandlingError(f"加载字幕文件 {filepath} 时出错: {e}") from e

def save_subtitles(subs: pysubs2.SSAFile, output_path: str, translated_texts: List[str], original_num_lines: Optional[int] = None):#用翻译好的文本更新字幕对象并保存
    """
    参数：
        subs: 要修改的 pysubs2 对象
        output_path: 保存翻译字幕文件的路径
        translated_texts: 翻译文本行列表
        original_num_lines: 预期行数（用于验证）
    引发:
        SubtitleHandlingError: 如果保存过程中出现错误或长度不匹配
    """
    if original_num_lines is None:
        original_num_lines = len(subs)

    # 处理可能的长度不匹配问题
    if len(translated_texts) < original_num_lines:
        print(f"警告: 翻译字幕行数 ({len(translated_texts)}) 少于原始行数 ({original_num_lines})，使用占位符填充。")
        translated_texts += ["⚠️[翻译缺失]"] * (original_num_lines - len(translated_texts))
    elif len(translated_texts) > original_num_lines:
        print(f"警告: 翻译字幕行数 ({len(translated_texts)}) 超出原始行数 ({original_num_lines})，截断。")
        translated_texts = translated_texts[:original_num_lines]

    # 更新文本行
    for i, line in enumerate(subs):
        if i < len(translated_texts):
             line.text = translated_texts[i]
        else:
             # 最好由前面部分处理，此处为 fallback
             line.text = "⚠️[索引超出]"

    try:
        subs.save(output_path)
        print(f"字幕成功保存至 {output_path}")
    except Exception as e:
        raise SubtitleHandlingError(f"保存字幕文件 {output_path} 时出错: {e}") from e
