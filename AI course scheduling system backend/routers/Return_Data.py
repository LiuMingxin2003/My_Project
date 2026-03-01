from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from DataBase.Database_Return_Data import Update_Schedule
from routers.Chart_Course_Day import router

app = FastAPI()

class ScheduleUpdate(BaseModel):
    origin: dict
    target: dict
    course_data: dict  # ✅ 与前端字段名一致
    classroom: str     # ✅ 添加缺失的字段

@router.post("/Return_Data")
def Update_Schedule(update_data: ScheduleUpdate):  # ✅ 使用Pydantic模型
    print(f"Received schedule update: {update_data.dict()}")  # 正确
    return {"status": "success"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)