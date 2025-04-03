import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
import time
import json
import pysubs2
import openai
import datetime
import re

# ------------------ 配置保存 ------------------

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ------------------ 翻译逻辑 ------------------

SYSTEM_PROMPT_TEMPLATE = (
    "将以下{context}英文字幕逐行翻译为简体中文。"
    "每行格式为 [数字] 内容。保持行数一致，仅翻译内容部分，不要更改编号。"
)

def translate_batch(texts, temperature=1.3, api_base=None, api_key=None, model="", system_prompt="", max_retries=1):
    openai.base_url = api_base
    openai.api_key = api_key

    numbered_texts = [f"[{i+1}] {line}" for i, line in enumerate(texts)]
    combined_text = "\n".join(numbered_texts)

    prompt = (
        system_prompt.strip()
        or "将以下英文字幕逐行翻译为简体中文，每行格式为 [数字] 内容。保持行数一致，仅翻译内容部分，不要更改编号。"
    )

    def get_translation():
        response = openai.chat.completions.create(
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
            translation = get_translation()

            # 提取编号和内容
            extracted = re.findall(r"\[(\d+)]\s*(.*)", translation)
            translated_lines = ["" for _ in texts]

            for idx_str, content in extracted:
                idx = int(idx_str) - 1
                if 0 <= idx < len(texts):
                    translated_lines[idx] = content.strip()

            if all(translated_lines):
                return translated_lines, None  # 翻译成功

        except Exception as e:
            return texts, f"翻译异常：{e}"

        if attempt == 0:
            print("翻译行数不一致或提取失败，重试中...")

    # 最终失败，插入警告 + 原文保留
    warning = f"⚠️ 翻译失败或行数不一致：原 {len(texts)} 行"
    filled = [line if line else f"[原文保留] {texts[i]}" for i, line in enumerate(translated_lines)]
    filled[0] = warning + r"\N" + filled[0]
    return filled, warning

# ------------------ 主翻译流程 ------------------

stop_translation_flag = False  # 用户中断标志

def run_translation(input_path, output_path, window_size, temperature, api_base, api_key, model_name, system_prompt, retry_times):
    eta_label.config(text="")
    try:
        subs = pysubs2.load(input_path)
        texts = [line.text for line in subs]
        translated_texts = []

        total = len(texts)
        progress_bar["maximum"] = total
        durations = []

        eta_label.config(text=f"总行数：{total}\n等待至少2个窗口以计算剩余时间...")

        for i in range(0, total, window_size):
            if stop_translation_flag:
                break  # 用户手动中断

            batch = texts[i:i+window_size]
            batch_start = time.time()

            status_label.config(text=f"翻译第 {i+1}-{i+len(batch)} 行...")
            root.update_idletasks()

            translated_batch, warning = translate_batch(
                batch,
                temperature=temperature,
                api_base=api_base,
                api_key=api_key,
                model=model_name,
                system_prompt=system_prompt,
                max_retries=retry_times
            )

            batch_end = time.time()
            durations.append(batch_end - batch_start)

            if warning:
                status_label.config(text=f"第 {i+1}-{i+len(batch)} 行：{warning}")
                print(warning)
            else:
                status_label.config(text=f"完成第 {i+1}-{i+len(batch)} 行")

            translated_texts.extend(translated_batch)
            progress_bar["value"] = len(translated_texts)
            root.update_idletasks()

            # 显示 ETA
            if len(durations) >= 2:
                avg_time = sum(durations) / len(durations)
                remaining = (total - (i + len(batch))) // window_size
                eta_seconds = int(avg_time * remaining)
                eta_str = str(datetime.timedelta(seconds=eta_seconds))
                status_label.config(text=f"完成第 {i+1}-{i+len(batch)} 行")
                eta_label.config(text=f"总行数：{total}\n预计剩余时间：{eta_str}")

            root.update_idletasks()
            time.sleep(1)

        # 应对意外长度不一致
        if len(translated_texts) < len(subs):
            translated_texts += ["⚠️ 翻译缺失"] * (len(subs) - len(translated_texts))
        elif len(translated_texts) > len(subs):
            translated_texts = translated_texts[:len(subs)]

        for i, line in enumerate(subs):
            line.text = translated_texts[i]
        
        # 判断是否被用户终止
        if stop_translation_flag:
            for i, line in enumerate(subs[:len(translated_texts)]):
                line.text = translated_texts[i]
            partial_output = output_path.replace(".ass", "_partial.ass")
            subs.save(partial_output)
            status_label.config(text=f"用户终止，部分翻译保存至：{partial_output}")
            eta_label.config(text=f"总行数：{total}\n翻译被中止")
            messagebox.showwarning("中止", f"翻译被用户中止，已保存部分结果到：{partial_output}")
            return

        subs.save(output_path)
        status_label.config(text="翻译完成！")
        eta_label.config(text="所有翻译已完成")
        messagebox.showinfo("完成", f"翻译完成，已保存至：{output_path}")

    except Exception as e:
        status_label.config(text="翻译失败")
        messagebox.showerror("错误", str(e))

# ------------------ Tooltip 工具 ------------------

class CreateToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, _cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + cy + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("arial", "10", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

# ------------------ GUI 控制 ------------------

def start_translation():
    global stop_translation_flag, system_prompt
    stop_translation_flag = False
    input_path = input_entry.get()
    output_path = output_entry.get()
    window_size = int(window_entry.get())
    temperature = float(temp_entry.get())
    api_base = api_base_entry.get()
    api_key = api_key_entry.get()
    model_name = model_entry.get()
    retry_times = int(retry_entry.get())

    if not os.path.exists(input_path):
        messagebox.showerror("错误", "输入文件不存在！")
        return

    if not output_path:
        ext = os.path.splitext(input_path)[1]
        output_path = input_path.replace(ext, f"_cn{ext}")
        output_entry.delete(0, tk.END)
        output_entry.insert(0, output_path)

    save_config({
        "api_base": api_base,
        "api_key": api_key,
        "model_name": model_name
    })

    threading.Thread(target=run_translation, args=(
        input_path, output_path, window_size, temperature, api_base, api_key, model_name, system_prompt, retry_times
    )).start()

def stop_translation():
    global stop_translation_flag
    stop_translation_flag = True
    stop_button.config(state="disabled")
    status_label.config(text="终止请求已发送，请等待当前段翻译完成...")
    eta_label.config(text="处理中...")
    root.update_idletasks()

def browse_input():
    file_path = filedialog.askopenfilename(filetypes=[("字幕文件", "*.ass *.srt")])
    if file_path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, file_path)

        # 自动填写输出路径
        base, ext = os.path.splitext(file_path)
        if ext.lower() in [".ass", ".srt"]:
            output_path = f"{base}_cn{ext}"
            output_entry.delete(0, tk.END)
            output_entry.insert(0, output_path)

def browse_output():
    default_ext = ".ass" if input_entry.get().lower().endswith(".ass") else ".srt"
    file_path = filedialog.asksaveasfilename(defaultextension=default_ext, filetypes=[("字幕文件", "*.ass *.srt")])
    output_entry.delete(0, tk.END)
    output_entry.insert(0, file_path)

def show_about():
    about_window = tk.Toplevel(root)
    about_window.title("关于")
    about_window.geometry("400x250")
    about_window.resizable(False, False)

    info = (
        "EzSubTrans v0.3\n\n"
        "基本功能：调用大语言模型 API 实现字幕文件直接翻译\n"
        "目前支持 .srt 与 .ass 格式\n\n"
        "警告：该工具会在 config 文件中明文存储 API key\n         切勿随意分享 config 文件"
    )

    tk.Label(about_window, text=info, justify="left", anchor="w", padx=20, pady=20).pack(fill="both", expand=True)
    tk.Button(about_window, text="关闭", command=about_window.destroy).pack(pady=10)

# ------------------ 界面布局 ------------------

root = tk.Tk()
root.title("EzSubTrans v0.3")
root.geometry("520x420")

tk.Label(root, text="输入字幕文件").grid(row=0, column=0, padx=5, pady=5, sticky="e")
input_entry = tk.Entry(root, width=50)
input_entry.grid(row=0, column=1)
tk.Button(root, text="浏览", command=browse_input).grid(row=0, column=2)

tk.Label(root, text="输出字幕文件").grid(row=1, column=0, padx=5, pady=5, sticky="e")
output_entry = tk.Entry(root, width=50)
output_entry.grid(row=1, column=1)
tk.Button(root, text="保存为", command=browse_output).grid(row=1, column=2)

window_label_frame = tk.Frame(root)
window_label_frame.grid(row=2, column=0, sticky="e")
tk.Label(window_label_frame, text="窗口大小").pack(side="left")
window_q = tk.Label(window_label_frame, text="?", fg="blue", cursor="question_arrow")
window_q.pack(side="left")
CreateToolTip(window_q, "每次提交翻译的字幕行数，越大则整体速度越快且语境理解越好，但越可能导致结果行数错乱")
window_entry = tk.Entry(root)
window_entry.insert(0, "10")
window_entry.grid(row=2, column=1, sticky="w")

temp_label_frame = tk.Frame(root)
temp_label_frame.grid(row=2, column=1, sticky="e")
tk.Label(temp_label_frame, text="温度").pack(side="left")
temp_q = tk.Label(temp_label_frame, text="?", fg="blue", cursor="question_arrow")
temp_q.pack(side="left")
CreateToolTip(temp_q, "控制模型创造力，高温更能灵活发挥，低温更能遵守指令")
temp_entry = tk.Entry(root, width=5)
temp_entry.insert(0, "1.3")
temp_entry.grid(row=2, column=2, sticky="w")

context_label_frame = tk.Frame(root)
context_label_frame.grid(row=3, column=0, sticky="e")
tk.Label(context_label_frame, text="背景描述（可选）").pack(side="left")
context_q = tk.Label(context_label_frame, text="?", fg="blue", cursor="question_arrow")
context_q.pack(side="left")
CreateToolTip(context_q, "用一个词组简要描述字幕文件的主题，例如“天体物理”或“美食节目”，有助于提升翻译质量\n如留空则使用内置通用指令")
context_entry = tk.Entry(root)
context_entry.grid(row=3, column=1, sticky="w")
# 拼接字幕背景信息
context = context_entry.get().strip()
if context:
    context_prefix = f"关于{context}的"
else:
    context_prefix = ""
system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context_prefix)

