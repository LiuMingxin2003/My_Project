import pandas as pd
from ortools.sat.python import cp_model
import random

# ===================== 1. 数据读取函数 =====================
def load_teacher_info(filepath: str) -> pd.DataFrame:
    """
    示例：读取教师信息的 Excel 文件。
    - 你可根据实际表头对列名进行重命名或过滤。
    """
    df = pd.read_excel(filepath, skiprows=[0])  # 如果第一行是无用标题
    # 示例：假设原列名为 [工号, 姓名, 单位], 重命名为英文
    df.rename(columns={
        "工号": "teacher_id",
        "姓名": "teacher_name",
        "单位": "department"
    }, inplace=True)
    return df

def load_class_info(filepath: str) -> pd.DataFrame:
    """
    示例：读取班级信息的 Excel 文件。
    """
    df = pd.read_excel(filepath, skiprows=[0])
    df.rename(columns={
        "班级编号": "class_id",
        "班级名称": "class_name",
        "班级人数": "student_count",
        "专业编号": "major_id",
        "专业方向": "major_direction",
        "固定教室": "fixed_room"
    }, inplace=True)
    return df

def load_room_info(filepath: str) -> pd.DataFrame:
    """
    示例：读取教室信息的 Excel 文件。
    """
    df = pd.read_excel(filepath, skiprows=[0])  # 或不skip,视具体表头而定
    df.rename(columns={
        "教室编号": "room_id",
        "教室名称": "room_name",
        "最大上课容纳人数": "capacity",
        "教室类型": "room_type"
    }, inplace=True)
    return df

def load_task_info(filepath: str) -> pd.DataFrame:
    """
    示例：读取排课任务信息（含课程性质、教学班组成、指定教室类型等）。
    """
    df = pd.read_excel(filepath)
    df.rename(columns={
    "课程编号": "course_id",
    "课程名称": "course_name",
    "课程性质": "course_type",
    "任课教师": "teacher_name",  # 修改为 "任课教师"
    "教学班组成": "class_list_str",
    "指定教室类型": "required_room_type"
     }, inplace=True)

    return df

# ===================== 2. 数据预处理函数 =====================
def preprocess_tasks(df_tasks: pd.DataFrame,
                     df_classes: pd.DataFrame,
                     df_teachers: pd.DataFrame) -> list:
    """
    1) 筛选出必修课 (或其他你关心的课程)；
    2) 合班课聚合：将多班级合并为一个虚拟班级实体；
    3) 多学时拆分：若有需要，可将一门课的多学时分成多个排课块；
    4) 返回一个适合后续建模的任务列表，每个元素可能包含:
       {
         "task_id": ...,
         "course_id": ...,
         "course_name": ...,
         "teacher_id": ...,
         "class_list": [...],
         "total_students": ...,
         "required_room_type": ...,
         ...
       }
    """
    tasks = []
    task_id_counter = 0

    # 简单示例：仅提取必修课
    df_tasks_filtered = df_tasks[df_tasks["course_type"] == "必修课"].copy()

    for _, row in df_tasks_filtered.iterrows():
        c_id = row["course_id"]
        c_name = row["course_name"]
        t_name = row["teacher_name"]
        required_type = row.get("required_room_type", "").strip()

        # 匹配教师ID（假设teacher_name唯一）
        teacher_row = df_teachers[df_teachers["teacher_name"] == t_name]
        if teacher_row.empty:
            # 数据异常，跳过或记录
            continue
        teacher_id = teacher_row["teacher_id"].values[0]

        # 合班处理
        class_list_raw = str(row["class_list_str"]).split(",")
        class_list_raw = [cl.strip() for cl in class_list_raw if cl.strip()]
        # 计算合班总人数
        total_students = 0
        for cl in class_list_raw:
            # 在 df_classes 中查找对应班级
            match_row = df_classes[df_classes["class_name"] == cl]
            if match_row.empty:
                continue
            total_students += match_row["student_count"].values[0]

        # 这里示例：不拆分多学时，假设只需1次上课
        tasks.append({
            "task_id": task_id_counter,
            "course_id": c_id,
            "course_name": c_name,
            "teacher_id": teacher_id,
            "class_list": class_list_raw,  # 或合并成一个虚拟班级ID
            "total_students": total_students,
            "required_room_type": required_type if required_type else None
        })
        task_id_counter += 1

    return tasks

