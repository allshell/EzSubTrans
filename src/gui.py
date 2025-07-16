# gui.py
import tkinter as tk
from tkinter import font as tkFont
import sys
if sys.platform == "win32":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
from tkinter import filedialog, messagebox, ttk
import threading
import os
import time
import datetime
import webbrowser

from config_manager import load_config, save_config, DEFAULT_CONFIG
from subtitle_parser import load_subtitles, save_subtitles, SubtitleHandlingError
from translator import translate_batch, TranslationError, SYSTEM_PROMPT_TEMPLATE, SYSTEM_PROMPT_WITH_SUMMARY_TEMPLATE

stop_translation_flag = False

total_subtitle_lines = 0

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

def update_status(text):
    if status_label:
        status_label.config(text=text)
        root.update_idletasks()

def update_eta(text):
    if eta_label:
        eta_label.config(text=text)
        root.update_idletasks()

def update_progress(value, maximum):
    if progress_bar:
        progress_bar["maximum"] = maximum
        progress_bar["value"] = value
        root.update_idletasks()

def update_preview_widgets(original_texts, translated_texts):
    try:
        original_text_widget.config(state=tk.NORMAL)
        translated_text_widget.config(state=tk.NORMAL)

        original_text_widget.delete('1.0', tk.END)
        translated_text_widget.delete('1.0', tk.END)

        original_text_widget.insert(tk.END, "\n".join(original_texts))
        translated_text_widget.insert(tk.END, "\n".join(translated_texts))

        original_text_widget.config(state=tk.DISABLED)
        translated_text_widget.config(state=tk.DISABLED)
    except tk.TclError as e:
        print(f"更新预览窗口时出错（可能窗口已关闭）: {e}")


def show_info(title, message):
    messagebox.showinfo(title, message)

def show_warning(title, message):
    messagebox.showwarning(title, message)

def show_error(title, message):
    messagebox.showerror(title, message)

