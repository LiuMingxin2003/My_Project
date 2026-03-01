# ==============================================================================
# 算法1.py - 完整最终代码 (CP-SAT 区间变量模型, 最小化超员, Room Name 匹配)
# ==============================================================================
import pandas as pd
from ortools.sat.python import cp_model
import random
import time
from collections import defaultdict
from tqdm import tqdm
import re
import math
import numpy as np
import traceback

# ===================== 1. 数据读取函数 =====================
# (基本保持不变，增加了清理和检查)
def load_teacher_info(filepath: str) -> pd.DataFrame:
    """读取教师信息"""
    print(f"Loading teacher info from: {filepath}")
    try:
        df = pd.read_excel(filepath, skiprows=[0])
        df.rename(columns={"工号": "teacher_id", "姓名": "teacher_name", "单位": "department"}, inplace=True, errors='ignore')
        if "teacher_id" not in df.columns or "teacher_name" not in df.columns: raise ValueError("教师信息文件缺少 '工号' 或 '姓名' 列。")
        df.dropna(subset=['teacher_id', 'teacher_name'], inplace=True)
        df['teacher_id'] = df['teacher_id'].astype(str).str.strip()
        df['teacher_name'] = df['teacher_name'].astype(str).str.strip()
        return df
    except FileNotFoundError: print(f"错误：找不到文件 {filepath}"); raise
    except Exception as e: print(f"加载教师信息时出错: {e}"); raise

def load_class_info(filepath: str) -> pd.DataFrame:
    """读取班级信息"""
    print(f"Loading class info from: {filepath}")
    try:
        df = pd.read_excel(filepath, skiprows=[0])
        df.rename(columns={"班级编号": "class_id", "班级名称": "class_name", "班级人数": "student_count", "专业编号": "major_id", "专业方向": "major_direction", "固定教室": "fixed_room"}, inplace=True, errors='ignore')
        if "class_name" not in df.columns or "student_count" not in df.columns: raise ValueError("班级数据文件缺少 '班级名称' 或 '班级人数' 列。")
        df['student_count'] = pd.to_numeric(df['student_count'], errors='coerce').fillna(0).astype(int)
        if 'class_name' in df.columns: df['class_name'] = df['class_name'].astype(str).str.strip()
        if 'fixed_room' in df.columns: df['fixed_room'] = df['fixed_room'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() else None)
        df.dropna(subset=['class_name'], inplace=True)
        return df
    except FileNotFoundError: print(f"错误：找不到文件 {filepath}"); raise
    except Exception as e: print(f"加载班级数据时出错: {e}"); raise

def load_room_info(filepath: str) -> pd.DataFrame:
    """读取教室信息"""
    print(f"Loading room info from: {filepath}")
    try:
        df = pd.read_excel(filepath, skiprows=[0])
        df.rename(columns={"教室编号": "room_id", "教室名称": "room_name", "最大上课容纳人数": "capacity", "教室类型": "room_type"}, inplace=True, errors='ignore')
        if "room_id" not in df.columns or "capacity" not in df.columns or "room_name" not in df.columns: raise ValueError("教室信息缺少 'room_id', 'capacity', 或 'room_name' 列。")
        df['capacity'] = pd.to_numeric(df['capacity'], errors='coerce').fillna(0).astype(int)
        df['room_id'] = df['room_id'].astype(str).str.strip()
        df['room_name'] = df['room_name'].astype(str).str.strip()
        if df['room_id'].duplicated().any(): print("Warning: Duplicate room_id found!")
        if df['room_name'].duplicated().any(): print("Warning: Duplicate room_name found!")
        df.dropna(subset=['room_id', 'room_name'], inplace=True)
        return df
    except FileNotFoundError: print(f"错误：找不到文件 {filepath}"); raise
    except Exception as e: print(f"加载教室信息时出错: {e}"); raise

def load_task_info(filepath: str) -> pd.DataFrame:
    """读取排课任务信息"""
    print(f"Loading task info from: {filepath}")
    try:
        df = pd.read_excel(filepath)
        required_cols = ["课程编号", "课程名称", "课程性质", "任课教师", "教学班组成", "开课周次学时", "连排节次"]
        optional_cols = ["指定教室", "指定教室类型"]
        for col in required_cols:
             if col not in df.columns: raise ValueError(f"排课任务文件缺少必需列: '{col}'")
        for col in optional_cols:
             if col not in df.columns: df[col] = None
        if '任课教师' in df.columns: df['任课教师'] = df['任课教师'].astype(str).str.strip()
        if '指定教室' in df.columns: df['指定教室'] = df['指定教室'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() else None)
        return df
    except FileNotFoundError: print(f"错误：找不到文件 {filepath}"); raise
    except Exception as e: print(f"加载排课任务时出错: {e}"); raise

