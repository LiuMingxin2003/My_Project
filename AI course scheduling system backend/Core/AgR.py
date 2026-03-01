import pandas as pd
from ortools.sat.python import cp_model
import random
import time # 引入 time 模块
from collections import defaultdict
from tqdm import tqdm
import re
# ===================== 1. 数据读取函数 =====================
# (保持你原来的 load_teacher_info, load_class_info, load_room_info, load_task_info 函数不变)
def load_teacher_info(filepath: str) -> pd.DataFrame:
    """示例：读取教师信息的 Excel 文件。"""
    print(f"Loading teacher info from: {filepath}")
    # 增加错误处理
    try:
        df = pd.read_excel(filepath, skiprows=[0])
        df.rename(columns={
            "工号": "teacher_id", "姓名": "teacher_name", "单位": "department"
        }, inplace=True, errors='ignore') # errors='ignore' 避免因列不存在而报错
        # 检查关键列是否存在
        if "teacher_id" not in df.columns or "teacher_name" not in df.columns:
             raise ValueError("教师信息文件缺少 '工号' 或 '姓名' 列。")
        return df
    except FileNotFoundError:
        print(f"错误：找不到文件 {filepath}")
        raise
    except Exception as e:
        print(f"加载教师信息时出错: {e}")
        raise

def load_class_info(filepath: str) -> pd.DataFrame:
    """示例：读取班级信息的 Excel 文件。"""
    print(f"Loading class info from: {filepath}")
    try:
        df = pd.read_excel(filepath, skiprows=[0])
        df.rename(columns={
            "班级编号": "class_id", "班级名称": "class_name", "班级人数": "student_count",
            "专业编号": "major_id", "专业方向": "major_direction", "固定教室": "fixed_room"
        }, inplace=True, errors='ignore')
        if "class_name" not in df.columns or "student_count" not in df.columns:
            raise ValueError("班级数据文件缺少 '班级名称' 或 '班级人数' 列。")
        # 确保 student_count 是数值类型
        df['student_count'] = pd.to_numeric(df['student_count'], errors='coerce').fillna(0).astype(int)
        return df
    except FileNotFoundError:
        print(f"错误：找不到文件 {filepath}")
        raise
    except Exception as e:
        print(f"加载班级数据时出错: {e}")
        raise

def load_room_info(filepath: str) -> pd.DataFrame:
    """示例：读取教室信息的 Excel 文件。"""
    print(f"Loading room info from: {filepath}")
    try:
        df = pd.read_excel(filepath, skiprows=[0])
        df.rename(columns={
            "教室编号": "room_id", "教室名称": "room_name",
            "最大上课容纳人数": "capacity", "教室类型": "room_type"
        }, inplace=True, errors='ignore')
        if "room_id" not in df.columns or "capacity" not in df.columns or "room_type" not in df.columns:
             raise ValueError("教室信息文件缺少 '教室编号', '最大上课容纳人数', 或 '教室类型' 列。")
        # 确保 capacity 是数值类型
        df['capacity'] = pd.to_numeric(df['capacity'], errors='coerce').fillna(0).astype(int)
        return df
    except FileNotFoundError:
        print(f"错误：找不到文件 {filepath}")
        raise
    except Exception as e:
        print(f"加载教室信息时出错: {e}")
        raise

def load_task_info(filepath: str) -> pd.DataFrame:
    """示例：读取排课任务信息。"""
    print(f"Loading task info from: {filepath}")
    try:
        df = pd.read_excel(filepath)
        df.rename(columns={
            "课程编号": "course_id", "课程名称": "course_name", "课程性质": "course_type",
            "任课教师": "teacher_name", "教学班组成": "class_list_str",
            "指定教室类型": "required_room_type"
        }, inplace=True, errors='ignore')
        if "course_id" not in df.columns or "teacher_name" not in df.columns or "class_list_str" not in df.columns:
             raise ValueError("排课任务文件缺少 '课程编号', '任课教师', 或 '教学班组成' 列。")
        return df
    except FileNotFoundError:
        print(f"错误：找不到文件 {filepath}")
        raise
    except Exception as e:
        print(f"加载排课任务时出错: {e}")
        raise