def translation_worker(input_path, output_path, window_size, temperature, api_base, api_key, translation_model, system_prompt, retry_times):
    global stop_translation_flag
    start_button.config(state="disabled")
    stop_button.config(state="normal")
    update_eta("")
    root.after(0, update_preview_widgets, ["翻译即将开始..."], [""])

    try:
        update_status("加载字幕文件中...")
        subs, texts = load_subtitles(input_path)
        original_num_lines = len(texts)
        update_status(f"加载完成，共 {original_num_lines} 行")

        translated_texts = []
        durations = []
        update_progress(0, original_num_lines)
        update_eta(f"总行数：{original_num_lines}\n等待至少2个窗口以计算剩余时间...")

        for i in range(0, original_num_lines, window_size):
            if stop_translation_flag:
                update_status("用户请求中断...")
                break

            batch_texts = texts[i : i + window_size]
            current_batch_info = f"行 {i + 1} - {min(i + len(batch_texts), original_num_lines)}"
            update_status(f"开始翻译 {current_batch_info}...")

            batch_start_time = time.time()

            batch_translated, warning_msg = translate_batch(
                texts=batch_texts,
                api_key=api_key,
                api_base=api_base,
                model=translation_model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_retries=retry_times
            )

            batch_end_time = time.time()
            durations.append(batch_end_time - batch_start_time)
            
            root.after(0, update_preview_widgets, batch_texts, batch_translated)

            if warning_msg:
                 update_status(f"{current_batch_info}: {warning_msg}")
                 print(f"翻译 {current_batch_info} 时出现警告/错误: {warning_msg}")
            else:
                 update_status(f"完成翻译 {current_batch_info}")

            translated_texts.extend(batch_translated)
            update_progress(len(translated_texts), original_num_lines)

            if len(durations) >= 2:
                avg_time_per_batch = sum(durations) / len(durations)
                remaining_batches = (original_num_lines - len(translated_texts) + window_size - 1) // window_size
                eta_seconds = int(avg_time_per_batch * remaining_batches)
                eta_str = str(datetime.timedelta(seconds=eta_seconds))
                update_eta(f"总行数：{original_num_lines}\n预计剩余时间：{eta_str}")
            else:
                 update_eta(f"总行数：{original_num_lines}\n正在计算剩余时间...")

        if stop_translation_flag:
            partial_output_path = output_path.replace(".ass", "_partial.ass").replace(".srt", "_partial.srt")
            update_status(f"正在保存部分结果至 {partial_output_path}...")
            try:
                save_subtitles(subs, partial_output_path, translated_texts, original_num_lines)
                update_status(f"用户终止，部分翻译已保存至 {partial_output_path}")
                update_eta(f"总行数：{original_num_lines}\n翻译被中止")
                show_warning("中止", f"翻译被用户中止。\n已保存部分结果到:\n{partial_output_path}")
            except SubtitleHandlingError as e:
                update_status(f"保存部分结果时出错: {e}")
                show_error("保存错误", f"保存部分结果时出错:\n{e}")
        else:
            update_status(f"正在保存完整结果至 {output_path}...")
            try:
                save_subtitles(subs, output_path, translated_texts, original_num_lines)
                update_status("翻译完成！")
                update_eta("所有翻译已完成。")
                show_info("完成", f"翻译完成!\n已保存至:\n{output_path}")
            except SubtitleHandlingError as e:
                update_status(f"保存结果时出错: {e}")
                show_error("保存错误", f"保存结果时出错:\n{e}")

    except FileNotFoundError as e:
        update_status("错误：输入文件未找到")
        show_error("文件错误", str(e))
    except SubtitleHandlingError as e:
        update_status(f"字幕处理错误: {e}")
        show_error("字幕错误", str(e))
    except TranslationError as e:
         update_status(f"翻译错误: {e}")
         show_error("翻译错误", str(e))
    except Exception as e:
        update_status(f"发生意外错误: {e}")
        show_error("意外错误", f"发生未预料的错误:\n{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        stop_translation_flag = False
        start_button.config(state="normal")
        stop_button.config(state="disabled")
        update_progress(0, 1)

def handle_test_api():
    api_base = api_base_entry.get().strip()
    api_key = api_key_entry.get().strip()
    
    translation_model = model_entry.get().strip()
    summary_model = summary_model_entry.get().strip()
    
    model_to_test = translation_model
    model_label = "翻译模型"
    
    if use_deep_summary_var.get() and summary_model:
        model_to_test = summary_model
        model_label = "摘要模型"

    if not api_key or not model_to_test:
        show_error("配置错误", f"API Key 和 {model_label} 名称不能为空。")
        return

    test_button.config(text="正在测试...", state="disabled")
    root.update_idletasks()

    def test_thread():
        try:
            import openai
            client = openai.OpenAI(base_url=api_base, api_key=api_key)

            response = client.chat.completions.create(
                model=model_to_test,
                messages=[
                    {"role": "system", "content": "你是一个测试助手，这是一次简单测试。"},
                    {"role": "user", "content": "请回复\"你好，世界！\"，不要添加任何多余内容。"}
                ],
                temperature=0.1
            )
            reply = response.choices[0].message.content.strip()
            show_info("配置成功", f"成功连接！{model_label} ({model_to_test}) 返回：\n“{reply}”")
        except openai.AuthenticationError:
            show_error("认证失败", "API Key 无效，请检查是否输入正确。")
        except openai.NotFoundError:
            show_error("模型错误", f"指定的 {model_label} ({model_to_test}) 无效或不存在。")
        except openai.OpenAIError as e:
            show_error("OpenAI 错误", f"请求失败：\n{type(e).__name__}: {e}")
        except Exception as e:
            show_error("连接失败", f"无法连接 API：\n{type(e).__name__}: {e}")
        finally:
            test_button.config(text="测试配置", state="normal")

    threading.Thread(target=test_thread, daemon=True).start()

def handle_start_translation():
    global stop_translation_flag
    stop_translation_flag = False

    input_path = input_entry.get()
    output_path = output_entry.get()

    try:
        window_size = int(window_entry.get())
        temperature = float(temp_entry.get())
        retry_times = int(retry_entry.get())
        if window_size <= 0 or temperature < 0 or retry_times < 0:
            raise ValueError("数值必须为正")
    except ValueError as e:
        show_error("输入错误", f"窗口大小、温度和重试次数必须是有效的正数: {e}")
        return

    source_language = source_lang_entry.get().strip()
    target_language = target_lang_entry.get().strip()

    api_base = api_base_entry.get()
    api_key = api_key_entry.get()
    translation_model = model_entry.get().strip()
    summary_model = summary_model_entry.get().strip()
    context_desc = context_entry.get().strip()

    if not input_path or not os.path.exists(input_path):
        show_error("错误", "输入文件无效或不存在！")
        return
    if not source_language:
        show_error("错误", "源语言不能为空！")
        return
    if not target_language:
        show_error("错误", "目标语言不能为空！")
        return
    if not api_key:
        show_error("错误", "API Key 不能为空！")
        return
    if not translation_model:
        show_error("错误", "翻译模型名称不能为空！")
        return
    if not api_base:
        show_warning("警告", "API Base URL 为空，将使用默认值。")

    if not output_path:
        base, ext = os.path.splitext(input_path)
        lang_suffix = f"_{target_language.lower().replace(' ', '')}" if target_language != "Simplified Chinese" else "_cn"
        output_path = f"{base}{lang_suffix}{ext}"
        output_entry.delete(0, tk.END)
        output_entry.insert(0, output_path)

    save_config({
        "api_base": api_base,
        "api_key": api_key,
        "translation_model": translation_model,
        "summary_model": summary_model,
        "source_language": source_language,
        "target_language": target_language
    })

    final_system_prompt = ""
    if use_deep_summary_var.get():
        if not summary_model:
            show_error("错误", "启用深度理解时，必须指定摘要模型！")
            return
        update_status("正在生成内容摘要...")
        try:
            from subtitle_parser import load_subtitles
            from translator import summarize_subtitles
            _, full_texts = load_subtitles(input_path)
            summary = summarize_subtitles(
                texts=full_texts,
                api_key=api_key,
                api_base=api_base,
                model=summary_model,
                temperature=0.3
            )
            final_system_prompt = SYSTEM_PROMPT_WITH_SUMMARY_TEMPLATE.format(
                source_language=source_language,
                target_language=target_language,
                summary=summary
            )
        except Exception as e:
            show_error("摘要失败", f"生成摘要失败：{e}")
            return
    else:
        context_prefix = f"关于{context_desc}的" if context_desc else ""
        final_system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            context=context_prefix,
            source_language=source_language,
            target_language=target_language
        )
    print(f"Using System Prompt:\n{final_system_prompt}")

    thread = threading.Thread(target=translation_worker, args=(
        input_path, output_path, window_size, temperature,
        api_base, api_key, translation_model, final_system_prompt, retry_times
    ), daemon=True)
    thread.start()

