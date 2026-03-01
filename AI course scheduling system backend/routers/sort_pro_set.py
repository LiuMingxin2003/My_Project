from fastapi import APIRouter, HTTPException
from database import get_connection
from models.schemas import ForbidSearchRequest

router = APIRouter()

@router.post("/sort_pro_set")
async def handle_forbid_search(request: ForbidSearchRequest):
    # 简单校验逻辑
    if request.dimension.lower() == "a":
        return {
            "status": "success",
            "data": {
                "name": "李华",
                "id": "123456",
                "position": "高级教师"
            }
        }
    else:
        raise HTTPException(
            status_code=404,
            detail="未找到该教师信息"
        )