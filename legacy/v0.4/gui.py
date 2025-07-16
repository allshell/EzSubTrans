# gui.py
import tkinter as tk
import sys
if sys.platform == "win32":# 尝试兼容高 DPI 模式
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

# 从其它模块导入函数
from config_manager import load_config, save_config, DEFAULT_CONFIG
from subtitle_parser import load_subtitles, save_subtitles, SubtitleHandlingError
from translator import translate_batch, TranslationError, SYSTEM_PROMPT_TEMPLATE

# 停止翻译的全局标志
stop_translation_flag = False

class CreateToolTip:# 提示类
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

# --- GUI 更新函数 ---
# 用于确保从工作线程安全地更新 GUI

def update_status(text):# 更新状态标签
    if status_label: # 检查标签是否存在
        status_label.config(text=text)
        root.update_idletasks() # 保证实时更新显示内容

def update_eta(text):# 更新 ETA 标签
    if eta_label:
        eta_label.config(text=text)
        root.update_idletasks()

def update_progress(value, maximum):# 更新进度条
    if progress_bar:
        progress_bar["maximum"] = maximum
        progress_bar["value"] = value
        root.update_idletasks()

def show_info(title, message):# 信息框
    messagebox.showinfo(title, message)

def show_warning(title, message):# 警告框
    messagebox.showwarning(title, message)

def show_error(title, message):# 错误框
    messagebox.showerror(title, message)

# --- 核心翻译流程（独立线程）---

def translation_worker(input_path, output_path, window_size, temperature, api_base, api_key, model_name, system_prompt, retry_times):# 执行翻译
    global stop_translation_flag
    start_button.config(state="disabled")
    stop_button.config(state="normal")
    update_eta("") # 清除初始 ETA

    try:
        # 使用 parser 模块加载字幕
        update_status("加载字幕文件中...")
        subs, texts = load_subtitles(input_path)
        original_num_lines = len(texts)
        update_status(f"加载完成，共 {original_num_lines} 行")

        translated_texts = []
        durations = []
        update_progress(0, original_num_lines)
        update_eta(f"总行数：{original_num_lines}\n等待至少2个窗口以计算剩余时间...")

        # 分批处理
        for i in range(0, original_num_lines, window_size):
            if stop_translation_flag:
                update_status("用户请求中断...")
                break

            batch_texts = texts[i : i + window_size]
            current_batch_info = f"行 {i + 1} - {min(i + len(batch_texts), original_num_lines)}"
            update_status(f"开始翻译 {current_batch_info}...")

            batch_start_time = time.time()

            # 使用 translator 模块批量翻译
            batch_translated, warning_msg = translate_batch(
                texts=batch_texts,
                api_key=api_key,
                api_base=api_base,
                model=model_name,
                system_prompt=system_prompt,
                temperature=temperature,
                max_retries=retry_times
            )

            batch_end_time = time.time()
            durations.append(batch_end_time - batch_start_time)

            if warning_msg:
                 update_status(f"{current_batch_info}: {warning_msg}")
                 print(f"翻译 {current_batch_info} 时出现警告/错误: {warning_msg}")
            else:
                 update_status(f"完成翻译 {current_batch_info}")

            translated_texts.extend(batch_translated)
            update_progress(len(translated_texts), original_num_lines)

            # 计算并更新 ETA
            if len(durations) >= 2:
                avg_time_per_batch = sum(durations) / len(durations)
                remaining_batches = (original_num_lines - len(translated_texts) + window_size - 1) // window_size
                eta_seconds = int(avg_time_per_batch * remaining_batches)
                eta_str = str(datetime.timedelta(seconds=eta_seconds))
                update_eta(f"总行数：{original_num_lines}\n预计剩余时间：{eta_str}")
            else:
                 update_eta(f"总行数：{original_num_lines}\n正在计算剩余时间...")

        # 使用 parser 模块保存结果
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
            # 完整保存
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
    except TranslationError as e: # 捕捉已定义的特定翻译错误
         update_status(f"翻译错误: {e}")
         show_error("翻译错误", str(e))
    except Exception as e: # 捕捉其它意外错误
        update_status(f"发生意外错误: {e}")
        show_error("意外错误", f"发生未预料的错误:\n{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc() # 调试功能：向控制台打印堆栈跟踪信息
    finally:
        # 确保按钮无论成功或失败都能重置
        stop_translation_flag = False # 重置标记
        start_button.config(state="normal")
        stop_button.config(state="disabled")
        update_progress(0, 1) # 重置进度条

# --- GUI 事件处理 ---

def handle_test_api():# 回调“测试配置”按钮
    api_base = api_base_entry.get().strip()
    api_key = api_key_entry.get().strip()
    model_name = model_entry.get().strip()

    if not api_key or not model_name:
        show_error("配置错误", "API Key 和模型名称不能为空。")
        return

    # 临时将按钮改为“正在测试”
    test_button.config(text="正在测试...", state="disabled")
    root.update_idletasks()  # 强制刷新 GUI

    def test_thread():
        try:
            import openai
            client = openai.OpenAI(base_url=api_base, api_key=api_key)

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "你是一个测试助手，这是一次简单测试。"},
                    {"role": "user", "content": "请回复\"你好，世界！\"，不要添加任何多余内容。"}
                ],
                temperature=0.1
            )
            reply = response.choices[0].message.content.strip()
            show_info("配置成功", f"成功连接！模型返回：\n“{reply}”")
        except openai.AuthenticationError:
            show_error("认证失败", "API Key 无效，请检查是否输入正确。")
        except openai.NotFoundError:
            show_error("模型错误", "指定的模型名称无效或不存在。")
        except openai.OpenAIError as e:
            show_error("OpenAI 错误", f"请求失败：\n{type(e).__name__}: {e}")
        except Exception as e:
            show_error("连接失败", f"无法连接 API：\n{type(e).__name__}: {e}")
        finally:
            test_button.config(text="测试配置", state="normal")

    threading.Thread(target=test_thread, daemon=True).start()

