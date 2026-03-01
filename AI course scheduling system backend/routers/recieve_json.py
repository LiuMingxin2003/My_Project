from fastapi import APIRouter, HTTPException, Body
from database import get_connection
from models.schemas import ForbidSearchRequest, ScheduleRequest
from pydantic import BaseModel
import logging
router = APIRouter()
logger = logging.getLogger("uvicorn.error")
@router.post("/schedule")
async def create_schedule(request: ScheduleRequest):  # ✅ 正确声明
    # 直接使用 request 对象，无需二次解析
    logger.info(f"接收数据: {request.dict()}")

    # 你的业务逻辑
    return {"success": True, "taskId": "123"}
