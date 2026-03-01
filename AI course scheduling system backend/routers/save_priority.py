from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from DataBase.Database_Show_Able import Show_Able
from DataBase.recieve_course import query_db
from typing import List
from pydantic import BaseModel, Field
router = APIRouter()
class PriorityItem(BaseModel):
    course_id: str = Field(..., alias="courseId")  # 通过别名处理驼峰式字段
    priority: int

    class Config:
        allow_population_by_field_name = True  # 允许通过别名创建实例
class TeacherLimits(BaseModel):
    priorities: List[PriorityItem]  # 明确指定为列表类型

@router.post("/save_priority")
async def save_limits(data: TeacherLimits):
    # 保存逻辑
    return {"status": "success"}