def handle_start_translation():# 回调“开始翻译”按钮
    global stop_translation_flag
    stop_translation_flag = False # 确保在启动前重置标记

    # 从 GUI 获取参数
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

    # 获取翻译语言对
    source_language = source_lang_entry.get().strip()
    target_language = target_lang_entry.get().strip()

    api_base = api_base_entry.get()
    api_key = api_key_entry.get()
    model_name = model_entry.get()
    context_desc = context_entry.get().strip()

    # 基础校验
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
    if not model_name:
        show_error("错误", "模型名称不能为空！")
        return
    if not api_base:
        show_warning("警告", "API Base URL 为空，将使用默认值。")

    # 如果为空，则自动生成输出路径
    if not output_path:
        base, ext = os.path.splitext(input_path)
        # 输出文件名包含目标语言
        lang_suffix = f"_{target_language.lower().replace(' ', '')}" if target_language != "Simplified Chinese" else "_cn" # 避免文件名太长
        output_path = f"{base}{lang_suffix}{ext}"
        output_entry.delete(0, tk.END)
        output_entry.insert(0, output_path)

    # 保存相关配置信息
    save_config({
        "api_base": api_base,
        "api_key": api_key,
        "model_name": model_name,
        "source_language": source_language,
        "target_language": target_language
    })

    # 构建系统提示
    # 使用模板和所选语言创建系统提示
    context_prefix = f"关于{context_desc}的" if context_desc else "" # 保持上下文措辞不变，或根据需要进行调整

    # 确保从 translator 模块导入更新后的模板
    from translator import SYSTEM_PROMPT_TEMPLATE, SYSTEM_PROMPT_WITH_SUMMARY_TEMPLATE

    # 确保深度理解生成摘要的高优先级
    if use_deep_summary_var.get():
        update_status("正在生成内容摘要...")
        try:
            from subtitle_parser import load_subtitles
            from translator import summarize_subtitles
            _, full_texts = load_subtitles(input_path)
            summary = summarize_subtitles(
                texts=full_texts,
                api_key=api_key,
                api_base=api_base,
                model=model_name,
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
    print(f"Using System Prompt:\n{final_system_prompt}") # 调试功能：向控制台打印生成的指令

    # 启动工作进程，传递更新后的指令
    thread = threading.Thread(target=translation_worker, args=(
        input_path, output_path, window_size, temperature,
        api_base, api_key, model_name, final_system_prompt, retry_times # 确保 final_system_prompt 被传递
    ), daemon=True)
    thread.start()

def handle_stop_translation():# 回调“终止翻译”按钮
    global stop_translation_flag
    if not stop_translation_flag: # 防止多次点击
        stop_translation_flag = True
        stop_button.config(state="disabled") # 立即禁用按钮
        update_status("终止请求已发送，等待当前批次完成...")
        update_eta("处理终止请求中...")

def handle_browse_input():# 回调“浏览”按钮
    file_path = filedialog.askopenfilename(
        title="选择输入字幕文件",
        filetypes=[("字幕文件", "*.ass *.srt"), ("所有文件", "*.*")]
    )
    if file_path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, file_path)
        # 自动填写输出路径
        base, ext = os.path.splitext(file_path)
        if ext.lower() in [".ass", ".srt"]:
            output_path = f"{base}_cn{ext}"
            output_entry.delete(0, tk.END)
            output_entry.insert(0, output_path)