# ===================== 3. 构建CP模型 =====================
def build_cp_model(tasks_preprocessed: list,
                   df_rooms: pd.DataFrame,
                   df_teachers: pd.DataFrame,
                   df_classes: pd.DataFrame):
    """
    构建OR-Tools CP-SAT模型，只演示硬约束+简单目标。
    返回:
      model: CpModel对象
      x_vars: dict, x_vars[(task_id, time_slot_idx, room_id)] = BoolVar
      meta_data: 包含 teacher_of_task, room_capacity 等辅助信息
    """
    model = cp_model.CpModel()

    # 1) 时间段 (示例: 5天*8节=40个time slots)
    time_slots = []
    for d in range(5):  # 周一到周五
        for p in range(8):  # 每天8节
            time_slots.append((d, p))
    time_slot_indices = list(range(len(time_slots)))

    # 2) 教师列表 & 容量
    teacher_list = df_teachers["teacher_id"].unique().tolist()
    # 教室信息
    room_list = df_rooms["room_id"].unique().tolist()
    room_capacity = {}
    room_type = {}
    for _, row in df_rooms.iterrows():
        room_capacity[row["room_id"]] = row["capacity"]
        room_type[row["room_id"]] = row["room_type"]

    # 3) 构造变量
    x_vars = {}
    for task in tasks_preprocessed:
        for ts_idx in time_slot_indices:
            for r_id in room_list:
                var_name = f"x_{task['task_id']}_{ts_idx}_{r_id}"
                x_vars[(task['task_id'], ts_idx, r_id)] = model.NewBoolVar(var_name)

    # 4) 硬约束
    #   (H1) 教师时间唯一性
    #   (H2) 教室时间唯一性
    #   (H3) 班级时间唯一性
    #   (H4) 容量限制
    #   (H5) 指定教室类型

    # 教师索引映射
    teacher_of_task = {}
    for task in tasks_preprocessed:
        teacher_of_task[task["task_id"]] = task["teacher_id"]

    # (H1) 同一教师同一时段不能教多门
    for ts_idx in time_slot_indices:
        for t_id in teacher_list:
            # 找到该教师相关的task
            relevant_vars = []
            for task in tasks_preprocessed:
                if task["teacher_id"] == t_id:
                    relevant_vars.extend([x_vars[(task["task_id"], ts_idx, r)]
                                          for r in room_list])
            model.Add(sum(relevant_vars) <= 1)

    # (H2) 同一教室同一时段只能上一门课
    for ts_idx in time_slot_indices:
        for r_id in room_list:
            model.Add(sum(x_vars[(task["task_id"], ts_idx, r_id)]
                          for task in tasks_preprocessed) <= 1)

    # (H3) 班级时间唯一性
    # 对每个时段、每个班级，不得重复上课
    all_class_names = df_classes["class_name"].unique().tolist()
    for ts_idx in time_slot_indices:
        for cl_name in all_class_names:
            # 找到所有task中包含cl_name的
            relevant_vars = []
            for task in tasks_preprocessed:
                if cl_name in task["class_list"]:
                    for r_id in room_list:
                        relevant_vars.append(x_vars[(task["task_id"], ts_idx, r_id)])
            model.Add(sum(relevant_vars) <= 1)

    # (H4) 容量限制
    for task in tasks_preprocessed:
        for ts_idx in time_slot_indices:
            for r_id in room_list:
                # 当 x=1 时, total_students <= room_capacity[r_id]
                # CP-SAT 不支持 x * total_students 直接比较, 需要条件约束
                model.Add(task["total_students"] <= room_capacity[r_id]).OnlyEnforceIf(
                    x_vars[(task["task_id"], ts_idx, r_id)]
                )

    # (H5) 指定教室类型
    for task in tasks_preprocessed:
        req_type = task["required_room_type"]
        if req_type:
            for ts_idx in time_slot_indices:
                for r_id in room_list:
                    if room_type[r_id] != req_type:
                        model.Add(x_vars[(task["task_id"], ts_idx, r_id)] == 0)

    # 5) 简单目标: 尽量多排课 (或可加入更多软约束)
    model.Maximize(
        sum(x_vars[(task["task_id"], ts_idx, r_id)]
            for task in tasks_preprocessed
            for ts_idx in time_slot_indices
            for r_id in room_list)
    )

    # meta_data 里存储辅助信息，以便后续提取解或做局部搜索
    meta_data = {
        "tasks": tasks_preprocessed,
        "time_slots": time_slots,
        "room_list": room_list,
        "teacher_of_task": teacher_of_task
    }
    return model, x_vars, meta_data

