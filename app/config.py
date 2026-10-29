"""集中配置：所有「会变的数字」都放这里，业务代码里不出现魔法值。

优先级：.env / 环境变量 > 本文件的默认值。
其他模块一律 `from app import config`，不要自己读 os.getenv。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # 幂等：重复导入无副作用，保证任何入口都能读到 .env

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
EVAL_DIR = ROOT / "eval"

# --- LLM 相关 ---
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
REQUEST_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))  # 秒；不设会挂死
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1500"))

# --- 业务约束 ---
RECS_COUNT = 5  # 一次生成几条推荐（M0 的验收标准就是 5）
