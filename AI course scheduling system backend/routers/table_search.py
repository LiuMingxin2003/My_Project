# FastAPI 示例
from fastapi import FastAPI
from pydantic import BaseModel

from DataBase.Database_teacher_search import query_employee_from_db
from routers.hour_deal import router

app = FastAPI()

class TeacherRequest(BaseModel):
    name: str
    id: str

class TeacherLimits(BaseModel):
    teacherId: str
    limits: dict

@router.post("/table_search")
async def get_teacher(data: TeacherRequest):
    result = query_employee_from_db(TeacherRequest.name,TeacherRequest.id)
    # 数据库查询逻辑
    return {
        "id": result.工号,
        "name": result.姓名,
        "dailyMax": 6,
        "weeklyMax": 30,
        "amMax": 3,
        "pmMax": 3
    }

@router.put("/teacher-limits")
async def save_limits(data: TeacherLimits):
    # 保存逻辑
    return {"status": "success"}