# ===================== 2. 数据预处理函数 (周学时 + 放宽类型 + 容量预检 + 指定教室) =====================
import re # 确保 re 已导入
import math # 用于处理 NaN

def preprocess_tasks(df_tasks: pd.DataFrame,
                     df_classes: pd.DataFrame,
                     df_teachers: pd.DataFrame,
                     df_rooms: pd.DataFrame) -> list: # <-- 添加 df_rooms 作为输入
    """
    预处理任务数据。
    修改点：
    1. 解析 '开课周次 学时' 获取每周学时 H。
    2. 根据每周学时 H 和 '连排节次' C 拆分任务。
    3. 忽略 '指定教室类型' (required_room_type = None)。
    4. 处理“全体教学班必修”。
    5. 新增：预先检查任务人数是否超过全局最大教室容量，超过则跳过。
    6. 新增：读取并传递 '指定教室' 信息。
    """
    print("Preprocessing tasks (Weekly hours, Relaxed type, Capacity pre-check, Fixed room)...")
    final_sub_tasks = []
    original_task_counter = 0
    sub_task_id_counter = 0
    missing_teachers = set()
    missing_classes_in_specific_tasks = set()
    skipped_tasks_capacity = 0 # 记录因容量超限跳过的原始任务数

    # --- 数据准备 ---
    if "teacher_id" not in df_teachers.columns or "teacher_name" not in df_teachers.columns:
        raise ValueError("教师信息文件缺少 'teacher_id' 或 'teacher_name' 列")
    teacher_name_to_id = pd.Series(df_teachers.teacher_id.values, index=df_teachers.teacher_name).to_dict()

    if "class_name" not in df_classes.columns or "student_count" not in df_classes.columns:
         raise ValueError("班级数据文件缺少 'class_name' 或 'student_count' 列")
    df_classes['student_count'] = pd.to_numeric(df_classes['student_count'], errors='coerce').fillna(0).astype(int)
    class_name_to_students = pd.Series(df_classes.student_count.values, index=df_classes.class_name).to_dict()
    all_class_names_list = df_classes["class_name"].tolist()
    print(f"Total number of unique classes found: {len(all_class_names_list)}")

    # 获取全局最大教室容量
    if df_rooms.empty or 'capacity' not in df_rooms.columns:
         print("Warning: Room data is empty or missing 'capacity' column. Cannot perform capacity pre-check.")
         max_overall_capacity = float('inf') # 无法检查，假设容量无限
    else:
         df_rooms['capacity'] = pd.to_numeric(df_rooms['capacity'], errors='coerce').fillna(0)
         max_overall_capacity = df_rooms['capacity'].max()
         if max_overall_capacity <= 0:
              print("Warning: Maximum room capacity found is 0 or less. All tasks requiring capacity will fail.")
         print(f"Maximum room capacity found across all rooms: {max_overall_capacity}")
    # --- 结束准备 ---

    # --- 检查并处理所需列 ---
    # 确保 '指定教室' 列存在，如果不存在则添加一个空列
    if '指定教室' not in df_tasks.columns:
        print("Warning: Column '指定教室' not found in 排课任务.xlsx. Assuming no fixed rooms.")
        df_tasks['指定教室'] = None # 或者 np.nan

    required_task_cols = ["course_type", "开课周次学时", "连排节次", "teacher_name", "class_list_str", "course_id", "course_name", "指定教室"]
    default_weekly_hours_str = '1-1:1' # 默认周学时格式和值

    for col in required_task_cols:
         if col not in df_tasks.columns:
              if col == "开课周次学时":
                   print(f"Warning: Column '开课周次学时' not found. Using default: {default_weekly_hours_str}")
                   df_tasks[col] = default_weekly_hours_str
              elif col == "连排节次":
                   print(f"Warning: Column '连排节次' not found. Assuming 1.")
                   df_tasks[col] = 1
              # 指定教室列已处理
              elif col != '指定教室':
                   raise ValueError(f"排课任务文件缺少必需列: '{col}'")

    df_tasks['连排节次'] = pd.to_numeric(df_tasks['连排节次'], errors='coerce').fillna(1).astype(int)
    df_tasks['连排节次'] = df_tasks['连排节次'].apply(lambda x: max(1, x))
    # --- 结束检查处理列 ---

    # --- 过滤任务 ---
    if "course_type" not in df_tasks.columns: raise ValueError("排课任务文件缺少 'course_type' 列")
    df_tasks_filtered = df_tasks[df_tasks["course_type"] == "必修课"].copy()
    print(f"Filtered {len(df_tasks_filtered)} initial mandatory tasks based on course_type '必修课'.")
    # --- 结束过滤 ---

    # --- 迭代原始任务并拆分 ---
    print("Processing, splitting by weekly hours, creating sub-tasks, and pre-checking capacity:")
    for index, row in tqdm(df_tasks_filtered.iterrows(), total=len(df_tasks_filtered), desc="Preprocessing Tasks"):
        original_task_counter += 1
        original_task_ref = f"orig_{index}"

        # --- 获取基本信息 ---
        c_id = row.get("course_id", f"UNKNOWN_{original_task_ref}")
        c_name = row.get("course_name", "Unknown")
        t_name = row.get("teacher_name", "").strip()
        course_type = row.get("course_type")

        # 解析周学时
        weekly_hours_str = str(row.get("开课周次学时", default_weekly_hours_str)).strip()
        weekly_periods = 1 # 默认值
        match_hours = re.search(r':(\d+)$', weekly_hours_str) # 查找末尾的 :H
        if match_hours:
            try:
                weekly_periods = int(match_hours.group(1))
                if weekly_periods <= 0: weekly_periods = 1
            except ValueError: weekly_periods = 1
        # print(f"  Task {c_name}: Raw weekly hours str='{weekly_hours_str}', Parsed weekly_periods={weekly_periods}") # Debug Print

        # 获取连排要求
        consecutive_periods = int(row.get('连排节次', 1))
        if consecutive_periods <= 0: consecutive_periods = 1
        if consecutive_periods > weekly_periods:
             consecutive_periods = weekly_periods # 连排不能超过周总学时

        # 放宽教室类型，并读取指定教室
        required_type = None
        fixed_room_id_raw = row.get("指定教室")
        # 处理可能的 NaN 或 None 值，并去除空白
        fixed_room_id = str(fixed_room_id_raw).strip() if pd.notna(fixed_room_id_raw) and str(fixed_room_id_raw).strip() else None
        # --- 结束获取基本信息 ---

        # --- 匹配教师 ---
        teacher_id = teacher_name_to_id.get(t_name)
        if teacher_id is None:
            if t_name not in missing_teachers: missing_teachers.add(t_name)
            continue
        # --- 结束匹配教师 ---

        # --- 判断是全体班级还是指定班级 ---
        class_list_str_raw = row.get("class_list_str")
        is_empty_or_nan = pd.isna(class_list_str_raw) or (isinstance(class_list_str_raw, str) and not class_list_str_raw.strip())
        task_groups_to_process = []

        if course_type == "必修课" and is_empty_or_nan:
            # --- 情况 A: 全体教学班必修 -> 为每个班级生成一个处理组 ---
            for class_name in all_class_names_list:
                student_count = class_name_to_students.get(class_name)
                if student_count is not None and student_count > 0:
                    task_groups_to_process.append({ "class_list": [class_name], "total_students": student_count, "group_ref": class_name })
        elif not is_empty_or_nan:
            # --- 情况 B: 处理指定班级列表 ---
            class_list_str = str(class_list_str_raw).strip()
            class_list_raw = [cl.strip() for cl in class_list_str.split(',') if cl.strip()]
            if class_list_raw:
                total_students = 0
                valid_class_list = []
                task_missing_classes = False
                for cl in class_list_raw:
                    student_count = class_name_to_students.get(cl)
                    if student_count is not None:
                         if student_count > 0:
                            total_students += student_count
                            valid_class_list.append(cl)
                    else:
                        if cl not in missing_classes_in_specific_tasks: missing_classes_in_specific_tasks.add(cl)
                        task_missing_classes = True
                if not task_missing_classes and valid_class_list and total_students > 0:
                    task_groups_to_process.append({ "class_list": valid_class_list, "total_students": total_students, "group_ref": "_".join(sorted(valid_class_list)) })
            # --- 结束情况 B ---

        # --- 容量预检并为每个有效班级组生成每周子任务 ---
        for group_info in task_groups_to_process:
            group_ref = group_info["group_ref"]
            required_students = group_info["total_students"]

            # *** 新增：容量预检 ***
            if required_students > max_overall_capacity:
                print(f"  SKIPPING Task Group: Course '{c_name}', Group '{group_ref}' requires {required_students} students, but max room capacity is {max_overall_capacity}.")
                skipped_tasks_capacity += 1
                continue # 跳过这个班级组，不生成子任务

            # 为每周需要的 H 个学时创建子任务
            for i in range(weekly_periods): # weekly_periods = H
                final_sub_tasks.append({
                    "sub_task_id": sub_task_id_counter,
                    "original_task_ref": f"{original_task_ref}_{group_ref}",
                    "sub_task_index": i,
                    "total_weekly_duration": weekly_periods,
                    "required_consecutive": consecutive_periods,
                    "course_id": c_id,
                    "course_name": c_name,
                    "teacher_id": teacher_id,
                    "class_list": group_info["class_list"],
                    "total_students": required_students,
                    "required_room_type": required_type, # Is None now
                    "fixed_room_id": fixed_room_id # 传递指定教室信息
                })
                sub_task_id_counter += 1
        # --- 结束子任务生成 ---

    # --- 结束主循环 ---

    if missing_teachers: print(f"\nWarning Summary: Skipped tasks for teachers not found: {missing_teachers}")
    if missing_classes_in_specific_tasks: print(f"\nWarning Summary: Skipped tasks involving specific classes not found: {missing_classes_in_specific_tasks}")
    if skipped_tasks_capacity > 0: print(f"\nWarning Summary: Skipped {skipped_tasks_capacity} task groups because their student count exceeds the max capacity of any room.")

    print(f"\nPreprocessing finished. Generated {len(final_sub_tasks)} individual single-period sub-tasks representing weekly requirements (after capacity pre-check).")
    return final_sub_tasks