# ===================== 2. 数据预处理 (按需拆分4学时任务) =====================
import re
import math
import numpy as np
# (确保 pandas, tqdm, defaultdict 已导入)

def preprocess_tasks(df_tasks: pd.DataFrame,
                     df_classes: pd.DataFrame,
                     df_teachers: pd.DataFrame,
                     df_rooms: pd.DataFrame,
                     room_capacity_dict_by_name: dict,
                     max_overall_capacity: float,
                     class_name_to_fixed_room_name: dict) -> list:
    """
    预处理任务数据，为区间变量模型准备 "task units"。
    修改点：
    1. 每周 4 学时的任务拆分成 2 个 2 学时的单元。
    2. 其他多学时任务保持 H 学时连排。
    3. 移除容量预检 (最小化超员)。
    4. 使用教室名称匹配固定教室。
    """
    print("Preprocessing tasks (Splitting H=4 tasks into 2x2 blocks)...") # 更新描述
    task_units = []
    task_unit_id_counter = 0
    missing_teachers = set(); missing_classes_in_specific_tasks = set()
    skipped_tasks_fixed_room_conflict = 0

    # --- 数据准备 (不变) ---
    teacher_name_to_id = pd.Series(df_teachers.teacher_id.values, index=df_teachers.teacher_name).to_dict()
    class_name_to_students = pd.Series(df_classes.student_count.values, index=df_classes.class_name).to_dict()
    all_class_names_list = df_classes["class_name"].tolist()
    print(f"Total number of unique classes found: {len(all_class_names_list)}")
    print(f"Using pre-calculated max room capacity: {max_overall_capacity}")
    # --- 结束准备 ---

    # --- 检查并处理所需列 (不变) ---
    if '指定教室' not in df_tasks.columns: df_tasks['指定教室'] = None
    if '开课周次学时' not in df_tasks.columns: df_tasks['开课周次学时'] = '1-1:1'
    if '连排节次' not in df_tasks.columns: df_tasks['连排节次'] = 1 # 连排节次在这里意义不大，因为我们根据H拆分
    # --- 结束检查处理列 ---

    # --- 过滤任务 ---
    df_tasks_filtered = df_tasks[df_tasks["课程性质"] == "必修课"].copy()
    print(f"Filtered {len(df_tasks_filtered)} initial mandatory tasks based on '课程性质' == '必修课'.")
    # --- 结束过滤 ---

    # --- 迭代原始任务 ---
    print("Processing original tasks and creating weekly task units (splitting H=4):")
    for index, row in tqdm(df_tasks_filtered.iterrows(), total=len(df_tasks_filtered), desc="Preprocessing Tasks"):
        original_task_ref = f"orig_{index}"
        # --- 获取基本信息 ---
        c_id = row.get("课程编号"); c_name = row.get("课程名称")
        t_name = row.get("任课教师", "").strip(); course_type = row.get("课程性质")
        # 解析周学时 H
        weekly_hours_str = str(row.get("开课周次学时", '1-1:1')).strip(); weekly_periods = 1
        match_hours = re.search(r':(\d+)$', weekly_hours_str)
        if match_hours:
            try:
                duration = max(1, int(match_hours.group(1)))
            except ValueError:
                duration = 1
        required_type = None
        task_fixed_room_name = str(row.get("指定教室")).strip() if pd.notna(row.get("指定教室")) and str(row.get("指定教室")).strip() else None
        # --- 结束获取 ---

        teacher_id = teacher_name_to_id.get(t_name)
        if teacher_id is None:
            if t_name not in missing_teachers:
                 missing_teachers.add(t_name)
            continue

        # --- 判断班级情况并确定处理组 (不变) ---
        class_list_str_raw = row.get("教学班组成")
        is_empty_or_nan = pd.isna(class_list_str_raw) or (isinstance(class_list_str_raw, str) and not class_list_str_raw.strip())
        task_groups_to_process = []
        if course_type == "必修课" and is_empty_or_nan:
            for class_name in all_class_names_list:
                student_count = class_name_to_students.get(class_name)
                if student_count is not None and student_count > 0:
                    class_fixed_room_name = class_name_to_fixed_room_name.get(class_name)
                    final_fixed_room_name = task_fixed_room_name if task_fixed_room_name else class_fixed_room_name
                    task_groups_to_process.append({"class_list": [class_name], "total_students": student_count, "group_ref": class_name, "effective_fixed_room_name": final_fixed_room_name})
        elif not is_empty_or_nan:
            class_list_str = str(class_list_str_raw).strip()
            class_list_raw = [cl.strip() for cl in class_list_str.split(',') if cl.strip()]
            if class_list_raw:
                total_students = 0; valid_class_list = []; task_missing_classes = False
                effective_fixed_room_name = task_fixed_room_name; first_class_fixed_room_name = None; fixed_room_conflict = False
                for cl in class_list_raw:
                    student_count = class_name_to_students.get(cl)
                    if student_count is not None:
                        if student_count > 0:
                            total_students += student_count; valid_class_list.append(cl)
                            current_class_fixed_name = class_name_to_fixed_room_name.get(cl)
                            if current_class_fixed_name:
                                if first_class_fixed_room_name is None: first_class_fixed_room_name = current_class_fixed_name
                                elif first_class_fixed_room_name != current_class_fixed_name: fixed_room_conflict = True; break
                    else:
                        if cl not in missing_classes_in_specific_tasks: missing_classes_in_specific_tasks.add(cl)
                        task_missing_classes = True
                if fixed_room_conflict: skipped_tasks_fixed_room_conflict += 1; continue
                if not effective_fixed_room_name and first_class_fixed_room_name: effective_fixed_room_name = first_class_fixed_room_name
                if not task_missing_classes and valid_class_list and total_students > 0:
                    task_groups_to_process.append({"class_list": valid_class_list, "total_students": total_students, "group_ref": "_".join(sorted(valid_class_list)), "effective_fixed_room_name": effective_fixed_room_name})
        # --- 结束班级判断 ---

        # --- 生成 task unit (根据 H 进行拆分) ---
        for group_info in task_groups_to_process:
            group_ref = group_info["group_ref"]; required_students = group_info["total_students"]
            effective_fixed_room_name = group_info["effective_fixed_room_name"]

            # *** 新增：根据 weekly_periods (H) 决定生成多少个 task unit 及它们的 duration ***
            units_to_create = []
            if weekly_periods == 4:
                 # 4 学时拆成 2 个 2 学时的单元
                 units_to_create.append({"duration": 2, "consecutive": 2, "block_index": 0})
                 units_to_create.append({"duration": 2, "consecutive": 2, "block_index": 1})
                 # print(f"  Splitting task {c_name} (Group: {group_ref}, H=4) into two 2-hour blocks.")
            elif weekly_periods > 1:
                 # 2 或 3 学时，保持为一个单元，时长 H，要求连排 H
                 units_to_create.append({"duration": weekly_periods, "consecutive": weekly_periods, "block_index": 0})
            else: # weekly_periods == 1
                 units_to_create.append({"duration": 1, "consecutive": 1, "block_index": 0})

            # 为每个需要创建的单元生成 task_unit 字典
            for unit_info in units_to_create:
                task_units.append({
                    "task_unit_id": task_unit_id_counter,
                    "original_task_ref": f"{original_task_ref}_{group_ref}",
                    "block_index": unit_info["block_index"], # 标记是哪个块
                    "duration": unit_info["duration"], # <--- 使用单元的时长
                    "required_consecutive": unit_info["consecutive"], # <--- 使用单元的连排要求
                    "course_id": c_id, "course_name": c_name, "teacher_id": teacher_id,
                    "class_list": group_info["class_list"], "total_students": required_students,
                    "required_room_type": required_type, # None
                    "fixed_room_name": effective_fixed_room_name
                })
                task_unit_id_counter += 1
            # --- 结束为单元生成字典 ---
        # --- 结束为班级组生成 task unit ---
    # --- 结束主循环 ---

    # --- 打印警告 (不变) ---
    if missing_teachers: print(f"\nWarning Summary: Skipped tasks for teachers not found: {missing_teachers}")
    if missing_classes_in_specific_tasks: print(f"\nWarning Summary: Skipped tasks involving specific classes not found: {missing_classes_in_specific_tasks}")
    # if skipped_tasks_capacity > 0: # 已移除
    if skipped_tasks_fixed_room_conflict > 0: print(f"\nWarning Summary: Skipped {skipped_tasks_fixed_room_conflict} task groups due to conflicting fixed rooms.")

    print(f"\nPreprocessing finished. Generated {len(task_units)} weekly task units for scheduling (H=4 split into 2x2).")
    return task_units if task_units else None