def handle_stop_translation():
    global stop_translation_flag
    if not stop_translation_flag:
        stop_translation_flag = True
        stop_button.config(state="disabled")
        update_status("终止请求已发送，等待当前批次完成...")
        update_eta("处理终止请求中...")

def handle_browse_input():
    global total_subtitle_lines
    file_path = filedialog.askopenfilename(
        title="选择输入字幕文件",
        filetypes=[("字幕文件", "*.ass *.srt"), ("所有文件", "*.*")]
    )
    if file_path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, file_path)
        base, ext = os.path.splitext(file_path)
        if ext.lower() in [".ass", ".srt"]:
            output_path = f"{base}_cn{ext}"
            output_entry.delete(0, tk.END)
            output_entry.insert(0, output_path)
        
        try:
            update_status(f"正在加载和统计 '{os.path.basename(file_path)}'...")
            _, texts = load_subtitles(file_path)
            total_subtitle_lines = len(texts)
            update_window_suggestion()
            update_status("文件已加载，请检查翻译选项。")
        except (SubtitleHandlingError, FileNotFoundError) as e:
            show_error("文件加载错误", str(e))
            total_subtitle_lines = 0
            update_window_suggestion()
            update_status("加载字幕文件失败。")

def update_window_suggestion(*args):
    if total_subtitle_lines == 0:
        file_stats_label.config(text="请先选择一个有效的字幕文件。")
        return

    base_text = f"字幕总行数: {total_subtitle_lines}。"
    try:
        window_size = int(window_entry.get())
        if window_size > 0:
            remainder = total_subtitle_lines % window_size
            if remainder == 0:
                suggestion = "当前窗口大小可被完美整除。"
            else:
                suggestion = f"提示: 最后批次将仅包含 {remainder} 行。"
            file_stats_label.config(text=f"{base_text} {suggestion}")
        else:
            file_stats_label.config(text=f"{base_text} 窗口大小必须为正数。")
    except ValueError:
        file_stats_label.config(text=f"{base_text} 请输入有效的窗口大小。")

