from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from DataBase.Database_Chart_Room import Classroom_Course_Distribution
from DataBase.recieve_course import query_db

router = APIRouter()
class Courselist(BaseModel):
    classroom : str

# FastAPI
@router.post("/Chart_Room")
async def search_courses(data: Courselist):
    result = Classroom_Course_Distribution(data.classroom)  # 传递正确的参数
    if result is None:
        raise HTTPException(status_code=500, detail="数据获取失败")
    return {"status": "success", "data": result}


@router.post("/save-priority")
async def save_priority(config: dict):
    # 保存逻辑
    return {"status": "success"}