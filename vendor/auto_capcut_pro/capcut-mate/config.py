# 项目常量定义
import os
from dotenv import load_dotenv


# 加载.env文件
load_dotenv()

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Writable data root. The desktop app launches capcut-mate from
# C:\Program Files\... which is read-only for a standard user, so
# output/temp directories MUST live under %APPDATA% instead of
# next to the exe. Go side sets CAPMATE_DATA_DIR; falls back to
# PROJECT_ROOT only when running from a dev checkout.
DATA_DIR = os.getenv("CAPMATE_DATA_DIR") or PROJECT_ROOT

# 保存剪映草稿的目录
DRAFT_DIR = os.path.join(DATA_DIR, "output", "draft")

# 临时文件目录
TEMP_DIR = os.path.join(DATA_DIR, "temp")

# Make sure both exist at import time so downstream code doesn't
# need to worry about FileNotFoundError on first run.
os.makedirs(DRAFT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 剪映草稿的下载路径
DRAFT_URL = os.getenv("DRAFT_URL", "https://capcut-mate.jcaigc.cn/openapi/capcut-mate/v1/get_draft")

# 将容器内的文件路径转成一个下载路径，执行替换操作，即将/app/ -> https://capcut-mate.jcaigc.cn/
DOWNLOAD_URL = os.getenv("DOWNLOAD_URL", "https://capcut-mate.jcaigc.cn/")

# 草稿提示URL
TIP_URL = os.getenv("TIP_URL", "https://docs.jcaigc.cn/")

# 贴纸配置文件路径
STICKER_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "sticker.json")

# 模板目录路径
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "template")

# 剪映草稿保存路径（下载剪映草稿保存位置）-- 云渲染必需配置
DRAFT_SAVE_PATH = os.getenv("DRAFT_SAVE_PATH", "C:/Users/CHINH_SERVER/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft")

# 腾讯云对象存储配置 -- 云渲染必需配置
COS_SECRET_ID = os.getenv("COS_SECRET_ID", "")
COS_SECRET_KEY = os.getenv("COS_SECRET_KEY", "")
COS_BUCKET_NAME = os.getenv("COS_BUCKET_NAME", "")
COS_REGION = os.getenv("COS_REGION", "")

# APIKEY启用配置-默认启用 -- 云渲染必需配置
ENABLE_APIKEY = os.getenv("ENABLE_APIKEY", "true")

# 文件下载大小限制（字节），默认200MB
DOWNLOAD_FILE_SIZE_LIMIT = int(os.getenv("DOWNLOAD_FILE_SIZE_LIMIT", str(200 * 1024 * 1024)))

# --- Auto Capcut Pro local mode ---
# Port capcut-mate listens on when launched as subprocess by the desktop app
LOCAL_PORT = int(os.getenv("LOCAL_PORT", "9100"))

# License verification endpoint (remote)
LICENSE_VERIFY_URL = os.getenv("LICENSE_VERIFY_URL", "https://be.4mmo.top/api/v1/license/verify")

# License cache TTL in seconds (5 minutes)
LICENSE_CACHE_TTL = int(os.getenv("LICENSE_CACHE_TTL", "300"))