def handle_browse_output():
    input_path = input_entry.get()
    default_ext = ".ass" if input_path.lower().endswith(".ass") else ".srt"
    initial_dir = os.path.dirname(input_path) if input_path else "."
    file_path = filedialog.asksaveasfilename(
        title="选择输出字幕文件",
        initialdir=initial_dir,
        defaultextension=default_ext,
        filetypes=[("ASS Subtitles", "*.ass"), ("SRT Subtitles", "*.srt"), ("所有文件", "*.*")]
    )
    if file_path:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, file_path)

def show_about():
    about_window = tk.Toplevel(root)
    about_window.title("关于 EzSubTrans")
    about_window.geometry("400x250")
    about_window.resizable(False, False)
    about_window.transient(root)

    info = ("EzSubTrans v0.5\n\n"
            "功能：调用大语言模型 API 翻译 .srt / .ass 字幕文件。\n\n"
            "项目页面：")
    tk.Label(about_window, text=info, justify="left", anchor="w", padx=20, pady=10).pack(fill="x")

    def open_link(event):
        webbrowser.open("https://github.com/allshell/EzSubTrans")
    
    link_label = tk.Label(about_window, text="https://github.com/allshell/EzSubTrans", fg="blue", cursor="hand2", anchor="w")
    link_label.pack(padx=50, anchor="w")
    link_label.bind("<Button-1>", open_link)

    tk.Label(about_window, text="\n\n注意：API Key 会明文存储在 config.json 文件中。\n请勿分享此文件！", justify="left", anchor="w", padx=20).pack(fill="x")
    tk.Button(about_window, text="关闭", command=about_window.destroy).pack(pady=10)

root = tk.Tk()
root.title("EzSubTrans v0.5")
root.update_idletasks()
root.minsize(720, 750)

file_frame = tk.Frame(root)
file_frame.grid(row=0, column=0, columnspan=4, padx=5, pady=2, sticky="ew")

tk.Label(file_frame, text="输入字幕文件:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
input_entry = tk.Entry(file_frame, width=55)
input_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="we")
tk.Button(file_frame, text="浏览...", command=handle_browse_input).grid(row=0, column=3, padx=5, pady=5)

tk.Label(file_frame, text="输出字幕文件:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
output_entry = tk.Entry(file_frame, width=55)
output_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="we")
tk.Button(file_frame, text="另存为...", command=handle_browse_output).grid(row=1, column=3, padx=5, pady=5)

file_frame.columnconfigure(1, weight=1)

file_stats_label = tk.Label(root, text="请先选择一个有效的字幕文件。", justify="left")
file_stats_label.grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 5), sticky="w")

options_frame = tk.LabelFrame(root, text="翻译选项", padx=10, pady=10)
options_frame.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky="ew")

window_var = tk.StringVar(value="10")
window_var.trace_add("write", update_window_suggestion)
tk.Label(options_frame, text="窗口大小:").grid(row=0, column=0, sticky="e", padx=2)
window_entry = tk.Entry(options_frame, width=5, textvariable=window_var)
window_entry.grid(row=0, column=1, sticky="w", padx=2)
CreateToolTip(window_entry, "每次API调用处理的行数。\n越大：速度可能越快，上下文可能更好。\n越小：API出错时影响范围小，不易丢失编号。")

