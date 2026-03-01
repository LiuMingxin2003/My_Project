from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from DataBase.recieve_course import query_db

router = APIRouter()


class Courselist(BaseModel):
    keyword : str

# FastAPI 示例接口
@router.post("/course-search")
async def search_courses(data: Courselist):
    result = query_db(data.keyword)
    # 返回示例数据
    return [
        {
            "id": result.get("课程编号"),  # 使用 .get() 方法避免 KeyError
            "code": result.get("课程类别"),
            "name": result.get("课程名称"),
            "credit": result.get("学分")
        }
    ]


@router.post("/save-priority")
async def save_priority(config: dict):
    # 保存逻辑
    return {"status": "success"}