# ===================== 4. 解读模型解 =====================
def extract_solution(solver: cp_model.CpSolver, x_vars: dict, meta_data: dict):
    """
    读取CP-SAT求解器的解，返回一个列表或DataFrame。
    """
    tasks = meta_data["tasks"]
    time_slots = meta_data["time_slots"]
    room_list = meta_data["room_list"]

    solution = []
    for task in tasks:
        t_id = task["task_id"]
        for ts_idx, slot in enumerate(time_slots):
            for r_id in room_list:
                if solver.Value(x_vars[(t_id, ts_idx, r_id)]) == 1:
                    day, period = slot
                    solution.append({
                        "task_id": t_id,
                        "course_id": task["course_id"],
                        "teacher_id": task["teacher_id"],
                        "class_list": task["class_list"],
                        "room_id": r_id,
                        "day_of_week": day,
                        "period": period
                    })
    return solution

# ===================== 5. 局部搜索优化示例 =====================
def local_search_improvement(base_solution: list,
                             meta_data: dict,
                             df_rooms: pd.DataFrame,
                             df_teachers: pd.DataFrame,
                             df_classes: pd.DataFrame) -> list:
    """
    示例：在初步可行解的基础上做随机邻域搜索或遗传算法等。
    此处仅做简化演示：
      - 随机挑选某个排课记录，尝试换到另一个教室或时间段，如果可行且提高目标则接受。
    """
    improved_solution = base_solution[:]  # 浅拷贝

    # 在实际中，需要写更完整的冲突检查、目标函数计算逻辑。
    # 这里仅演示一个随机扰动。

    for _ in range(10):  # 迭代次数
        idx = random.randint(0, len(improved_solution)-1)
        original_record = improved_solution[idx]

        # 随机生成一个新 day_of_week / period / room_id
        new_day = random.randint(0, 4)
        new_period = random.randint(0, 7)
        # 教室随机
        room_candidates = df_rooms["room_id"].unique().tolist()
        new_room = random.choice(room_candidates)

        # 简单检查容量是否足够
        # (更严谨的做法：还要检查教师、班级冲突等)
        task_obj = None
        for t in meta_data["tasks"]:
            if t["task_id"] == original_record["task_id"]:
                task_obj = t
                break
        if not task_obj:
            continue
        if task_obj["total_students"] > df_rooms.loc[df_rooms["room_id"]==new_room, "capacity"].values[0]:
            continue

        # 构造一个新的记录
        new_record = original_record.copy()
        new_record["day_of_week"] = new_day
        new_record["period"] = new_period
        new_record["room_id"] = new_room

        # 这里省略冲突检查(教师、班级、教室在同一时段是否占用)...
        # 假设没有冲突就可以替换
        improved_solution[idx] = new_record

    return improved_solution

# ===================== 6. 节假日调课示例 =====================
def holiday_reschedule(improved_solution: list,
                       holiday_list: list,
                       meta_data: dict) -> list:
    """
    若某天是节假日，则将该天所有课程移到其他时段。
    holiday_list: [0, 2] 表示周一、周三放假之类的示例。
    这里只做最简单的演示：把所有落在节假日day_of_week的课都移到 day=4(周五) 随机空闲节次。
    """
    final_solution = []
    for record in improved_solution:
        if record["day_of_week"] in holiday_list:
            # 强行移到周五
            record["day_of_week"] = 4
            record["period"] = random.randint(0,7)
        final_solution.append(record)
    return final_solution

# ===================== 7. 主函数 =====================
def main():
    # 1. 数据加载
    df_teachers = load_teacher_info("教师信息.xlsx")
    df_classes  = load_class_info("班级数据.xls")
    df_rooms    = load_room_info("教室信息.xls")
    df_tasks    = load_task_info("排课任务.xlsx")
    # 2. 预处理(必修课、合班、学时拆分等)
    tasks_preprocessed = preprocess_tasks(df_tasks, df_classes, df_teachers)

    # 3. 构建CP模型
    model, x_vars, meta_data = build_cp_model(tasks_preprocessed, df_rooms, df_teachers, df_classes)

    # 4. 求解(先满足硬约束)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3000  # 设置最大求解时间 5 分钟
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress =True
    solver.parameters.use_lns = True
    solver.parameters.linearization_level = 3
    solver.parameters.random_seed = 42

    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        base_solution = extract_solution(solver, x_vars, meta_data)
        improved_solution = local_search_improvement(base_solution, meta_data, df_rooms, df_teachers, df_classes)
        holiday_list = [2]  # 示例：周三放假
        final_solution = holiday_reschedule(improved_solution, holiday_list, meta_data)

        # 将结果封装到字典中返回
        result = {
            "status": "feasible",
            "base_solution": base_solution,
            "improved_solution": improved_solution,
            "final_solution": final_solution,
            "meta_data": meta_data
        }
        return result
    else:
        return {"status": "infeasible", "message": "未找到可行解，可能需要放宽约束或延长搜索时间。"}

if __name__ == "__main__":
    result = main()
    print(result)


