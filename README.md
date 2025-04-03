# EzSubTrans v0.3

一个 Windows 端图形界面字幕翻译工具，依靠调用大语言模型 API，自动翻译 `.srt` 或 `.ass` 格式的英文字幕文件，并保存为同格式的简体中文字幕文件。

---

## 功能特色

- 支持 `.srt` 和 `.ass` 字幕格式
- 自动识别类型并保存为相应格式
- 基于滑动窗口分批翻译，大幅改善单行字幕的翻译质量，并支持自定义窗口大小
- 根据内容简述定制系统指令
- 自动保存模型 API 配置，无需重复输入
- 提供 ETA 预估剩余时间
- 支持某一窗口翻译失败自动重试
- 可随时终止翻译并保存已完成部分

---

## 使用方法

1. 普通用户
    - [下载](https://github.com/allshell/EzSubTrans/releases/download/v0.3/EzSubTrans_v0.3.exe)并直接运行 EzSubTrans_v0.3.exe（无需额外依赖或安装）
    - 通过`浏览`选择字幕文件或直接输入路径（支持 `.srt`/`.ass`）
    - 设置输出路径（默认根据`浏览`选中的文件自动生成）
    - 根据具体的 API 提供方信息，输入 API Base、API Key 和模型名称
    - （可选）设置窗口大小、温度、最大重试次数、背景描述词
    - 点击“开始翻译”启动
    - 如需终止可点击“终止翻译”

2. 开发者
    - 安装依赖：`pip install openai pysubs2`
    - 执行：`python EzSubTrans_gui_dev.py`

> ⚠️ 注意：API Key 将保存在本地同目录下的 `config.json` 文件中，请妥善保管，**切勿泄露或随意与他人共享该文件**。

---

## 窗口大小、温度、背景描述、最大重试次数

- **窗口大小**：控制每次提取并提交给模型翻译的字幕行数
>   - 该值越大，整体翻译越快，且单行翻译与上下文语境的结合越好，但过大可能导致结果与原文频繁错行；
>   - 若不确定如何设置，推荐使用`10`进行初步测试。

- **温度**：控制模型的温度参数
>   - 该值越大，模型越能够灵活发挥，反之，低温能让模型更好地遵循指令；
>   - 若不确定如何设置，推荐使用`1.3`进行初步测试。

- **背景描述**：用于生成特定系统指令，进一步提高翻译质量
>   - 使用一个词组描述字幕文件的大致内容，如`太空科幻`、`美食节目`等；
>   - 若不确定也可留空，程序将使用默认系统指令。

- **最大重试次数**：限制某个窗口翻译异常时，最多重试几次
>   - 达到最大重试次数后若仍然失败，程序将在输出文件中的相应位置进行标注，并继续翻译。

---

## 输出文件说明

- 默认输出文件名在原文件名后添加 `_cn`，格式与原文件一致
- 若翻译中被用户提前终止，将把已完成的部分保存为 `_partial.ass` 或 `_partial.srt`

---

## 已知问题

- 窗口大小设置过大可能导致翻译行数不一致或输出错乱
- 部分模型可能不严格遵守编号格式，建议设置合理的最大重试次数以提高成功率

---

## 版本信息

- 当前版本：`v0.3`
- 支持模型：任意能够使用 Python `openai` 库 API 的模型（目前几乎所有提供 API 服务的大语言模型均可，如 `gpt-4o-mini`、`deepseek-chat` 等）
