from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from DataBase.Data_Room_Rate import Chart_Room_Rate
from DataBase.recieve_course import query_db

router = APIRouter()

# FastAPI 示例接口
@router.get("/Chart_Room_Rate")
async def search_courses():
    result = Chart_Room_Rate()
    if result is None:
        raise HTTPException(status_code=500, detail="数据获取失败")

    return {
        "status": "success",
        "data": result
    }


@router.post("/save-priority")
async def save_priority(config: dict):
    # 保存逻辑
    return {"status": "success"}