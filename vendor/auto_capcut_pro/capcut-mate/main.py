from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from src.router import v1_router
from src.utils.draft_downloader import download_draft
from src.utils.logger import logger
from src.middlewares import PrepareMiddleware, ResponseMiddleware, LicenseMiddleware
import config
import os


# 1. 创建 FastAPI 应用
app: FastAPI = FastAPI(title="CapCut Mate API", version="1.0")

# /health — no auth required; used by Go subprocess manager for readiness probe
@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "version": "1.0"})

# 2. 注册路由
app.include_router(router=v1_router, prefix="/openapi/capcut-mate", tags=["capcut-mate"])

# 2.5 挂载静态文件目录（草稿资源文件下载）
_output_dir = os.path.join(config.DATA_DIR, "output")
os.makedirs(_output_dir, exist_ok=True)
app.mount("/output", StaticFiles(directory=_output_dir), name="output")

# 3. 添加中间件
app.add_middleware(middleware_class=PrepareMiddleware)
# License verification — only active when ENABLE_APIKEY=true (default)
if config.ENABLE_APIKEY.lower() in ("true", "1", "yes"):
    app.add_middleware(middleware_class=LicenseMiddleware)
# 注册统一响应处理中间件（注意顺序，应该在其他中间件之后注册）
app.add_middleware(middleware_class=ResponseMiddleware)

# 4. 打印所有路由
for r in app.routes:
    # 1. 取 HTTP 方法列表
    methods = getattr(r, "methods", None) or [getattr(r, "method", "WS")]
    # 2. 安全地取路径
    path = getattr(r, "path", "<unknown>")
    # 3. 安全地取函数名
    name = getattr(r, "name", "<unnamed>")
    logger.info("Route: %s %s -> %s", ",".join(sorted(methods)), path, name)

logger.info("CapCut Mate API")

# 5. 启动
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.LOCAL_PORT, log_config=None, log_level="info")