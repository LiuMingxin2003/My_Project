from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from DataBase.Database_Show_Able import Show_Able
from DataBase.recieve_course import query_db

router = APIRouter()
class Courselist(BaseModel):
    classroom : str

# FastAPI
@router.post("/Show_Able")
async def search_courses(data: Courselist):
    classroom = data.classroom  # 通过实例访问属性
    result = Show_Able(classroom)  # 传递正确的参数
    if result is None:
        raise HTTPException(status_code=500, detail="数据获取失败")
    return {"status": "success", "data": result}


@router.post("/save-priority")
async def save_priority(config: dict):
    # 保存逻辑
    return {"status": "success"}
