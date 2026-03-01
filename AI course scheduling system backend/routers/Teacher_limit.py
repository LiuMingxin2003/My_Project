# FastAPI 示例
from http.client import HTTPException

from fastapi import FastAPI
from pydantic import BaseModel

from DataBase.Database_teacher_search import query_employee_from_db
from routers.hour_deal import router
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from routers.recieve_json import logger

app = FastAPI()

class TeacherRequest(BaseModel):
    name: str
    employee_id: str

class TeacherLimits(BaseModel):
    limits: dict

@router.post("/teacher")
async def get_teacher(request_data: TeacherRequest):
    try:
        # 基础校验
        if not request_data.name and not request_data.employee_id:
            raise HTTPException(400, detail="必须提供姓名或工号")

        # 执行查询
        result = query_employee_from_db(request_data.name, request_data.employee_id)

        if not result:
            raise HTTPException(404, detail="未找到教师信息")

        return result

    except ValueError as ve:
        raise HTTPException(400, detail=str(ve))
    except Exception as e:
        logger.exception("数据库查询失败")
        raise HTTPException(500, detail="服务器内部错误")

@router.put("/teacher-limits")
async def save_limits(data: TeacherLimits):
    # 保存逻辑
    return {"status": "success"}