# ===================== 3. 构建CP模型 (周学时+放宽类型+容量预检+指定教室+连排) =====================
def build_cp_model(sub_tasks_preprocessed: list,
                   df_rooms: pd.DataFrame,
                   df_teachers: pd.DataFrame,
                   df_classes: pd.DataFrame):
    """
    构建OR-Tools CP-SAT模型。
    修改点：
    1. 使用基于周学时拆分的子任务。
    2. 创建变量时结合 指定教室 和 容量 进行预剪枝 (忽略类型)。
    3. 包含处理连排子任务组的约束。
    """
    print("Building CP-SAT model (Weekly sub-tasks, Relaxed type, Capacity filter, Fixed room, Consecutive constraints)...")
    model = cp_model.CpModel()

    # --- 1. 基础数据准备 ---
    time_slots = [(d, p) for d in range(5) for p in range(8)]
    time_slot_indices = list(range(len(time_slots)))
    num_time_slots = len(time_slots)
    teacher_list = df_teachers["teacher_id"].unique().tolist()
    room_list = df_rooms["room_id"].tolist() # 使用 tolist() 获取列表
    if not room_list: raise ValueError("教室列表为空!")
    room_capacity = pd.Series(df_rooms.capacity.values, index=df_rooms.room_id).to_dict()
    # room_type 不再需要
    # --- 结束基础数据准备 ---

    # --- 2. 按原始任务分组子任务 ---
    sub_tasks_by_original = defaultdict(list)
    for sub_task in sub_tasks_preprocessed:
        sub_tasks_by_original[sub_task['original_task_ref']].append(sub_task)
    for ref in sub_tasks_by_original:
        sub_tasks_by_original[ref].sort(key=lambda x: x['sub_task_index'])
    # --- 结束分组 ---

    # --- 3. 构造核心变量 x[sub_task_id, time_idx, room_id] (结合指定教室和容量剪枝) ---
    print("Creating boolean assignment variables (Pruning by Fixed Room & Capacity)...")
    x_vars = {}
    sub_tasks_with_no_valid_assignment = set() # 记录无法安排的子任务

    for sub_task in tqdm(sub_tasks_preprocessed, desc="Creating Variables"):
        st_id = sub_task["sub_task_id"]
        required_students = sub_task["total_students"]
        fixed_room_id = sub_task.get("fixed_room_id") # 获取指定教室
        possible_rooms_for_subtask = []

        if fixed_room_id and fixed_room_id in room_capacity: # 如果指定了教室且该教室存在
            if room_capacity[fixed_room_id] >= required_students:
                possible_rooms_for_subtask = [fixed_room_id] # 只考虑这个指定教室
            else:
                # 指定教室容量不足，此子任务无法安排
                sub_tasks_with_no_valid_assignment.add(st_id)
                # print(f"Warning: Fixed room {fixed_room_id} capacity insufficient for sub_task {st_id} (Students: {required_students}).")
                continue # 跳过变量创建
        elif fixed_room_id: # 指定了教室但教室信息不存在
             sub_tasks_with_no_valid_assignment.add(st_id)
             # print(f"Warning: Fixed room {fixed_room_id} for sub_task {st_id} not found in room data.")
             continue # 跳过变量创建
        else: # 没有指定教室，考虑所有容量足够的教室
            possible_rooms_for_subtask = [r_id for r_id in room_list if room_capacity.get(r_id, 0) >= required_students]

        if not possible_rooms_for_subtask:
            # 无论是否指定，都找不到容量足够的教室
            sub_tasks_with_no_valid_assignment.add(st_id)
            # print(f"Warning: No rooms with sufficient capacity found for sub_task {st_id} (Students: {required_students}).")
            continue # 跳过变量创建

        # 为所有可能的 (时间, 可能教室) 组合创建变量
        for ts_idx in time_slot_indices:
            for r_id in possible_rooms_for_subtask:
                var_name = f"x_{st_id}_{ts_idx}_{r_id}"
                x_vars[(st_id, ts_idx, r_id)] = model.NewBoolVar(var_name)

    if sub_tasks_with_no_valid_assignment:
         print(f"\nWarning Summary: {len(sub_tasks_with_no_valid_assignment)} sub-tasks were skipped during variable creation due to missing/invalid fixed room or insufficient capacity in any available room.")
         print(f"Problematic sub-task IDs (first 10 skipped): {list(sub_tasks_with_no_valid_assignment)[:10]}")
    # --- 结束构造变量 ---


    # --- 4. 添加约束 ---
    print("Adding constraints...")
    # (H0 - Modified) 每个 *可安排的子任务* 必须恰好分配一次
    print("  - Adding ExactlyOne constraint for each schedulable sub-task...")
    scheduled_subtask_count = 0
    for sub_task in sub_tasks_preprocessed:
        st_id = sub_task["sub_task_id"]
        if st_id in sub_tasks_with_no_valid_assignment: continue # 跳过无法安排的

        possible_assignments = [ var for key, var in x_vars.items() if key[0] == st_id ]
        if possible_assignments:
             model.AddExactlyOne(possible_assignments)
             scheduled_subtask_count += 1
        else:
             # 这理论上不应发生，因为我们在上面已经 continue 了
             print(f"Internal Error: Schedulable sub-task {st_id} has no assignment variables!")
             model.Add(cp_model.FALSE)
    print(f"  - ExactlyOne constraints added for {scheduled_subtask_count} sub-tasks.")


    # (H1) 教师时间唯一性
    print("  - Adding Teacher conflict constraints...")
    teacher_time_assignments = defaultdict(list)
    for st_id, ts_idx, r_id in x_vars.keys(): # Iterate through created variables only
        # Find the subtask object (maybe create a lookup dict first for efficiency)
        sub_task = next((st for st in sub_tasks_preprocessed if st['sub_task_id'] == st_id), None)
        if sub_task:
             teacher_id = sub_task["teacher_id"]
             teacher_time_assignments[(teacher_id, ts_idx)].append(x_vars[(st_id, ts_idx, r_id)])
    for key, vars_list in teacher_time_assignments.items():
        if len(vars_list) > 1: model.AddAtMostOne(vars_list)


    # (H2) 教室时间唯一性
    print("  - Adding Room conflict constraints...")
    room_time_assignments = defaultdict(list)
    for key, var in x_vars.items():
        st_id, ts_idx, r_id = key
        room_time_assignments[(r_id, ts_idx)].append(var)
    for key, vars_list in room_time_assignments.items():
        if len(vars_list) > 1: model.AddAtMostOne(vars_list)


    # (H3) 班级时间唯一性
    print("  - Adding Class conflict constraints...")
    class_time_assignments = defaultdict(list)
    sub_task_lookup = {st['sub_task_id']: st for st in sub_tasks_preprocessed} # Create lookup
    for key, var in x_vars.items():
        st_id, ts_idx, r_id = key
        sub_task = sub_task_lookup.get(st_id)
        if sub_task:
            for class_name in sub_task.get("class_list", []):
                 if isinstance(class_name, str) and class_name:
                    class_time_assignments[(class_name, ts_idx)].append(var)
    for key, vars_list in class_time_assignments.items():
        if len(vars_list) > 1: model.AddAtMostOne(vars_list)


    # (H4 & H5) 容量和类型约束 (容量由变量剪枝保证，类型被忽略)


    # (H6) 连排约束 (逻辑不变，但作用于剪枝后的变量)
    print("  - Adding Consecutive constraints for sub-tasks...")
    consecutive_groups_processed = 0
    # ... (分组、创建 start_time_var, room_bool_vars, 通道约束的逻辑不变) ...
    # !!! 注意: 这里的逻辑需要确保它只考虑那些变量实际被创建了的子任务和房间 !!!
    # 例如，在创建 room_bool_vars 时，只为那些对组内所有子任务都容量足够的房间创建
    # 在添加通道约束时，使用 if (st_id, t, r_id) in x_vars: 检查

    for original_ref, sub_task_list in sub_tasks_by_original.items():
        # 检查组内是否有任务无法安排
        if any(st['sub_task_id'] in sub_tasks_with_no_valid_assignment for st in sub_task_list):
            # print(f"Skipping consecutive constraint for {original_ref} due to unassignable sub-tasks.")
            continue

        if not sub_task_list: continue
        required_consecutive = sub_task_list[0]['required_consecutive']
        total_duration = sub_task_list[0]['total_weekly_duration'] # 使用新字段名

        if required_consecutive > 1 and total_duration > 1:
            consecutive_groups_processed += 1
            C = required_consecutive
            if C != total_duration: C = total_duration # 简化

            max_start_time = num_time_slots - C
            if max_start_time < 0:
                 print(f"Error: Required consecutive periods ({C}) for {original_ref} exceeds total time slots ({num_time_slots}). Forcing infeasibility.")
                 model.Add(cp_model.FALSE); continue
            start_time_var = model.NewIntVar(0, max_start_time, f'start_{original_ref}')

            # 找到组的有效公共教室 (只基于容量)
            common_valid_rooms = set(room_list)
            possible_group = True
            for sub_task in sub_task_list[:C]: # 检查连排块内的子任务
                 st_id = sub_task['sub_task_id']
                 required_students = sub_task['total_students']
                 current_valid = set(r for r in room_list if room_capacity.get(r,0) >= required_students)
                 common_valid_rooms.intersection_update(current_valid)
                 if not common_valid_rooms: # 如果交集为空，则不可能连排
                      possible_group = False; break
            if not possible_group or not common_valid_rooms:
                 print(f"Error: No common valid rooms (capacity only) found for consecutive group {original_ref}. Forcing infeasibility.")
                 model.Add(cp_model.FALSE); continue
            valid_rooms_for_group = list(common_valid_rooms)

            # 检查指定教室（如果组内所有子任务指定了同一个教室）
            fixed_room_for_group = None
            first_fixed = sub_task_list[0].get('fixed_room_id')
            if first_fixed and all(st.get('fixed_room_id') == first_fixed for st in sub_task_list[:C]):
                 if first_fixed in valid_rooms_for_group: # 确保指定教室容量足够
                      fixed_room_for_group = first_fixed
                      valid_rooms_for_group = [first_fixed] # 强制只能用这个房间
                 else:
                      print(f"Error: Fixed room {first_fixed} for group {original_ref} lacks capacity. Forcing infeasibility.")
                      model.Add(cp_model.FALSE); continue

            room_bool_vars = {r_id: model.NewBoolVar(f'room_{original_ref}_{r_id}') for r_id in valid_rooms_for_group}
            model.AddExactlyOne(room_bool_vars.values())

            # 添加通道约束
            for i in range(C):
                sub_task = sub_task_list[i]
                st_id = sub_task['sub_task_id']
                # 检查每个可能的 (t, r) 组合是否创建了变量
                for t in range(i, max_start_time + i + 1): # 优化时间范围
                    possible_start = t - i
                    if 0 <= possible_start <= max_start_time:
                        for r_id in valid_rooms_for_group:
                            if (st_id, t, r_id) in x_vars: # 只为存在的变量添加约束
                                # If x=1 => start=t-i and room=r
                                model.Add(start_time_var == possible_start).OnlyEnforceIf(x_vars[(st_id, t, r_id)])
                                model.Add(room_bool_vars[r_id] == 1).OnlyEnforceIf(x_vars[(st_id, t, r_id)])

                                # If start=t-i and room=r => x=1 (反向约束，确保 x 被设置)
                                # 使用 Reification (更推荐的方式)
                                b_start = model.NewBoolVar('')
                                model.Add(start_time_var == possible_start).OnlyEnforceIf(b_start)
                                model.Add(start_time_var != possible_start).OnlyEnforceIf(b_start.Not())

                                b_room = room_bool_vars[r_id] # 直接使用房间选择变量

                                # b_cond = b_start AND b_room
                                b_cond = model.NewBoolVar('')
                                model.AddBoolOr([b_start.Not(), b_room.Not(), b_cond]) # if b_start and b_room then b_cond
                                model.AddImplication(b_cond, b_start) # if b_cond then b_start
                                model.AddImplication(b_cond, b_room)  # if b_cond then b_room

                                model.AddImplication(b_cond, x_vars[(st_id, t, r_id)])

    print(f"  - Added consecutive constraints for {consecutive_groups_processed} groups.")
    # --- 结束连排约束 ---

    # --- 5. 目标函数 ---
    # model.Maximize(0)
    # --- 结束目标函数 ---

    print("Model building complete.")
    meta_data = { "sub_tasks": sub_tasks_preprocessed, "time_slots": time_slots, "room_list": room_list }
    return model, x_vars, meta_data
