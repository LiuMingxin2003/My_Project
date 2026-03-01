from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from DataBase.Database_Search_Teacher_Chart import Search_Teacher_Chart
from DataBase.recieve_course import query_db

router = APIRouter()

# FastAPI 示例接口
class Courselist(BaseModel):
    teacher_id : str

# FastAPI 示例接口
@router.post("/Search_Teacher_Chart")
async def Search_Teacher_Chart(data: Courselist):
    teacher_id = data.teacher_id  # 通过实例访问属性
    result = Search_Teacher_Chart(teacher_id)  # 传递正确的参数
    if result is None:
        raise HTTPException(status_code=500, detail="数据获取失败")
    return {"status": "success", "data": result}


@router.post("/save-priority")
async def save_priority(config: dict):
    # 保存逻辑
    return {"status": "success"}