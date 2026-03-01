from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

# ✅ 只创建一个 FastAPI 实例
app = FastAPI()

# ✅ 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],  # 允许的前端来源
    allow_credentials=True,  # 是否允许发送 Cookie
    allow_methods=["*"],  # 允许的 HTTP 方法（例如 GET, POST, PUT, DELETE 等）
    allow_headers=["*"],  # 允许的请求头
)


# ✅ 先注册核心路由
@app.get("/health", tags=["Monitoring"])
async def health_check():
    return {"status": "ok"}


# ✅ 再注册其他路由（确保模块内没有创建新实例）
try:
    from routers.prohibited import router as prohibited_router

    app.include_router(prohibited_router, prefix="/api")
except ImportError:
    print("Warning: routers.prohibited could not be imported.")

try:
    from routers.hour_deal import router as hour_deal_router

    app.include_router(hour_deal_router, prefix="/api")
except ImportError:
    print("Warning: routers.hour_deal could not be imported.")

try:
    from routers.sort_pro_set import router as sort_pro_set_router

    app.include_router(sort_pro_set_router, prefix="/api")
except ImportError:
    print("Warning: routers.sort_pro_set could not be imported.")

try:
    from routers.Teacher_limit import router as Teacher_limit_router

    app.include_router(Teacher_limit_router, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.hour_deal import router as hour_deal

    app.include_router(hour_deal, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.recieve_json import router as recieve_json

    app.include_router(recieve_json, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Chart_Room_Rate import router as Chart_Room_Rate

    app.include_router(Chart_Room_Rate, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Chart_Teacher_Course import router as Chart_Teacher_Course

    app.include_router(Chart_Teacher_Course, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Chart_Course_Day import router as Chart_Course_Day

    app.include_router(Chart_Course_Day, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Chart_Teacher import router as Chart_Teacher

    app.include_router(Chart_Teacher, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Search_Teacher_Chart import router as Search_Teacher_Chart

    app.include_router(Search_Teacher_Chart, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Chart_Full_Teacher import router as Chart_Full_Teacher

    app.include_router(Chart_Full_Teacher, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Chart_Full_Room import router as Chart_Full_Room

    app.include_router(Chart_Full_Room, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Chart_Room import router as Chart_Room

    app.include_router(Chart_Room, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Show_Able import router as Show_Able

    app.include_router(Show_Able, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.Return_Data import router as Return_Data

    app.include_router(Return_Data, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.login import router as login

    app.include_router(login, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

try:
    from routers.save_priority import router as save_priority

    app.include_router(save_priority, prefix="/api")
except ImportError:
    print("Warning: routers.Teacher_limit could not be imported.")

# ✅ 最后添加中间件
@app.middleware("http")
async def force_json_response(request: Request, call_next):
    try:
        # 调用下一个中间件或路由处理程序
        response = await call_next(request)

        # 如果响应没有设置 Content-Type，则强制设置为 application/json
        if "Content-Type" not in response.headers:
            response.headers["Content-Type"] = "application/json"

        return response
    except Exception as e:
        # 返回 JSON 格式的错误响应
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "Internal Server Error",
                "error": str(e)  # 可选：生产环境中可以移除或隐藏详细错误信息
            }
        )


# ✅ 打印路由调试信息
@app.on_event("startup")
async def print_routes():
    print("\n🔍 已注册路由列表：")
    for route in app.routes:
        print(f"Path: {route.path}, Methods: {route.methods}")