# ===================== 3. 构建 CP 模型 (最小化超员 + 混合匹配) =====================
def build_cp_model(task_units_preprocessed: list,
                   df_rooms: pd.DataFrame, # 需要用来获取 room ID
                   df_teachers: pd.DataFrame,
                   df_classes: pd.DataFrame,
                   # *** 接收 ID->Capacity 字典, Name->ID 映射, ID列表 ***
                   room_capacity_dict_by_id: dict,
                   room_name_to_id_map: dict,
                   all_room_ids: list):
    """
    构建使用区间变量的 CP-SAT 模型。
    目标：最小化教室容量的总超员人数。
    匹配逻辑：指定教室按 Name 匹配查找对应 ID，无指定则考虑所有教室 ID。
    """
    print("Building CP-SAT model (Minimize Overflow, Hybrid Room Match)...")
    model = cp_model.CpModel()

    # --- 1. 基础数据准备 ---
    time_slots = [(d, p) for d in range(5) for p in range(8)]; num_time_slots = len(time_slots)
    if not all_room_ids: raise ValueError("教室 ID 列表为空!")
    teacher_name_to_id = pd.Series(df_teachers.teacher_id.values, index=df_teachers.teacher_name).to_dict()
    T_ZG_ID = teacher_name_to_id.get("张桂华"); T_ZL_ID = teacher_name_to_id.get("张岚")
    print(f"Teacher IDs for specific constraints: 张桂华={T_ZG_ID}, 张岚={T_ZL_ID}")
    # --- 结束基础数据准备 ---

    # --- 2. 按原始任务分组 (不变) ---
    task_units_by_original = defaultdict(list);
    for task_unit in task_units_preprocessed: task_units_by_original[task_unit['original_task_ref']].append(task_unit)
    # --- 结束分组 ---

    # --- 3. 构造变量 (混合匹配逻辑, 移除容量剪枝, 添加超员变量) ---
    print("Creating interval vars, presence literals, and overflow vars (pruning by Fixed Room Name, Teacher Time)...")
    all_intervals = defaultdict(dict)
    presence_literals_per_task = defaultdict(list)
    task_units_with_no_valid_assignment = set()
    all_overflow_vars = []
    max_possible_total_overflow = 0

    for task_unit in tqdm(task_units_preprocessed, desc="Creating Variables"):
        try:
            tu_id = task_unit["task_unit_id"]; duration = task_unit["duration"]
            required_students = task_unit["total_students"]; teacher_id = task_unit["teacher_id"]
            fixed_room_name = task_unit.get("fixed_room_name") # 获取指定教室名称

            if duration <= 0 or duration > num_time_slots: task_units_with_no_valid_assignment.add(tu_id); continue

            possible_room_ids = [] # 存储最终考虑的 Room ID 列表
            # *** 实现混合匹配逻辑 ***
            if fixed_room_name:
                fixed_room_id = room_name_to_id_map.get(fixed_room_name)
                if fixed_room_id and fixed_room_id in room_capacity_dict_by_id: # 确保 Name->ID 映射有效且 ID 有容量信息
                     possible_room_ids = [fixed_room_id] # 只考虑这一个 ID
                     # 容量限制将在 overflow 变量中体现
                else: task_units_with_no_valid_assignment.add(tu_id); continue # 指定教室无效
            else:
                # 没有指定教室，所有教室 ID 都可能 (容量限制在 overflow 处理)
                possible_room_ids = all_room_ids

            if not possible_room_ids: task_units_with_no_valid_assignment.add(tu_id); continue

            task_presences = []
            morning_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if p < 4}
            afternoon_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if p >= 4}

            for room_id in possible_room_ids: # 迭代可能的 Room ID
                room_cap = room_capacity_dict_by_id.get(room_id, 0) # 使用 ID 字典获取容量
                overflow_amount = max(0, required_students - room_cap)
                max_possible_total_overflow += overflow_amount # 累加

                # --- 教师时间剪枝 ---
                start_domain = cp_model.Domain(0, num_time_slots - duration)
                possible_starts = set(range(num_time_slots - duration + 1))
                if teacher_id == T_ZG_ID: valid_starts = {s for s in possible_starts if all(s + i in morning_slots for i in range(duration))}; start_domain = cp_model.Domain.FromValues(list(valid_starts))
                elif teacher_id == T_ZL_ID: valid_starts = {s for s in possible_starts if all(s + i in afternoon_slots for i in range(duration))}; start_domain = cp_model.Domain.FromValues(list(valid_starts))
                if not start_domain.FlattenedIntervals(): continue

                # --- 创建核心变量 (使用 room_id) ---
                presence_var = model.NewBoolVar(f'presence_{tu_id}_{room_id}')
                start_var = model.NewIntVarFromDomain(start_domain, f'start_{tu_id}_{room_id}')
                interval_var = model.NewOptionalFixedSizeIntervalVar(start=start_var, size=duration, is_present=presence_var, name=f'interval_{tu_id}_{room_id}')
                all_intervals[(tu_id, room_id)] = interval_var
                task_presences.append(presence_var)

                # --- 创建超员变量并关联 ---
                overflow_var = model.NewIntVar(0, overflow_amount, f'overflow_{tu_id}_{room_id}')
                model.Add(overflow_var == overflow_amount).OnlyEnforceIf(presence_var)
                model.Add(overflow_var == 0).OnlyEnforceIf(presence_var.Not())
                all_overflow_vars.append(overflow_var)

            if task_presences: presence_literals_per_task[tu_id] = task_presences
            else: task_units_with_no_valid_assignment.add(tu_id)

        except KeyError as e: print(f"\n>>> BUILD KeyError: {e} in task_unit: {task_unit}"); raise
        except Exception as e: print(f"\n>>> BUILD Error: {e} processing {task_unit}"); raise

    if task_units_with_no_valid_assignment: print(f"\nWarning Summary: {len(task_units_with_no_valid_assignment)} task units skipped (invalid fixed room or no valid time after pruning).")
    print(f"Created {len(all_intervals)} optional interval variables (unique task-room combos).")
    print(f"Created {len(all_overflow_vars)} overflow variables.")
    # --- 结束构造变量 ---

    # --- 4. 添加约束 ---
    print("Adding constraints...")
    # (H0) ExactlyOne Room (不变)
    print("  - Adding Task Assignment (ExactlyOne Room)..."); assigned_task_unit_count = 0
    for tu_id, presence_vars in presence_literals_per_task.items():
        if tu_id in task_units_with_no_valid_assignment: continue
        if presence_vars: model.AddExactlyOne(presence_vars); assigned_task_unit_count += 1
    print(f"  - ExactlyOne constraints added for {assigned_task_unit_count} task units.")

    # (H1, H2, H3) NoOverlap (不变)
    print("  - Adding NoOverlap constraints for Resources...")
    intervals_in_room=defaultdict(list); intervals_for_teacher=defaultdict(list); intervals_for_class=defaultdict(list)
    task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units_preprocessed}
    for (tu_id, room_id), interval_var in all_intervals.items():
        task_unit = task_unit_lookup.get(tu_id);
        if not task_unit: continue
        teacher_id = task_unit["teacher_id"]; class_list = task_unit.get("class_list", [])
        intervals_in_room[room_id].append(interval_var)
        intervals_for_teacher[teacher_id].append(interval_var)
        for class_name in class_list:
             if isinstance(class_name, str) and class_name: intervals_for_class[class_name].append(interval_var)
    print("    - Applying NoOverlap for rooms..."); [model.AddNoOverlap(intervals) for intervals in intervals_in_room.values() if len(intervals) > 1]
    print("    - Applying NoOverlap for teachers...");[model.AddNoOverlap(intervals) for intervals in intervals_for_teacher.values() if len(intervals) > 1]
    print("    - Applying NoOverlap for classes..."); [model.AddNoOverlap(intervals) for intervals in intervals_for_class.values() if len(intervals) > 1]

    # (H_Load) 教师负载约束 (不变)
    print("  - Adding Teacher load constraints (based on task count)...")
    teacher_weekly_presence = defaultdict(list)
    for tu_id, presence_vars in presence_literals_per_task.items():
         task_unit = task_unit_lookup.get(tu_id);
         if not task_unit: continue
         teacher_id = task_unit["teacher_id"]
         task_presence_var = model.NewBoolVar(f'task_present_{tu_id}')
         model.Add(sum(presence_vars) == 1).OnlyEnforceIf(task_presence_var)
         model.Add(sum(presence_vars) == 0).OnlyEnforceIf(task_presence_var.Not())
         teacher_weekly_presence[teacher_id].append(task_presence_var)
    if T_ZG_ID and T_ZG_ID in teacher_weekly_presence: model.Add(sum(teacher_weekly_presence[T_ZG_ID]) <= 5); print(f"    - Weekly load constraint added for 张桂华 (ID: {T_ZG_ID})")
    if T_ZL_ID and T_ZL_ID in teacher_weekly_presence: model.Add(sum(teacher_weekly_presence[T_ZL_ID]) <= 3); print(f"    - Weekly load constraint added for 张岚 (ID: {T_ZL_ID})")


    # --- 5. 设置优化目标：最小化总超员量 --- (不变)
    print("  - Setting Objective: Minimize Total Capacity Overflow...")
    if all_overflow_vars:
         print(f"    - Calculated Max Possible Total Overflow: {max_possible_total_overflow}")
         safe_upper_bound = max(0, int(max_possible_total_overflow))
         if safe_upper_bound == 0 and all_overflow_vars:
             has_potential_overflow = any(ov.UpperBound > 0 for ov in all_overflow_vars if hasattr(ov, 'UpperBound')) # Approximate check
             if has_potential_overflow: safe_upper_bound = sum(tu['total_students'] for tu in task_units_preprocessed)
         total_overflow_var = model.NewIntVar(0, safe_upper_bound, 'total_overflow')
         model.Add(total_overflow_var == sum(all_overflow_vars))
         model.Minimize(total_overflow_var)
    else: print("    - No overflow variables created. No overflow objective added.")

    print("Model building complete.")
    # 传递 id->name 映射给 extract_solution
    if 'room_id' in df_rooms.columns and 'room_name' in df_rooms.columns:
         room_id_to_name_map = pd.Series(df_rooms.room_name.values, index=df_rooms.room_id).to_dict()
    else: room_id_to_name_map = {}
    # *** 修正 meta_data 中 overflow_vars 的创建 ***
    # 创建一个正确的 (tu_id, room_id) -> overflow_var 映射
    overflow_vars_dict = {}
    temp_overflow_vars = all_overflow_vars[:] # 创建副本以安全迭代
    for (tu_id, room_id), interval_var in all_intervals.items():
        # 假设 overflow_vars 的顺序与 all_intervals 迭代器创建时的顺序一致
        # 这是一个比较脆弱的假设，更好的方式是在创建 overflow_var 时就存入字典
        if temp_overflow_vars: # 确保列表不为空
             overflow_vars_dict[(tu_id, room_id)] = temp_overflow_vars.pop(0)
        else:
             print(f"Warning: Mismatch between number of intervals and overflow variables for ({tu_id}, {room_id})")

    meta_data = {
        "task_units": task_units_preprocessed, "time_slots": time_slots,
        "all_intervals": all_intervals,
        "overflow_vars": overflow_vars_dict, # <<< 使用修正后的字典
        "room_id_to_name": room_id_to_name_map
    }
    return model, None, meta_data

