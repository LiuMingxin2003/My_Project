from fastapi import APIRouter, HTTPException

from DataBase.DataBase_Test import main, transform_data
from database import get_connection
from models.schemas import ForbidSearchRequest

router = APIRouter()



@router.post("/test")
async def handle_forbid_search(request: ForbidSearchRequest):
    result = main(request.keyword,request.dimension)
    result_finally = transform_data(result)
    # 简单校验逻辑
    if result != 'a':
        return {
            "status": "success",
            "data": result_finally
        }
    else:
        raise HTTPException(
            status_code=404,
            detail="未找到信息"
        )