# ===================== 7. 主函数 (CP-SAT 专用) =====================
def run_cp_sat_scheduler():
    """使用 CP-SAT 进行排课的主流程 (已添加修正计时)"""
    print("--- Starting CP-SAT Scheduler ---")
    start_total_time = time.time() # 全局开始时间

    # --- 文件路径 ---
    teacher_file = "教师信息.xlsx"
    class_file = "班级数据.xls"
    room_file = "教室信息.xls"
    task_file = "排课任务.xlsx"
    output_file = "课程表方案_CP_SAT.xlsx" # 输出文件名

    # --- 1. 数据加载 ---
    print("\n--- Step 1: Loading Data ---")
    load_start = time.time()
    try:
        df_teachers = load_teacher_info(teacher_file)
        df_classes = load_class_info(class_file)
        df_rooms = load_room_info(room_file)
        df_tasks = load_task_info(task_file)
        if df_rooms.empty or df_teachers.empty or df_classes.empty or df_tasks.empty:
             print("错误：一个或多个输入数据文件为空或加载失败。")
             return None
    except Exception as e:
        print(f"数据加载过程中出错: {e}")
        return None
    load_end = time.time()
    print(f"Data Loading completed in {load_end - load_start:.2f} seconds.")

    # --- 2. 预处理 ---
    print("\n--- Step 2: Preprocessing Tasks ---")
    preprocess_start = time.time()
    try:
        # !!! 重要: 确保 preprocess_tasks 函数已按需修改 !!!
        # (例如，处理“全体班级必修”的情况)
        tasks_preprocessed = preprocess_tasks(df_tasks, df_classes, df_teachers, df_rooms) # <<< 添加 df_rooms

        if not tasks_preprocessed:
            print("错误：预处理后没有生成任何有效的排课任务。请检查输入数据和过滤/处理逻辑。")
            return None
    except Exception as e:
        print(f"任务预处理过程中出错: {e}")
        return None
    preprocess_end = time.time()
    print(f"Task Preprocessing completed in {preprocess_end - preprocess_start:.2f} seconds.")

    # --- 3. 构建 CP 模型 ---
    print("\n--- Step 3: Building CP-SAT Model ---")
    build_start = time.time()
    try:
        # 定义 model, x_vars, meta_data
        model, x_vars, meta_data = build_cp_model(tasks_preprocessed, df_rooms, df_teachers, df_classes)
    except Exception as e:
        print(f"构建 CP 模型时出错: {e}")
        return None
    build_end = time.time()
    print(f"Model Building completed in {build_end - build_start:.2f} seconds.")

    # --- 4. 求解 ---
    print("\n--- Step 4: Solving the Model ---")
    # 在这里定义 solver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 1000# 例如 5 分钟超时
    solver.parameters.num_search_workers = 8     # 使用多核并行求解 (根据你的 CPU 调整)
    solver.parameters.log_search_progress = True # 显示求解日志

    solve_start_time = time.time()
    try:
        status = solver.Solve(model) # 调用 Solve
    except Exception as e:
        print(f"调用 solver.Solve 时发生错误: {e}")
        return None # 求解出错，无法继续
    solve_end_time = time.time()
    # 确保在调用 solver.WallTime() 或 solver.StatusName() 之前 solver 已定义且 Solve 已调用
    print(f"Solving attempt finished in {solve_end_time - solve_start_time:.2f} seconds (Solver Wall Time: {solver.WallTime():.2f}s).")

    # --- 5. 处理结果 ---
    print("\n--- Step 5: Processing Results ---")
    process_start = time.time()
    # 在这里定义 result_data
    result_data = {"status": solver.StatusName()} # 获取求解状态
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"Solution found! Status: {solver.StatusName()}")
        print(f"Objective value (if any): {solver.ObjectiveValue()}") # Objective 可能未定义或为0
        # 提取解
        solution_list = extract_solution(solver, x_vars, meta_data)

        if solution_list:
            # 保存到 Excel
            try:
                df_solution = pd.DataFrame(solution_list)
                df_solution.to_excel(output_file, index=False)
                print(f"Solution successfully saved to {output_file}")
                result_data["output_file"] = output_file
                # result_data["solution_df"] = df_solution # 可选：如果后续需要处理 DataFrame
            except Exception as e:
                print(f"Error saving solution to Excel: {e}")
                result_data["status"] = "ERROR_SAVING_SOLUTION" # 更新状态
        else:
            print("Error: Solver reported a solution, but extraction failed or returned empty list.")
            result_data["status"] = "ERROR_EXTRACTING_SOLUTION" # 更新状态

    elif status == cp_model.INFEASIBLE:
        print("Solver proved the model has no feasible solution.")
        print("This means, given the current data and constraints, it's impossible to schedule all tasks without violating rules.")
        print("Consider relaxing some constraints or checking data (especially after potential preprocessing changes).")
    elif status == cp_model.MODEL_INVALID:
        print("Error: The CP-SAT model is invalid. Check the constraint building logic in 'build_cp_model'.")
    else:
        print(f"Solver finished with status: {solver.StatusName()}. No feasible solution found within the time limit or due to other issues.")

    process_end = time.time()
    print(f"Result Processing completed in {process_end - process_start:.2f} seconds.")

    end_total_time = time.time()
    print(f"\nTotal script execution time: {end_total_time - start_total_time:.2f} seconds.")

    # 确保返回定义好的 result_data
    return result_data


# --- 主程序入口 ---
if __name__ == "__main__":
    print("========================================")
    print(" Starting Course Scheduling using CP-SAT")
    print("========================================")
    # 运行主调度函数
    final_result = run_cp_sat_scheduler()

    print("\n--- Final Summary ---")
    if final_result:
        print(f"Final Status: {final_result.get('status', 'N/A')}")
        if "output_file" in final_result:
            print(f"Output File: {final_result.get('output_file')}")
            print("\nNext Step: Use Check.py to verify the generated Excel file.")
        elif final_result.get('status') == 'INFEASIBLE':
             print("The problem seems infeasible with the current constraints.")
        else:
             print("Scheduler finished, but may not have produced a valid output file. Check logs above.")
    else:
        print("Scheduler script failed to run completely. Check error messages above.")
    print("========================================")