# ===================== 4. 解读模型解 (区间变量 + 超员量) =====================
# (这个函数上次是正确的，保持不变)
def extract_solution(solver: cp_model.CpSolver, x_vars: dict, meta_data: dict) -> list:
    """读取CP-SAT使用区间变量的解，并包含超员量信息。"""
    print("Extracting solution from Interval Variable model (with overflow)...")
    task_units = meta_data["task_units"]; time_slots = meta_data["time_slots"]
    all_intervals = meta_data["all_intervals"]; overflow_vars = meta_data.get("overflow_vars", {})
    room_id_to_name = meta_data.get("room_id_to_name", {}); solution = []
    if not task_units or solver.StatusName() not in ["OPTIMAL", "FEASIBLE"]: return []

    start_time_ext = time.time(); assigned_task_unit_count = 0; total_schedule_overflow = 0
    print("Extracting assignments and overflow (with progress):")
    task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units}
    presence_literals_per_task = defaultdict(list) # 重新计算用于比较
    for tu_id in all_intervals:
        if all_intervals[tu_id]: presence_literals_per_task[tu_id] = list(all_intervals[tu_id].values())


    for (tu_id, room_id), interval_var in tqdm(all_intervals.items(), desc="Extracting Solution"):
        presence_literal = interval_var.PresenceLiteral()
        if presence_literal is not None and solver.BooleanValue(presence_literal):
            task_unit = task_unit_lookup.get(tu_id);
            if not task_unit: continue
            start_idx = solver.Value(interval_var.StartExpr()); duration = task_unit["duration"]
            room_name = room_id_to_name.get(room_id, str(room_id)); overflow_amount = 0
            overflow_var = overflow_vars.get((tu_id, room_id))
            current_task_overflow = 0 # 当前任务的超员量
            if overflow_var is not None:
                 try: current_task_overflow = solver.Value(overflow_var)
                 except: print(f"Warning: Could not get value for overflow var for task {tu_id}, room {room_id}")

            # 只在找到第一个分配时累加总超员和计数
            if tu_id not in [s['task_unit_id'] for s in solution if s['is_start_period']]: # 避免重复计数
                total_schedule_overflow += current_task_overflow
                assigned_task_unit_count += 1

            for i in range(duration):
                ts_idx = start_idx + i
                if 0 <= ts_idx < len(time_slots):
                    day, period = time_slots[ts_idx]
                    solution.append({
                        "task_unit_id": tu_id, "original_task_ref": task_unit.get("original_task_ref", "N/A"),
                        "duration": duration, "course_id": task_unit.get("course_id", "N/A"),
                        "course_name": task_unit.get("course_name", "N/A"), "teacher_id": task_unit.get("teacher_id", "N/A"),
                        "class_list": task_unit.get("class_list", []), "room_id": room_id, "room_name": room_name,
                        "day_of_week": day, "period": period, "is_start_period": (i == 0),
                        "student_overflow": current_task_overflow # 使用当前任务的超员量
                    })

    end_time_ext = time.time()
    num_tasks_in_model = len(presence_literals_per_task)
    print(f"Solution extraction complete. Extracted assignments for {assigned_task_unit_count} task units in {end_time_ext - start_time_ext:.2f} seconds.")
    print(f"Sum of Overflows for assigned tasks: {total_schedule_overflow}")
    if assigned_task_unit_count != num_tasks_in_model: print(f"Warning: Assigned task units ({assigned_task_unit_count}) != task units in model ({num_tasks_in_model}).")

    return solution