def handle_browse_output():# 回调“保存为”按钮
    input_path = input_entry.get()
    # Suggest extension based on input
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

def show_about():# 显示“关于”窗口
    about_window = tk.Toplevel(root)
    about_window.title("关于 EzSubTrans")
    about_window.geometry("400x250")
    about_window.resizable(False, False)
    about_window.transient(root) # 确保其处于主窗口之上

    info = (
        "EzSubTrans v0.4\n\n"
        "功能：调用大语言模型 API 翻译 .srt / .ass 字幕文件。\n\n"
        "项目页面："
    )
    tk.Label(about_window, text=info, justify="left", anchor="w", padx=20, pady=10).pack(fill="x")

    def open_link(event):
        webbrowser.open("https://github.com/allshell/EzSubTrans")
    
    link_label = tk.Label(about_window, text="https://github.com/allshell/EzSubTrans", fg="blue", cursor="hand2", anchor="w")
    link_label.pack(padx=50, anchor="w")
    link_label.bind("<Button-1>", open_link)

    tk.Label(about_window, text="\n\n注意：API Key 会明文存储在 config.json 文件中。\n请勿分享此文件！", justify="left", anchor="w", padx=20).pack(fill="x")
    tk.Button(about_window, text="关闭", command=about_window.destroy).pack(pady=10)

# --- GUI 布局 ---

root = tk.Tk()
root.title("EzSubTrans v0.4")
root.update_idletasks()
root.minsize(720, 560)

# 输入文件行
tk.Label(root, text="输入字幕文件:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
input_entry = tk.Entry(root, width=55)
input_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="we")
tk.Button(root, text="浏览...", command=handle_browse_input).grid(row=0, column=3, padx=5, pady=5)

# 输出文件行
tk.Label(root, text="输出字幕文件:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
output_entry = tk.Entry(root, width=55)
output_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="we")
tk.Button(root, text="另存为...", command=handle_browse_output).grid(row=1, column=3, padx=5, pady=5)

# 选项框
options_frame = tk.LabelFrame(root, text="翻译选项", padx=10, pady=10)
options_frame.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky="ew")