tk.Label(options_frame, text="温度:").grid(row=0, column=3, sticky="e", padx=2)
temp_entry = tk.Entry(options_frame, width=5)
temp_entry.insert(0, "1.3")
temp_entry.grid(row=0, column=4, sticky="w", padx=2)
CreateToolTip(temp_entry, "控制翻译的创造性/随机性。\n建议范围 0.5 - 1.5。\n越高：越有创造力，可能不那么精确。\n越低：越保守，更贴近原文。")

tk.Label(options_frame, text="最大重试:").grid(row=1, column=0, sticky="e", padx=2, pady=5)
retry_entry = tk.Entry(options_frame, width=5)
retry_entry.insert(0, "1")
retry_entry.grid(row=1, column=1, sticky="w", padx=2, pady=5)
CreateToolTip(retry_entry, "单批次翻译失败时的最大重试次数。")

tk.Label(options_frame, text="背景描述:").grid(row=1, column=3, sticky="e", padx=2, pady=5)
context_entry = tk.Entry(options_frame, width=20)
context_entry.grid(row=1, column=4, columnspan=2, sticky="w", padx=2, pady=5)
CreateToolTip(context_entry, "（可选）提供字幕主题词组 (如 '科幻电影', '烹饪教程')\n有助于提高翻译的相关性和准确性。\n留空则使用通用翻译指令。")

use_deep_summary_var = tk.BooleanVar(value=False)
deep_summary_check = tk.Checkbutton(options_frame, text="启用深度理解", variable=use_deep_summary_var)
deep_summary_check.grid(row=0, column=5, columnspan=2, sticky="w", padx=(15,0))
CreateToolTip(deep_summary_check, "在开始翻译前对全部字幕进行综合分析，以准确引导翻译。\n开启后将替代“背景描述”。\n注意：开启该功能会额外消耗 token，但可配置不同模型。")

def toggle_context_state(*args):
    state = "disabled" if use_deep_summary_var.get() else "normal"
    context_entry.config(state=state)
    summary_model_entry.config(state="normal" if use_deep_summary_var.get() else "disabled")
use_deep_summary_var.trace_add("write", toggle_context_state)

tk.Label(options_frame, text="源语言:").grid(row=2, column=0, sticky="e", padx=2, pady=5)
source_lang_entry = tk.Entry(options_frame, width=15)
source_lang_entry.grid(row=2, column=1, columnspan=2, sticky="w", padx=2, pady=5)
CreateToolTip(source_lang_entry, "输入字幕的原始语言。\n(例如: 英语, 日语, 简体中文)")

tk.Label(options_frame, text="目标语言:").grid(row=2, column=4, sticky="e", padx=2, pady=5)
target_lang_entry = tk.Entry(options_frame, width=15)
target_lang_entry.grid(row=2, column=5, columnspan=2, sticky="w", padx=2, pady=5)
CreateToolTip(target_lang_entry, "输入您希望翻译成的目标语言。\n(例如: 简体中文, 法语, 韩语)")

api_frame = tk.LabelFrame(root, text="API 配置", padx=10, pady=10)
api_frame.grid(row=4, column=0, columnspan=4, padx=5, pady=5, sticky="ew")

tk.Label(api_frame, text="API Base URL:").grid(row=0, column=0, sticky="e", padx=5, pady=2)
api_base_entry = tk.Entry(api_frame, width=50)
api_base_entry.grid(row=0, column=1, padx=5, pady=2, sticky="we")

tk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky="e", padx=5, pady=2)
api_key_entry = tk.Entry(api_frame, width=50, show="*")
api_key_entry.grid(row=1, column=1, padx=5, pady=2, sticky="we")

tk.Label(api_frame, text="翻译模型:").grid(row=2, column=0, sticky="e", padx=5, pady=2)
model_entry = tk.Entry(api_frame, width=50)
model_entry.grid(row=2, column=1, padx=5, pady=2, sticky="we")
CreateToolTip(model_entry, "用于逐行翻译的模型。")

