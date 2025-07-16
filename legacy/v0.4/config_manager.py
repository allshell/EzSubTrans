# config_manager.py
import json
import os

CONFIG_FILE = "config.json"

# 如果 CONFIG_FILE 存在，从其中加载配置数据
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"加载配置文件错误: {e}")
            return {}
    return {}

# 将配置数据保存到 CONFIG_FILE 中
def save_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"保存配置文件错误: {e}")

# 默认配置文件示例（可选，供参考）
DEFAULT_CONFIG = {
    "api_base": "https://api.openai.com/v1",
    "api_key": "",
    "model_name": "gpt-4o-mini"
}

# 从加载的配置中获取特定值，并提供默认值
def get_config_value(key, default=None):
    config = load_config()
    return config.get(key, default)