# --- 框内选项 ---
tk.Label(options_frame, text="窗口大小:").grid(row=0, column=0, sticky="e", padx=2)
window_entry = tk.Entry(options_frame, width=5)
window_entry.insert(0, "10")
window_entry.grid(row=0, column=1, sticky="w", padx=2)
window_q = tk.Label(options_frame, text="?", fg="blue", cursor="question_arrow")
window_q.grid(row=0, column=2, sticky="w", padx=(0,10))
CreateToolTip(window_q, "每次API调用处理的行数。\n越大：速度可能越快，上下文可能更好。\n越小：API出错时影响范围小，不易丢失编号。")

tk.Label(options_frame, text="温度:").grid(row=0, column=3, sticky="e", padx=2)
temp_entry = tk.Entry(options_frame, width=5)
temp_entry.insert(0, "1.3")
temp_entry.grid(row=0, column=4, sticky="w", padx=2)
temp_q = tk.Label(options_frame, text="?", fg="blue", cursor="question_arrow")
temp_q.grid(row=0, column=5, sticky="w", padx=(0,10))
CreateToolTip(temp_q, "控制翻译的创造性/随机性。\n建议范围 0.5 - 1.5。\n越高：越有创造力，可能不那么精确。\n越低：越保守，更贴近原文。")

tk.Label(options_frame, text="最大重试:").grid(row=1, column=0, sticky="e", padx=2, pady=5)
retry_entry = tk.Entry(options_frame, width=5)
retry_entry.insert(0, "1")
retry_entry.grid(row=1, column=1, sticky="w", padx=2, pady=5)
retry_q = tk.Label(options_frame, text="?", fg="blue", cursor="question_arrow")
retry_q.grid(row=1, column=2, sticky="w", padx=(0,10), pady=5)
CreateToolTip(retry_q, "单批次翻译失败时的最大重试次数。")

tk.Label(options_frame, text="背景描述:").grid(row=1, column=3, sticky="e", padx=2, pady=5)
context_entry = tk.Entry(options_frame, width=20)
context_entry.grid(row=1, column=4, columnspan=2, sticky="w", padx=2, pady=5)
context_q = tk.Label(options_frame, text="?", fg="blue", cursor="question_arrow")
context_q.grid(row=1, column=6, sticky="w", padx=(0,5), pady=5)
CreateToolTip(context_q, "（可选）提供字幕主题词组 (如 '科幻电影', '烹饪教程')\n有助于提高翻译的相关性和准确性。\n留空则使用通用翻译指令。")

use_deep_summary_var = tk.BooleanVar(value=False)

deep_summary_check = tk.Checkbutton(options_frame, text="启用深度理解", variable=use_deep_summary_var)
deep_summary_check.grid(row=0, column=5, columnspan=1, sticky="w", pady=5)

deep_summary_q = tk.Label(options_frame, text="?", fg="blue", cursor="question_arrow")
deep_summary_q.grid(row=0, column=6, sticky="w", padx=(0,10))
CreateToolTip(deep_summary_q, "在开始翻译前对全部字幕进行综合分析，以准确引导翻译。\n开启后将替代“背景描述”。\n注意：开启该功能后会额外消耗约一至二倍的 token。")
def toggle_context_state(*args):# 在启用深度理解时禁用背景描述
    if use_deep_summary_var.get():
        context_entry.config(state="disabled")
    else:
        context_entry.config(state="normal")
use_deep_summary_var.trace_add("write", toggle_context_state)

tk.Label(options_frame, text="源语言:").grid(row=2, column=0, sticky="e", padx=2, pady=5)
source_lang_entry = tk.Entry(options_frame, width=15)
source_lang_entry.insert(0, "")
source_lang_entry.grid(row=2, column=1, columnspan=2, sticky="w", padx=2, pady=5)
source_lang_q = tk.Label(options_frame, text="?", fg="blue", cursor="question_arrow")
source_lang_q.grid(row=2, column=3, sticky="w", padx=(0,10), pady=5)
CreateToolTip(source_lang_q, "输入字幕的原始语言。\n(例如: 英语, 日语, 简体中文)")

