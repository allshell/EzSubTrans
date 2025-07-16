# config_manager.py
import json
import os

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"加载配置文件错误: {e}")
            return {}
    return {}

def save_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"保存配置文件错误: {e}")

DEFAULT_CONFIG = {
    "api_base": "https://api.openai.com/v1",
    "api_key": "",
    "translation_model": "gpt-4o-mini",
    "summary_model": "gpt-4o"
}

def get_config_value(key, default=None):
    config = load_config()
    return config.get(key, default)