tk.Label(api_frame, text="摘要模型:").grid(row=3, column=0, sticky="e", padx=5, pady=2)
summary_model_entry = tk.Entry(api_frame, width=50)
summary_model_entry.grid(row=3, column=1, padx=5, pady=2, sticky="we")
CreateToolTip(summary_model_entry, "（可选）仅在启用“深度理解”时使用。\n可配置更强大的模型以获得更好的上下文理解。")

test_button = tk.Button(api_frame, text="测试配置", command=handle_test_api)
test_button.grid(row=4, column=1, sticky="e", padx=5, pady=5)

api_frame.columnconfigure(1, weight=1)

button_frame = tk.Frame(root)
button_frame.grid(row=5, column=0, columnspan=4, pady=10)

start_button = tk.Button(button_frame, text="开始翻译", command=handle_start_translation, width=15)
start_button.pack(side=tk.LEFT, padx=10)

stop_button = tk.Button(button_frame, text="终止翻译", command=handle_stop_translation, width=15, state="disabled")
stop_button.pack(side=tk.LEFT, padx=10)

progress_frame = tk.Frame(root)
progress_frame.grid(row=6, column=0, columnspan=4, padx=10, pady=5, sticky="ew")

progress_bar = ttk.Progressbar(progress_frame, length=400, mode='determinate')
progress_bar.pack(fill="x", expand=True)

status_label = tk.Label(progress_frame, text="请配置并选择文件", anchor="center", justify="center")
status_label.pack(fill="x", expand=True, pady=2)

eta_label = tk.Label(progress_frame, text="", anchor="center", justify="center")
eta_label.pack(fill="x", expand=True, pady=2)

preview_frame = tk.LabelFrame(root, text="实时翻译预览", padx=10, pady=10)
preview_frame.grid(row=7, column=0, columnspan=4, padx=10, pady=5, sticky="nsew")

preview_frame.columnconfigure(0, weight=1)
preview_frame.columnconfigure(1, weight=1)
preview_frame.rowconfigure(1, weight=1)

tk.Label(preview_frame, text="原文").grid(row=0, column=0)
tk.Label(preview_frame, text="译文").grid(row=0, column=1)

original_text_frame = tk.Frame(preview_frame)
original_text_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
original_scrollbar = tk.Scrollbar(original_text_frame)
original_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
original_text_widget = tk.Text(original_text_frame, wrap=tk.WORD, state=tk.DISABLED, height=5, yscrollcommand=original_scrollbar.set)
original_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
original_scrollbar.config(command=original_text_widget.yview)

translated_text_frame = tk.Frame(preview_frame)
translated_text_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
translated_scrollbar = tk.Scrollbar(translated_text_frame)
translated_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
translated_text_widget = tk.Text(translated_text_frame, wrap=tk.WORD, state=tk.DISABLED, height=5, yscrollcommand=translated_scrollbar.set)
translated_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
translated_scrollbar.config(command=translated_text_widget.yview)

bottom_frame = tk.Frame(root)
bottom_frame.grid(row=8, column=0, columnspan=4, padx=10, pady=10, sticky="e")
tk.Button(bottom_frame, text="关于", command=show_about, width=8).pack()

config = load_config()
api_base_entry.insert(0, config.get("api_base", DEFAULT_CONFIG.get("api_base", "https://api.openai.com/v1")))
api_key_entry.insert(0, config.get("api_key", DEFAULT_CONFIG.get("api_key", "")))
model_entry.insert(0, config.get("translation_model", DEFAULT_CONFIG.get("translation_model", "gpt-4o-mini")))
summary_model_entry.insert(0, config.get("summary_model", DEFAULT_CONFIG.get("summary_model", "gpt-4o")))
source_lang_entry.insert(0, config.get("source_language", "英语"))
target_lang_entry.insert(0, config.get("target_language", "简体中文"))

toggle_context_state()
default_font = tkFont.nametofont("TkDefaultFont")
original_text_widget.config(font=default_font)
translated_text_widget.config(font=default_font)

root.columnconfigure(0, weight=1)
root.rowconfigure(7, weight=1)

root.mainloop()
