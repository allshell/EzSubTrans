# translator.py
import openai
import re
import time
from typing import List, Tuple, Optional

SYSTEM_PROMPT_TEMPLATE = (
    "将以下{context}**{source_language}**字幕逐行翻译为**{target_language}**。"
    "每行格式为 [数字] 内容。保持行数一致，仅翻译内容部分，不要更改编号和格式。"
    "例如，输入 '[1] Hello world'，如果目标语言是法语，你应该只输出 '[1] Bonjour le monde'。"
    "请确保严格按照此格式输出，不要添加任何额外的解释或注释。"
)

SYSTEM_PROMPT_WITH_SUMMARY_TEMPLATE = (
    "你将处理的是**{source_language}**字幕的逐行翻译任务，目标语言为**{target_language}**。\n\n"
    "为了更准确地把握语境，以下是完整字幕的简要内容摘要：\n{summary}\n\n"
    "请据此进行逐行翻译。"
    "每行格式为 [数字] 内容。保持行数一致，仅翻译内容部分，不要更改编号和格式。"
    "例如，输入 '[1] Hello world'，如果目标语言是法语，你应该只输出 '[1] Bonjour le monde'。"
    "请确保严格按照此格式输出，不要添加任何额外的解释或注释。"
)

class TranslationError(Exception):
    pass

def translate_batch(
    texts: List[str],
    api_key: str,
    api_base: str,
    model: str,
    system_prompt: str,
    temperature: float = 1.3,
    max_retries: int = 1
) -> Tuple[List[str], Optional[str]]:
    client = openai.OpenAI(
        base_url=api_base,
        api_key=api_key,
    )

    numbered_texts = [f"[{i+1}] {line}" for i, line in enumerate(texts)]
    combined_text = "\n".join(numbered_texts)

    prompt = system_prompt.strip() or SYSTEM_PROMPT_TEMPLATE.format(context="")

    def get_translation_attempt():
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": combined_text}
            ]
        )
        return response.choices[0].message.content

    for attempt in range(max_retries + 1):
        try:
            raw_translation = get_translation_attempt()
            extracted = re.findall(r"\[(\d+)]\s*(.*)", raw_translation)
            translated_lines = [""] * len(texts)

            processed_indices = set()
            for idx_str, content in extracted:
                try:
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(texts) and idx not in processed_indices:
                        translated_lines[idx] = content.strip()
                        processed_indices.add(idx)
                except ValueError:
                    continue

            if len(processed_indices) == len(texts) and all(translated_lines):
                return translated_lines, None

            warning_msg = f"行数不一致或提取不完整 (尝试 {attempt + 1}/{max_retries + 1})"
            if attempt < max_retries:
                time.sleep(1)
        except Exception as e:
            if attempt >= max_retries:
                return _prepare_failure_output(texts, f"异常: {e}")
            time.sleep(1)

    final_warning = f"⚠️ 翻译失败或行数不一致 (尝试 {max_retries + 1} 次后)"
    return _prepare_failure_output(texts, final_warning, translated_lines if 'translated_lines' in locals() else None)

def _prepare_failure_output(original_texts, warning_prefix, partial_translations=None):
    if partial_translations is None:
        partial_translations = [""] * len(original_texts)
    filled_lines = [
        t if t else f"[原文保留] {original_texts[i]}"
        for i, t in enumerate(partial_translations)
    ]
    if filled_lines:
        filled_lines[0] = warning_prefix + r"\N" + filled_lines[0]
    elif original_texts:
        filled_lines = [warning_prefix + r"\N" + f"[原文保留] {original_texts[0]}"] +                        [f"[原文保留] {ot}" for ot in original_texts[1:]]
    return filled_lines, warning_prefix

def summarize_subtitles(
    texts: List[str],
    api_key: str,
    api_base: str,
    model: str,
    temperature: float = 0.3
) -> str:
    client = openai.OpenAI(
        base_url=api_base,
        api_key=api_key,
    )
    combined_text = "\n".join(texts)
    if len(combined_text) > 12000:
        combined_text = combined_text[:12000]
    prompt = "你是一位字幕分析助手。请简洁扼要地总结以下字幕的主要内容和风格，控制在200字以内。不要加入你自己的评论。"
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": combined_text}
        ]
    )
    return response.choices[0].message.content.strip()
