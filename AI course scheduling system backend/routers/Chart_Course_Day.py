from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from DataBase.Database_Teacher_course import Teacher_Utilization
from DataBase.Database_Course_Day import Database_Course_Day

router = APIRouter()

# FastAPI 示例接口
@router.get("/Chart_Course_Day")
async def search_courses():
    result = Database_Course_Day()
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