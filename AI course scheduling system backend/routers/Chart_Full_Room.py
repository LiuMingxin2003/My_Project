from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from DataBase.Database_Chart_Full_Room import get_all_classroom_schedules
from DataBase.recieve_course import query_db

router = APIRouter()

# FastAPI 示例接口
@router.get("/Chart_Full_Room")
async def search_courses():
    result = get_all_classroom_schedules()  # 传递正确的参数
    if result is None:
        raise HTTPException(status_code=500, detail="数据获取失败")
    return {"status": "success", "data": result}


@router.post("/save-priority")
async def save_priority(config: dict):
    # 保存逻辑
    return {"status": "success"}