# ===================== 7. 主函数 (CP-SAT 专用) =====================
# (这个函数应该已经是正确的，调用了修正后的 preprocess 和 build)
def run_cp_sat_scheduler():
    """使用 CP-SAT 进行排课的主流程 (使用教室名称匹配, 最小化超员)"""
    print("--- Starting CP-SAT Scheduler (Minimize Overflow, Room Name Match) ---")
    start_total_time = time.time()

    # --- 文件路径 ---
    teacher_file = "教师信息.xlsx"; class_file = "班级数据.xls"
    room_file = "教室信息.xls"; task_file = "排课任务.xlsx"
    output_file = "课程表方案_CP_SAT_MinOverflow.xlsx"

    # --- 1. 数据加载 ---
    print("\n--- Step 1: Loading Data ---")
    load_start = time.time()
    try:
        df_teachers = load_teacher_info(teacher_file)
        df_classes = load_class_info(class_file)
        df_rooms = load_room_info(room_file)
        df_tasks = load_task_info(task_file)
        if df_rooms.empty or df_teachers.empty or df_classes.empty or df_tasks.empty: return None
    except Exception as e: print(f"数据加载出错: {e}"); return None
    load_end = time.time(); print(f"Data Loading completed in {load_end - load_start:.2f} seconds.")

    # --- 1.5 创建查找字典 ---
    print("\n--- Step 1.5: Creating Lookups ---")
    try:
        # 按 Name 索引的容量字典
        if 'room_name' not in df_rooms.columns or 'capacity' not in df_rooms.columns or 'room_id' not in df_rooms.columns: raise ValueError("教室信息缺少列")
        df_rooms['capacity'] = pd.to_numeric(df_rooms['capacity'], errors='coerce').fillna(0).astype(int)
        room_capacity_dict_by_name = pd.Series(df_rooms.capacity.values, index=df_rooms.room_name).to_dict()
        # 按 ID 索引的容量字典
        room_capacity_dict_by_id = pd.Series(df_rooms.capacity.values, index=df_rooms.room_id).to_dict()
        # Name -> ID 映射
        room_name_to_id_map = pd.Series(df_rooms.room_id.values, index=df_rooms.room_name).to_dict()
        # ID -> Name 映射
        room_id_to_name_map = pd.Series(df_rooms.room_name.values, index=df_rooms.room_id).to_dict()
        all_room_ids = df_rooms["room_id"].tolist()
        max_overall_capacity = df_rooms['capacity'].max() if not df_rooms.empty else 0
        print(f"Created room lookups. Max capacity: {max_overall_capacity}")
        # Class -> Fixed Room Name 映射
        class_name_to_fixed_room_name = {}
        if '指定教室' in df_classes.columns and 'class_name' in df_classes.columns:
            for index, row in df_classes.iterrows():
                 class_name = row['class_name']
                 fixed_room_name = str(row['指定教室']).strip() if pd.notna(row['指定教室']) and str(row['指定教室']).strip() else None
                 if class_name and fixed_room_name:
                      if fixed_room_name not in room_capacity_dict_by_name: print(f"Warning: Fixed room name '{fixed_room_name}' for class '{class_name}' not found. Ignored.")
                      else: class_name_to_fixed_room_name[class_name] = fixed_room_name
            print(f"Created class-to-fixed-room lookup for {len(class_name_to_fixed_room_name)} classes.")
        else: print("Warning: '指定教室' column not found. Class fixed room constraint ignored.")
    except Exception as e: print(f"创建查找字典时出错: {e}"); traceback.print_exc(); return None
    # --- 结束创建字典 ---

    # --- 2. 预处理 ---
    print("\n--- Step 2: Preprocessing Tasks ---")
    preprocess_start = time.time()
    try:
        # *** 确保传递基于 Name 的字典 ***
        tasks_preprocessed = preprocess_tasks(
            df_tasks, df_classes, df_teachers, df_rooms, # 传递 df_rooms
            room_capacity_dict_by_name, max_overall_capacity, # 传递 Name 容量字典和 Max Cap
            class_name_to_fixed_room_name
        )
        if tasks_preprocessed is None or not tasks_preprocessed: return None
    except Exception as e: print(f"任务预处理出错: {e}"); traceback.print_exc(); return None
    preprocess_end = time.time(); print(f"Task Preprocessing completed in {preprocess_end - preprocess_start:.2f} seconds.")

    # --- 3. 构建 CP 模型 ---
    print("\n--- Step 3: Building CP-SAT Model ---")
    build_start = time.time()
    try:
        # *** 确保传递基于 ID 的字典和映射 ***
        model, _, meta_data = build_cp_model(
            tasks_preprocessed, df_rooms, df_teachers, df_classes,
            room_capacity_dict_by_id, # ID 容量字典
            room_name_to_id_map,      # Name->ID 映射
            all_room_ids
        )
    except Exception as e: print(f"构建 CP 模型时出错: {e}"); traceback.print_exc(); return None
    build_end = time.time(); print(f"Model Building completed in {build_end - build_start:.2f} seconds.")

    # --- 4. 求解 ---
    print("\n--- Step 4: Solving the Model ---")
    solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = 1000
    solver.parameters.num_search_workers = 8; solver.parameters.log_search_progress = True
    solve_start_time = time.time()
    try: status = solver.Solve(model)
    except Exception as e: print(f"调用 solver.Solve 时发生错误: {e}"); return None
    solve_end_time = time.time()
    print(f"Solving attempt finished in {solve_end_time - solve_start_time:.2f}s (Solver Wall Time: {solver.WallTime():.2f}s).")

    # --- 5. 处理结果 ---
    print("\n--- Step 5: Processing Results ---")
    process_start = time.time()
    result_data = {"status": solver.StatusName()}
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"Solution found! Status: {solver.StatusName()}");
        print(f"Objective value (minimized total overflow): {solver.ObjectiveValue()}")
        meta_data['room_id_to_name'] = room_id_to_name_map # 确保传递映射
        solution_list = extract_solution(solver, None, meta_data) # 调用 extract
        if solution_list:
            try:
                df_solution = pd.DataFrame(solution_list)
                df_solution.to_excel(output_file, index=False)
                print(f"Solution successfully saved to {output_file}")
                result_data["output_file"] = output_file
            except Exception as e: print(f"Error saving solution: {e}"); result_data["status"] = "ERROR_SAVING"
        else: print("Error: Solution extraction failed."); result_data["status"] = "ERROR_EXTRACTING"
    elif status == cp_model.INFEASIBLE: print("Solver proved infeasible.")
    elif status == cp_model.MODEL_INVALID: print("Error: Invalid model.")
    else: print(f"Solver finished: {solver.StatusName()}. No solution found.")
    process_end = time.time(); print(f"Result Processing completed in {process_end - process_start:.2f} seconds.")
    end_total_time = time.time(); print(f"\nTotal script execution time: {end_total_time - start_total_time:.2f} seconds.")
    return result_data

# --- 主程序入口 ---
if __name__ == "__main__":
    print("========================================")
    print(" Starting Course Scheduling using CP-SAT (Minimize Overflow, Room Name Match)")
    print("========================================")
    final_result = run_cp_sat_scheduler()
    print("\n--- Final Summary ---")
    if final_result:
        print(f"Final Status: {final_result.get('status', 'N/A')}")
        if "output_file" in final_result:
            print(f"Output File: {final_result.get('output_file')}")
            print("\nNext Step: Check Excel for schedule and 'student_overflow'. Verify basic conflicts.")
        elif final_result.get('status') == 'INFEASIBLE':
             print("The problem remains infeasible even when minimizing overflow.")
        else: print("Scheduler finished, but may not have produced a valid output file.")
    else: print("Scheduler script failed to run completely.")
    print("========================================")