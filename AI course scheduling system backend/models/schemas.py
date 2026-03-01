from typing import List, Dict
from pydantic import BaseModel

class PriorityRule(BaseModel):
    rule_id: int
    label: str
    enabled: bool

# 定义基础数据模型
class BaseData(BaseModel):
    fixedClassroom: bool = True
    PE_Time: bool = True
    PE_No_Clas: bool = True
    Lesson_Noon: bool = True
    Lab_Only_Noon: bool = False
    Multi_Classed: bool = False

class ScheduleRequest(BaseModel):
    basic: dict
    conflict: dict
    priority_rules: List[PriorityRule]  # 明确列表元素类型
    priorities: list
    teacherLimits: list
    forbidden: dict
# 可扩展其他模型（示例）
class ForbidSearchRequest(BaseModel):
    dimension: str
    keyword: str