tk.Label(options_frame, text="目标语言:").grid(row=2, column=4, sticky="e", padx=2, pady=5)
target_lang_entry = tk.Entry(options_frame, width=15)
target_lang_entry.insert(0, "")
target_lang_entry.grid(row=2, column=5, columnspan=2, sticky="w", padx=2, pady=5)
target_lang_q = tk.Label(options_frame, text="?", fg="blue", cursor="question_arrow")
target_lang_q.grid(row=2, column=7, sticky="w", padx=(0,5), pady=5) # 调整列防止重叠
CreateToolTip(target_lang_q, "输入您希望翻译成的目标语言。\n(例如: 简体中文, 法语, 韩语)")

# --- API 配置框 ---
api_frame = tk.LabelFrame(root, text="API 配置", padx=10, pady=10)
api_frame.grid(row=4, column=0, columnspan=4, padx=5, pady=5, sticky="ew")

tk.Label(api_frame, text="API Base URL:").grid(row=0, column=0, sticky="e", padx=5, pady=2)
api_base_entry = tk.Entry(api_frame, width=50)
api_base_entry.grid(row=0, column=1, padx=5, pady=2, sticky="we")

tk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky="e", padx=5, pady=2)
api_key_entry = tk.Entry(api_frame, width=50, show="*")
api_key_entry.grid(row=1, column=1, padx=5, pady=2, sticky="we")

tk.Label(api_frame, text="模型名称:").grid(row=2, column=0, sticky="e", padx=5, pady=2)
model_entry = tk.Entry(api_frame, width=50)
model_entry.grid(row=2, column=1, padx=5, pady=2, sticky="we")

test_button = tk.Button(api_frame, text="测试配置", command=handle_test_api)
test_button.grid(row=3, column=1, sticky="e", padx=5, pady=5)

# 缩放 API 配置框
api_frame.columnconfigure(1, weight=1)

# --- 控制按钮 ---
button_frame = tk.Frame(root)
button_frame.grid(row=5, column=0, columnspan=4, pady=10)

start_button = tk.Button(button_frame, text="开始翻译", command=handle_start_translation, width=15)
start_button.pack(side=tk.LEFT, padx=10)

stop_button = tk.Button(button_frame, text="终止翻译", command=handle_stop_translation, width=15, state="disabled")
stop_button.pack(side=tk.LEFT, padx=10)

# --- 进度条与状态显示 ---
progress_bar = ttk.Progressbar(root, length=400, mode='determinate')
progress_bar.grid(row=6, column=0, columnspan=4, padx=10, pady=5, sticky="ew")

status_label = tk.Label(root, text="请配置并选择文件", anchor="center", justify="center")
status_label.grid(row=7, column=0, columnspan=4, padx=10, pady=2, sticky="ew")

eta_label = tk.Label(root, text="", anchor="center", justify="center")
eta_label.grid(row=8, column=0, columnspan=4, padx=10, pady=2, sticky="ew")

# --- 关于按钮 ---
tk.Button(root, text="关于", command=show_about, width=8).grid(row=8, column=3, sticky="e", padx=10, pady=5)

# --- 加载初始配置 ---
config = load_config()
api_base_entry.insert(0, config.get("api_base", DEFAULT_CONFIG.get("api_base", "https://api.openai.com/v1")))
api_key_entry.insert(0, config.get("api_key", DEFAULT_CONFIG.get("api_key", "")))
model_entry.insert(0, config.get("model_name", DEFAULT_CONFIG.get("model_name", "gpt-4o-mini")))
source_lang_entry.insert(0, config.get("source_language", "英语"))
target_lang_entry.insert(0, config.get("target_language", "简体中文"))

for i in range(4):
    root.columnconfigure(i, weight=1)

# --- 启动 GUI 主循环 ---
root.mainloop()