retry_label_frame = tk.Frame(root)
retry_label_frame.grid(row=3, column=1, sticky="e")
tk.Label(retry_label_frame, text="最大重试次数").pack(side="left")
retry_q = tk.Label(retry_label_frame, text="?", fg="blue", cursor="question_arrow")
retry_q.pack(side="left")
CreateToolTip(retry_q, "翻译失败时重新尝试的最大次数")
retry_entry = tk.Entry(root, width=5)
retry_entry.insert(0, "1")
retry_entry.grid(row=3, column=2, sticky="w")

tk.Label(root, text="API Base URL").grid(row=4, column=0, sticky="e")
api_base_entry = tk.Entry(root, width=50)
api_base_entry.grid(row=4, column=1, columnspan=2)

tk.Label(root, text="API Key").grid(row=5, column=0, sticky="e")
api_key_entry = tk.Entry(root, width=50, show="*")
api_key_entry.grid(row=5, column=1, columnspan=2)

tk.Label(root, text="模型名称").grid(row=6, column=0, sticky="e")
model_entry = tk.Entry(root, width=50)
model_entry.grid(row=6, column=1, columnspan=2)

tk.Button(root, text="开始翻译", command=start_translation, width=20).grid(row=8, column=1, pady=15)
stop_button = tk.Button(root, text="终止翻译", command=stop_translation, width=20)
stop_button.grid(row=9, column=1, pady=0)

progress_bar = ttk.Progressbar(root, length=400, mode='determinate')
progress_bar.grid(row=10, column=0, columnspan=3, pady=15)

status_label = tk.Label(root, text="", anchor="center", justify="center")
status_label.grid(row=11, column=0, columnspan=3, pady=2)

eta_label = tk.Label(root, text="", anchor="center", justify="center")
eta_label.grid(row=12, column=0, columnspan=3, pady=2)

tk.Button(root, text="关于", command=show_about).grid(row=13, column=2, sticky="e", pady=5, padx=10)

# 载入配置
config = load_config()
api_base_entry.insert(0, config.get("api_base", "https://api.openai.com/v1"))
api_key_entry.insert(0, config.get("api_key", ""))
model_entry.insert(0, config.get("model_name", "gpt-4o-mini"))

root.mainloop()