# ==============================================================================
# 算法1.py - 完整最终代码 (CP-SAT 区间变量, JSON规则驱动, 最小化超员)
# 版本: v_final_json
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
import json # 导入 json 模块

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
        if df['teacher_id'].duplicated().any(): print("Warning: Duplicate teacher_id found!")
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
        # 清理固定教室名称
        if 'fixed_room' in df.columns: df['fixed_room'] = df['fixed_room'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() else None)
        df.dropna(subset=['class_name'], inplace=True)
        if df['class_name'].duplicated().any(): print("Warning: Duplicate class_name found!")
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
        # 检查重复并警告
        if df['room_id'].duplicated().any(): print("Warning: Duplicate room_id found! Ensure IDs are unique.")
        if df['room_name'].duplicated().any(): print("Warning: Duplicate room_name found! Name matching might be ambiguous.")
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

# ===================== 2. 数据预处理 (应用 JSON 规则 - 最终版) =====================
def preprocess_tasks(df_tasks: pd.DataFrame,
                     df_classes: pd.DataFrame,
                     df_teachers: pd.DataFrame,
                     df_rooms: pd.DataFrame, # 仍然需要原始 df_rooms 用于某些检查
                     room_capacity_dict_by_name: dict, # 按名称索引的容量字典
                     max_overall_capacity: float,
                     class_name_to_fixed_room_name: dict, # 按名称索引的固定教室
                     rules: dict) -> list:
    """
    预处理任务数据，应用 JSON 规则，为区间变量模型准备 task units。
    """
    print("Preprocessing tasks (Applying JSON Rules - Final Version)...")
    task_units = []
    task_unit_id_counter = 0
    missing_teachers = set(); missing_classes_in_specific_tasks = set()
    skipped_tasks_fixed_room_conflict = 0
    skipped_by_forbidden_teacher = 0; skipped_by_forbidden_course = 0

    # --- 从 rules 中获取配置 ---
    basic_rules = rules.get('basic', {})
    apply_fixed_classroom = basic_rules.get('fixedClassroom', True) # 默认 True
    force_consecutive_rule = basic_rules.get('continuousHours', True) # 默认 True (C=H)
    time_rules_set = set(basic_rules.get('timeRules', []))
    sport_afternoon_only = 'sportAfternoon' in time_rules_set

    forbidden_rules = rules.get('forbidden', {})
    forbidden_teacher_ids = {str(tid).strip() for tid in forbidden_rules.get('teachers', [])}
    forbidden_course_ids = {str(cid).strip() for cid in forbidden_rules.get('courses', [])}
    print(f"Applying Rules: FixedClassroom={apply_fixed_classroom}, ForceConsecutive={force_consecutive_rule}, SportAfternoonOnly={sport_afternoon_only}")
    if forbidden_teacher_ids: print(f"  Forbidden Teacher IDs: {forbidden_teacher_ids}")
    if forbidden_course_ids: print(f"  Forbidden Course IDs: {forbidden_course_ids}")
    # --- 结束获取配置 ---

    # --- 数据准备 ---
    teacher_name_to_id = pd.Series(df_teachers.teacher_id.values, index=df_teachers.teacher_name).to_dict()
    class_name_to_students = pd.Series(df_classes.student_count.values, index=df_classes.class_name).to_dict()
    all_class_names_list = df_classes["class_name"].tolist()
    print(f"Total number of unique classes found: {len(all_class_names_list)}")
    print(f"Using pre-calculated max room capacity: {max_overall_capacity}")
    # --- 结束准备 ---

    # --- 检查列 ---
    if '指定教室' not in df_tasks.columns: df_tasks['指定教室'] = None
    if '开课周次学时' not in df_tasks.columns: df_tasks['开课周次学时'] = '1-1:1'
    if '连排节次' not in df_tasks.columns: df_tasks['连排节次'] = 1
    df_tasks['连排节次'] = pd.to_numeric(df_tasks['连排节次'], errors='coerce').fillna(1).astype(int).apply(lambda x: max(1, x))
    # --- 结束检查 ---

    # --- 过滤任务 ---
    df_tasks_filtered = df_tasks[df_tasks["课程性质"] == "必修课"].copy()
    initial_count = len(df_tasks_filtered)
    if forbidden_course_ids:
        df_tasks_filtered = df_tasks_filtered[~df_tasks_filtered['课程编号'].astype(str).isin(forbidden_course_ids)]
        skipped_by_forbidden_course = initial_count - len(df_tasks_filtered)
        initial_count = len(df_tasks_filtered)
    print(f"Filtered {len(df_tasks_filtered)} initial mandatory tasks after forbidden course check.")
    # --- 结束过滤 ---

    # --- 迭代原始任务 ---
    print("Processing original tasks, applying rules, creating task units:")
    for index, row in tqdm(df_tasks_filtered.iterrows(), total=len(df_tasks_filtered), desc="Preprocessing Tasks"):
        original_task_ref = f"orig_{index}"
        # --- 获取基本信息 ---
        c_id_raw = row.get("课程编号"); c_name = row.get("课程名称"); t_name = row.get("任课教师", "").strip(); course_type = row.get("课程性质")
        c_id = str(c_id_raw).strip() if pd.notna(c_id_raw) else f"UNKNOWN_{original_task_ref}"

        teacher_id = teacher_name_to_id.get(t_name) # 获取 ID
        # *** 修正语法错误 - 教师检查 ***
        if teacher_id is None:
            if t_name not in missing_teachers: missing_teachers.add(t_name)
            continue # 如果找不到老师，跳过此任务
        # *** 检查禁排教师 ***
        if teacher_id in forbidden_teacher_ids: skipped_by_forbidden_teacher += 1; continue

        # 解析周学时 H
        weekly_hours_str = str(row.get("开课周次学时", '1-1:1')).strip(); weekly_periods = 1 # H
        match_hours = re.search(r':(\d+)$', weekly_hours_str)
        # *** 修正语法错误 - 解析 duration (现在是 weekly_periods) ***
        if match_hours:
            try: weekly_periods = max(1, int(match_hours.group(1)))
            except ValueError: weekly_periods = 1

        # *** 根据 continuousHours 规则决定连排 C ***
        consecutive_periods = 1 # 默认不连排
        if force_consecutive_rule: # 如果规则要求强制连排
             consecutive_periods = weekly_periods # 则 C = H
        else: # 否则按 '连排节次' 列决定
             consecutive_periods = max(1, int(row.get('连排节次', 1)))
             consecutive_periods = min(consecutive_periods, weekly_periods) # C 不能大于 H

        required_type = None # 放宽类型
        task_fixed_room_name = str(row.get("指定教室")).strip() if pd.notna(row.get("指定教室")) and str(row.get("指定教室")).strip() else None
        # --- 结束获取 ---

        # --- !!! 需要逻辑来识别体育课和实验课 !!! ---
        is_pe_course = False # Placeholder
        is_lab_course = False # Placeholder
        # !!! 你需要根据实际数据填充这里的逻辑 !!!
        # Example: if "体育" in c_name or course_type == "体育": is_pe_course = True
        # --- 结束识别 ---

        # --- 判断班级情况并确定处理组 ---
        # ... (与上版本相同, 受 apply_fixed_classroom 控制) ...
        class_list_str_raw = row.get("教学班组成"); is_empty_or_nan = pd.isna(class_list_str_raw) or (isinstance(class_list_str_raw, str) and not class_list_str_raw.strip())
        task_groups_to_process = []
        if course_type == "必修课" and is_empty_or_nan:
            for class_name in all_class_names_list:
                student_count = class_name_to_students.get(class_name)
                if student_count is not None and student_count > 0:
                    final_fixed_room_name = None
                    if apply_fixed_classroom: class_fixed_room_name = class_name_to_fixed_room_name.get(class_name); final_fixed_room_name = task_fixed_room_name if task_fixed_room_name else class_fixed_room_name
                    task_groups_to_process.append({"class_list": [class_name], "total_students": student_count, "group_ref": class_name, "effective_fixed_room_name": final_fixed_room_name})
        elif not is_empty_or_nan:
            class_list_str = str(class_list_str_raw).strip(); class_list_raw = [cl.strip() for cl in class_list_str.split(',') if cl.strip()]
            if class_list_raw:
                total_students = 0; valid_class_list = []; task_missing_classes = False
                effective_fixed_room_name = task_fixed_room_name if apply_fixed_classroom else None
                first_class_fixed_room_name = None; fixed_room_conflict = False
                for cl in class_list_raw:
                    student_count = class_name_to_students.get(cl)
                    if student_count is not None:
                        if student_count > 0:
                            total_students += student_count; valid_class_list.append(cl)
                            if apply_fixed_classroom:
                                current_class_fixed_name = class_name_to_fixed_room_name.get(cl)
                                if current_class_fixed_name:
                                    if first_class_fixed_room_name is None: first_class_fixed_room_name = current_class_fixed_name
                                    elif first_class_fixed_room_name != current_class_fixed_name: fixed_room_conflict = True; break
                    else:
                        if cl not in missing_classes_in_specific_tasks: missing_classes_in_specific_tasks.add(cl); task_missing_classes = True
                if apply_fixed_classroom and fixed_room_conflict: skipped_tasks_fixed_room_conflict += 1; continue
                if apply_fixed_classroom and not effective_fixed_room_name and first_class_fixed_room_name: effective_fixed_room_name = first_class_fixed_room_name
                if not task_missing_classes and valid_class_list and total_students > 0:
                    task_groups_to_process.append({"class_list": valid_class_list, "total_students": total_students, "group_ref": "_".join(sorted(valid_class_list)), "effective_fixed_room_name": effective_fixed_room_name if apply_fixed_classroom else None})
        # --- 结束班级判断 ---

        # --- 生成 task unit (移除容量预检, 根据 H 和 C 拆分) ---
        for group_info in task_groups_to_process:
            group_ref = group_info["group_ref"]; required_students = group_info["total_students"]
            effective_fixed_room_name = group_info["effective_fixed_room_name"] # 可能是 None

            # *** 移除容量预检 ***

            # *** 根据 weekly_periods (H) 和 consecutive_periods (C) 生成单元 ***
            units_to_create = []
            block_idx_gen = 0
            # 确保 H 和 C 是有效的正整数
            H = weekly_periods
            C = consecutive_periods
            if C > H: C = H # 连排不能超过总时长

            if H <= 0: continue # 如果周学时为0，则不生成

            if C >= H: # 如果要求连排数等于或超过周学时，视为一个块
                 units_to_create.append({"duration": H, "block_index": 0})
            else: # H > C >= 1, 需要拆分
                 num_full_blocks = H // C
                 remaining_single = H % C
                 for _ in range(num_full_blocks):
                      if C > 0: units_to_create.append({"duration": C, "block_index": block_idx_gen}); block_idx_gen+=1
                 for _ in range(remaining_single):
                      units_to_create.append({"duration": 1, "block_index": block_idx_gen}); block_idx_gen+=1

            for unit_info in units_to_create:
                task_units.append({
                    "task_unit_id": task_unit_id_counter,
                    "original_task_ref": f"{original_task_ref}_{group_ref}",
                    "block_index": unit_info["block_index"],
                    "duration": unit_info["duration"], # 使用单元的时长
                    # "required_consecutive": unit_info["consecutive"], # 模型只关心 duration
                    "course_id": c_id, "course_name": c_name, "teacher_id": teacher_id,
                    "class_list": group_info["class_list"], "total_students": required_students,
                    "required_room_type": required_type, # None
                    "fixed_room_name": effective_fixed_room_name, # 传递名称或 None
                    "is_pe_course": is_pe_course, # 传递类型标志
                    "is_lab_course": is_lab_course # 传递类型标志
                })
                task_unit_id_counter += 1
            # --- 结束为单元生成字典 ---
        # --- 结束为班级组生成 ---
    # --- 结束主循环 ---

    # --- 打印警告 ---
    if missing_teachers: print(f"\nWarning Summary: Skipped tasks for teachers not found: {missing_teachers}")
    if missing_classes_in_specific_tasks: print(f"\nWarning Summary: Skipped tasks involving specific classes not found: {missing_classes_in_specific_tasks}")
    if skipped_tasks_fixed_room_conflict > 0: print(f"\nWarning Summary: Skipped {skipped_tasks_fixed_room_conflict} task groups due to conflicting/invalid fixed rooms.")
    if skipped_by_forbidden_teacher > 0: print(f"\nWarning Summary: Skipped {skipped_by_forbidden_teacher} tasks due to forbidden teacher.")
    if skipped_by_forbidden_course > 0: print(f"\nWarning Summary: Skipped {skipped_by_forbidden_course} tasks due to forbidden course.")

    print(f"\nPreprocessing finished. Generated {len(task_units)} weekly task units for scheduling based on JSON rules (capacity pre-check removed).")
    return task_units if task_units else None

# ===================== 3. 构建 CP 模型 (应用 JSON 规则 - 包含所有修正) =====================
def build_cp_model(task_units_preprocessed: list,
                   df_rooms: pd.DataFrame,
                   df_teachers: pd.DataFrame,
                   df_classes: pd.DataFrame,
                   room_capacity_dict_by_id: dict,
                   room_name_to_id_map: dict,
                   all_room_ids: list,
                   rules: dict):
    """
    构建使用区间变量的 CP-SAT 模型，应用 JSON 规则。
    目标：最小化教室容量的总超员人数。
    修正：teacher_name_to_id 定义, 教师负载约束中的 pass, meta_data 中加入 presence_literals_per_task
    """
    print("Building CP-SAT model (Applying JSON Rules - All Fixes)...")
    model = cp_model.CpModel()

    # --- 1. 基础数据准备 ---
    time_slots = [(d, p) for d in range(5) for p in range(8)]; num_time_slots = len(time_slots)
    if not all_room_ids: raise ValueError("教室 ID 列表为空!")
    basic_rules = rules.get('basic', {})
    apply_fixed_classroom = basic_rules.get('fixedClassroom', True)
    time_rules_set = set(basic_rules.get('timeRules', []))
    sport_afternoon_only = 'sportAfternoon' in time_rules_set
    teacher_limits_rule = {item['teacherId']: item['limits'] for item in rules.get('teacherLimits', [])}

    # *** 确保 teacher_name_to_id 和 id_to_name 在此作用域定义 ***
    if "teacher_id" not in df_teachers.columns or "teacher_name" not in df_teachers.columns: raise ValueError("教师信息缺少列")
    teacher_name_to_id = pd.Series(df_teachers.teacher_id.values, index=df_teachers.teacher_name).to_dict()
    teacher_id_to_name = {v:k for k,v in teacher_name_to_id.items()} # ID -> Name map

    print(f"Applying Rules: FixedClassroom={apply_fixed_classroom}, SportAfternoonOnly={sport_afternoon_only}")
    if teacher_limits_rule: print(f"  Teacher Limits Found for: {list(teacher_limits_rule.keys())}")
    # --- 结束基础数据准备 ---

    # --- 2. 按原始任务分组 (不变) ---
    task_units_by_original = defaultdict(list);
    for task_unit in task_units_preprocessed: task_units_by_original[task_unit['original_task_ref']].append(task_unit)
    # --- 结束分组 ---

    # --- 3. 构造变量 (应用规则剪枝) ---
    print("Creating interval variables (Applying rule-based pruning)...")
    all_intervals = defaultdict(dict) # key: (tu_id, room_id) -> interval_var
    presence_literals_per_task = defaultdict(list) # key: tu_id -> list of presence vars
    task_units_with_no_valid_assignment = set()
    all_overflow_vars = []
    max_possible_total_overflow = 0
    morning_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if p < 4}
    afternoon_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if p >= 4}

    for task_unit in tqdm(task_units_preprocessed, desc="Creating Variables"):
        try:
            tu_id = task_unit["task_unit_id"]; duration = task_unit["duration"]
            required_students = task_unit["total_students"]; teacher_id = task_unit["teacher_id"]
            fixed_room_name = task_unit.get("fixed_room_name") if apply_fixed_classroom else None # 应用规则
            is_pe_course = task_unit.get("is_pe_course", False)

            if duration <= 0 or duration > num_time_slots: task_units_with_no_valid_assignment.add(tu_id); continue

            possible_room_ids = []
            if fixed_room_name:
                fixed_room_id = room_name_to_id_map.get(fixed_room_name)
                if fixed_room_id and fixed_room_id in room_capacity_dict_by_id: possible_room_ids = [fixed_room_id]
                else: task_units_with_no_valid_assignment.add(tu_id); continue
            else: possible_room_ids = all_room_ids

            if not possible_room_ids: task_units_with_no_valid_assignment.add(tu_id); continue

            task_presences = []
            # --- 获取此教师的特定时间限制 ---
            teacher_limit = teacher_limits_rule.get(str(teacher_id)) # 使用 ID (转为 str 匹配 JSON key)
            teacher_name_for_lookup = teacher_id_to_name.get(teacher_id)
            if not teacher_limit and teacher_name_for_lookup: teacher_limit = teacher_limits_rule.get(teacher_name_for_lookup) # 尝试用名字
            teacher_allow_am = True; teacher_allow_pm = True
            if teacher_limit:
                 if teacher_limit.get('morning') == False: teacher_allow_am = False
                 if teacher_limit.get('afternoon') == False: teacher_allow_pm = False
            # --- 结束获取教师限制 ---

            for room_id in possible_room_ids: # 迭代可能的 Room ID
                room_cap = room_capacity_dict_by_id.get(room_id, 0) # 使用 ID 字典获取容量
                overflow_amount = max(0, required_students - room_cap)
                max_possible_total_overflow += overflow_amount

                # --- 时间剪枝 ---
                valid_starts = set(range(num_time_slots - duration + 1))
                # 1. 教师通用时间限制
                if not teacher_allow_am: valid_starts = {s for s in valid_starts if not any(s + i in morning_slots for i in range(duration))}
                if not teacher_allow_pm: valid_starts = {s for s in valid_starts if not any(s + i in afternoon_slots for i in range(duration))}
                # 2. 体育课时间限制
                if is_pe_course and sport_afternoon_only:
                     valid_starts = {s for s in valid_starts if all(s + i in afternoon_slots for i in range(duration))}
                if not valid_starts: continue # 如果没有有效的开始时间了
                start_domain = cp_model.Domain.FromValues(list(valid_starts))
                # --- 结束时间剪枝 ---

                # --- 创建变量 ---
                presence_var = model.NewBoolVar(f'presence_{tu_id}_{room_id}')
                start_var = model.NewIntVarFromDomain(start_domain, f'start_{tu_id}_{room_id}')
                interval_var = model.NewOptionalFixedSizeIntervalVar(start=start_var, size=duration, is_present=presence_var, name=f'interval_{tu_id}_{room_id}')
                all_intervals[(tu_id, room_id)] = interval_var
                task_presences.append(presence_var)
                # --- 创建超员变量 ---
                overflow_var = model.NewIntVar(0, overflow_amount, f'overflow_{tu_id}_{room_id}')
                model.Add(overflow_var == overflow_amount).OnlyEnforceIf(presence_var)
                model.Add(overflow_var == 0).OnlyEnforceIf(presence_var.Not())
                all_overflow_vars.append(overflow_var)

            if task_presences: presence_literals_per_task[tu_id] = task_presences
            else: task_units_with_no_valid_assignment.add(tu_id) # 因时间剪枝导致无选项

        except KeyError as e: print(f"\n>>> BUILD KeyError: {e} in task_unit: {task_unit}"); raise
        except Exception as e: print(f"\n>>> BUILD Error: {e} processing {task_unit}"); raise

    if task_units_with_no_valid_assignment: print(f"\nWarning Summary: {len(task_units_with_no_valid_assignment)} task units skipped (invalid fixed room or no valid time after pruning).")
    print(f"Created {len(all_intervals)} optional interval variables (unique task-room combos).")
    print(f"Created {len(all_overflow_vars)} overflow variables.")
    # --- 结束构造变量 ---

    # --- 4. 添加约束 ---
    print("Adding constraints...")
    # (H0) ExactlyOne Room
    print("  - Adding Task Assignment (ExactlyOne Room)..."); assigned_task_unit_count = 0
    for tu_id, presence_vars in presence_literals_per_task.items():
        if tu_id in task_units_with_no_valid_assignment: continue
        if presence_vars: model.AddExactlyOne(presence_vars); assigned_task_unit_count += 1
    print(f"  - ExactlyOne constraints added for {assigned_task_unit_count} task units.")

    # (H1, H2, H3) NoOverlap
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

    # *** (H_Load) 教师负载约束 (根据 JSON 规则动态添加 - 修正语法错误) ***
    print("  - Adding Teacher load constraints from rules...")
    active_limit_teachers = 0
    # 为每个 task unit 创建一个总的 presence 变量，并按老师分组
    teacher_weekly_load_vars = defaultdict(list)
    for tu_id, presence_vars in presence_literals_per_task.items():
        task_unit = task_unit_lookup.get(tu_id)
        if not task_unit: continue
        teacher_id = task_unit["teacher_id"]
        if presence_vars: # 只有当任务单元有有效的变量时才创建
            task_presence_var = model.NewBoolVar(f'task_present_{tu_id}')
            # 修正：任务存在当且仅当其在某个房间存在
            model.Add(sum(presence_vars) == 1).OnlyEnforceIf(task_presence_var)
            model.Add(sum(presence_vars) == 0).OnlyEnforceIf(task_presence_var.Not())
            # 也可以用 BoolsOR: model.AddBoolOr(presence_vars).OnlyEnforceIf(task_presence_var)
            # 和 model.AddImplication(task_presence_var, sum(presence_vars) >= 1) ? - 前者更直接
            teacher_weekly_load_vars[teacher_id].append(task_presence_var)

    # 现在应用负载约束
    for teacher_id_key, limits in teacher_limits_rule.items():
        teacher_id_target = None; teacher_id_str = str(teacher_id_key).strip()
        # 尝试作为 ID 查找 (确保 teacher_id 是字符串)
        if teacher_id_str in teacher_id_to_name: teacher_id_target = teacher_id_str
        # 如果 ID 找不到，尝试作为 Name
        elif teacher_id_str in teacher_name_to_id: teacher_id_target = teacher_name_to_id[teacher_id_str]

        if teacher_id_target is None: print(f"Warning: Cannot resolve teacher '{teacher_id_key}' from rules."); continue

        if teacher_id_target in teacher_weekly_load_vars:
            weekly_max = limits.get('weeklyMax')
            if weekly_max is not None:
                 model.Add(sum(teacher_weekly_load_vars[teacher_id_target]) <= weekly_max)
                 print(f"    - Weekly load constraint (<= {weekly_max} tasks) added for Teacher ID: {teacher_id_target}")
                 active_limit_teachers += 1 # 标记至少应用了一个限制

            # --- 添加日/上下午限制 (修正语法错误) ---
            daily_max = limits.get('dailyMax')
            am_max = limits.get('amMax') # 假设 JSON 中的 'amMax x' 是笔误
            pm_max = limits.get('pmMax')

            if daily_max is not None:
                print(f"    - NOTE: Daily Max constraint for teacher {teacher_id_target} NOT YET IMPLEMENTED.")
                pass # <<< 添加 pass
            if am_max is not None:
                print(f"    - NOTE: AM Max constraint for teacher {teacher_id_target} NOT YET IMPLEMENTED.")
                pass # <<< 添加 pass
            if pm_max is not None:
                print(f"    - NOTE: PM Max constraint for teacher {teacher_id_target} NOT YET IMPLEMENTED.")
                pass # <<< 添加 pass
            # --- 结束日/上下午限制 ---

    if active_limit_teachers == 0: print("    - No specific teacher load limits applied from rules (check teacher names/IDs in JSON).")
    # *** 结束教师负载约束 ***


    # --- 5. 设置优化目标：最小化总超员量 --- (不变)
    print("  - Setting Objective: Minimize Total Capacity Overflow...")
    if all_overflow_vars:
         safe_upper_bound = max(0, int(max_possible_total_overflow))
         if safe_upper_bound == 0 and all_overflow_vars:
             if any(hasattr(ov, 'Proto') and ov.Proto().domain and ov.Proto().domain[-1] > 0 for ov in all_overflow_vars): # 检查上限
                  safe_upper_bound = sum(tu['total_students'] for tu in task_units_preprocessed if 'total_students' in tu) # 修正求和
         total_overflow_var = model.NewIntVar(0, safe_upper_bound, 'total_overflow')
         model.Add(total_overflow_var == sum(all_overflow_vars))
         model.Minimize(total_overflow_var)
    else: print("    - No overflow variables created. No overflow objective added.")

    print("Model building complete.")
    # --- meta_data (修正) ---
    if 'room_id' in df_rooms.columns and 'room_name' in df_rooms.columns: room_id_to_name_map = pd.Series(df_rooms.room_name.values, index=df_rooms.room_id).to_dict()
    else: room_id_to_name_map = {}
    overflow_vars_dict = {}
    # 尝试更健壮地创建 overflow_vars_dict
    for (tu_id, room_id), interval in all_intervals.items():
        # 假设 overflow_var 的命名与 interval 变量相关或者能通过某种方式查找
        # 由于我们是按顺序添加到 all_overflow_vars 列表的，这个假设比较危险
        # 更好的方式是在创建 overflow_var 时就存入字典
        # 暂时保留之前的 zip 方式，但加上警告
        pass # zip 逻辑移到 return 前

    # 确保 overflow_vars_dict 正确创建
    temp_overflow_vars_list = all_overflow_vars[:]
    created_interval_keys = list(all_intervals.keys())
    if len(created_interval_keys) == len(temp_overflow_vars_list):
         overflow_vars_dict = dict(zip(created_interval_keys, temp_overflow_vars_list))
    else:
         print(f"CRITICAL Warning: Mismatch count intervals({len(created_interval_keys)}) / overflow vars({len(temp_overflow_vars_list)}). Overflow data invalid.")
         overflow_vars_dict = {} # 置空以避免后续错误

    meta_data = {
        "task_units": task_units_preprocessed, "time_slots": time_slots,
        "all_intervals": all_intervals,
        "overflow_vars": overflow_vars_dict, # <<< 使用修正后的字典
        "room_id_to_name": room_id_to_name_map,
        "presence_literals_per_task": presence_literals_per_task # <<< 确保已添加
    }
    return model, None, meta_data

# ===================== 4. 解读模型解 (不变) =====================
# (保持上次的 extract_solution 函数)
def extract_solution(solver: cp_model.CpSolver, x_vars: dict, meta_data: dict) -> list:
    """读取CP-SAT使用区间变量的解，并包含超员量信息。"""
    print("Extracting solution from Interval Variable model (with overflow)...")
    task_units = meta_data["task_units"]; time_slots = meta_data["time_slots"]
    all_intervals = meta_data["all_intervals"]; overflow_vars = meta_data.get("overflow_vars", {})
    room_id_to_name = meta_data.get("room_id_to_name", {}); solution = []
    presence_literals = meta_data.get('presence_literals_per_task', {}) # 获取

    if not task_units or solver.StatusName() not in ["OPTIMAL", "FEASIBLE"]: return []

    start_time_ext = time.time(); assigned_task_unit_count = 0; total_schedule_overflow = 0
    print("Extracting assignments and overflow (with progress):")
    task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units}
    processed_tu_ids = set() # 用于确保 overflow 只加一次

    for (tu_id, room_id), interval_var in tqdm(all_intervals.items(), desc="Extracting Solution"):
        presence_literal = interval_var.PresenceLiteral()
        if presence_literal is not None and solver.BooleanValue(presence_literal):
            task_unit = task_unit_lookup.get(tu_id);
            if not task_unit: continue
            start_idx = solver.Value(interval_var.StartExpr()); duration = task_unit["duration"]
            room_name = room_id_to_name.get(room_id, str(room_id));
            current_task_overflow = 0
            overflow_var = overflow_vars.get((tu_id, room_id))
            if overflow_var is not None:
                 try: current_task_overflow = solver.Value(overflow_var)
                 except Exception as e: print(f"Warning: Could not get overflow value for ({tu_id},{room_id}): {e}")

            # 只在首次遇到该任务单元的分配时累加 overflow 和计数
            if tu_id not in processed_tu_ids:
                total_schedule_overflow += current_task_overflow
                assigned_task_unit_count += 1
                processed_tu_ids.add(tu_id)

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
                        "student_overflow": current_task_overflow # 记录这个分配的超员量
                    })

    end_time_ext = time.time()
    num_tasks_in_model = len(presence_literals)
    print(f"Solution extraction complete. Extracted assignments for {assigned_task_unit_count} task units in {end_time_ext - start_time_ext:.2f} seconds.")
    print(f"Sum of Overflows for assigned tasks from extracted solution: {total_schedule_overflow}")
    if solver.StatusName() in ["OPTIMAL", "FEASIBLE"]: print(f"Solver Objective Value (min total overflow): {solver.ObjectiveValue()}")
    if assigned_task_unit_count != num_tasks_in_model: print(f"Warning: Assigned task units ({assigned_task_unit_count}) != task units in model ({num_tasks_in_model}).")

    return solution

# ===================== 7. 主函数 (CP-SAT + JSON 规则 - 包含定义) =====================
def run_cp_sat_scheduler():
    """使用 CP-SAT 进行排课的主流程 (读取 JSON 规则, 最小化超员)"""
    # --- 读取 JSON 规则 ---
    rules_file = "scheduling_rules.json" # 假设 JSON 文件名
    try:
        with open(rules_file, 'r', encoding='utf-8') as f:
            rules = json.load(f).get("schedulingRules", {})
        print(f"--- Loaded Scheduling Rules from {rules_file} ---")
    except FileNotFoundError:
        print(f"Error: Scheduling rules file '{rules_file}' not found. Using default behaviors.")
        rules = {} # 使用空字典，后续代码需要处理默认情况
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {rules_file}: {e}. Using default behaviors.")
        rules = {}
    except Exception as e:
        print(f"Error loading rules: {e}. Using default behaviors.")
        rules = {}
    # --- 结束读取规则 ---

    print("--- Starting CP-SAT Scheduler (Applying JSON Rules) ---") # 更新标题
    start_total_time = time.time()

    # --- 文件路径 ---
    teacher_file = "教师信息.xlsx"; class_file = "班级数据.xls"
    room_file = "教室信息.xls"; task_file = "排课任务.xlsx"
    output_file = "课程表方案_CP_SAT_Rules_MinOverflow.xlsx" # 新文件名

    # --- 1. 数据加载 ---
    print("\n--- Step 1: Loading Data ---")
    load_start = time.time()
    try:
        df_teachers = load_teacher_info(teacher_file)
        df_classes = load_class_info(class_file)
        df_rooms = load_room_info(room_file)
        df_tasks = load_task_info(task_file)
        if df_rooms.empty or df_teachers.empty or df_classes.empty or df_tasks.empty:
             print("错误：一个或多个输入数据文件为空或加载失败。"); return None
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
        if '固定教室' in df_classes.columns and 'class_name' in df_classes.columns:
            for index, row in df_classes.iterrows():
                 class_name = row['class_name']
                 fixed_room_name = str(row['固定教室']).strip() if pd.notna(row['固定教室']) and str(row['固定教室']).strip() else None
                 if class_name and fixed_room_name:
                      if fixed_room_name not in room_capacity_dict_by_name: print(f"Warning: Fixed room name '{fixed_room_name}' for class '{class_name}' not found. Ignored.")
                      else: class_name_to_fixed_room_name[class_name] = fixed_room_name
            print(f"Created class-to-fixed-room lookup for {len(class_name_to_fixed_room_name)} classes.")
        else: print("Warning: '固定教室' column not found. Class fixed room constraint ignored.")
    except Exception as e: print(f"创建查找字典时出错: {e}"); traceback.print_exc(); return None
    # --- 结束创建字典 ---

    # --- 2. 预处理 ---
    print("\n--- Step 2: Preprocessing Tasks ---")
    preprocess_start = time.time()
    try:
        # *** 调用 preprocess_tasks 并传递 rules ***
        tasks_preprocessed = preprocess_tasks(
            df_tasks, df_classes, df_teachers, df_rooms,
            room_capacity_dict_by_name, max_overall_capacity,
            class_name_to_fixed_room_name,
            rules # <<< 传递 rules
        )
        if tasks_preprocessed is None or not tasks_preprocessed:
             print("错误：预处理失败或未生成任务。"); return None
    except Exception as e: print(f"任务预处理出错: {e}"); traceback.print_exc(); return None
    preprocess_end = time.time(); print(f"Task Preprocessing completed in {preprocess_end - preprocess_start:.2f} seconds.")

    # --- 3. 构建 CP 模型 ---
    print("\n--- Step 3: Building CP-SAT Model ---")
    build_start = time.time()
    try:
        # *** 调用 build_cp_model 并传递 rules 和正确的字典 ***
        model, _, meta_data = build_cp_model(
            tasks_preprocessed, df_rooms, df_teachers, df_classes,
            room_capacity_dict_by_id, # ID 容量字典
            room_name_to_id_map,      # Name->ID 映射
            all_room_ids,             # 所有 Room ID
            rules                     # <<< 传递 rules
        )
    except Exception as e: print(f"构建 CP 模型时出错: {e}"); traceback.print_exc(); return None
    build_end = time.time(); print(f"Model Building completed in {build_end - build_start:.2f} seconds.")

    # --- 4. 求解 ---
    print("\n--- Step 4: Solving the Model ---")
    solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = 1000 # 可调整
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
        solution_list = extract_solution(solver, None, meta_data)
        if solution_list:
            try:
                df_solution = pd.DataFrame(solution_list); df_solution.to_excel(output_file, index=False)
                print(f"Solution successfully saved to {output_file}"); result_data["output_file"] = output_file
            except Exception as e: print(f"Error saving solution: {e}"); result_data["status"] = "ERROR_SAVING"
        else: print("Error: Solution extraction failed."); result_data["status"] = "ERROR_EXTRACTING"
    elif status == cp_model.INFEASIBLE: print("Solver proved infeasible.")
    elif status == cp_model.MODEL_INVALID: print("Error: Invalid model.")
    else: print(f"Solver finished: {solver.StatusName()}. No solution found.")
    process_end = time.time(); print(f"Result Processing completed in {process_end - process_start:.2f} seconds.")
    end_total_time = time.time(); print(f"\nTotal script execution time: {end_total_time - start_total_time:.2f} seconds.")
    return result_data

# ===================== 主程序入口 =====================
# (确保这部分在文件的最末尾！)
# if __name__ == "__main__":
#     ... (调用 run_cp_sat_scheduler 的代码保持不变) ...
if __name__ == "__main__":
    print("========================================")
    print(" Starting Course Scheduling using CP-SAT (Applying JSON Rules)")
    print("========================================")
    # 调用上面定义的 run_cp_sat_scheduler 函数
    final_result = run_cp_sat_scheduler()
    print("\n--- Final Summary ---")
    if final_result:
        print(f"Final Status: {final_result.get('status', 'N/A')}")
        if "output_file" in final_result:
            print(f"Output File: {final_result.get('output_file')}")
            print("\nNext Step: Check Excel for schedule and 'student_overflow'. Verify constraints.")
        elif final_result.get('status') == 'INFEASIBLE':
             print("The problem is infeasible even with specified rules and minimizing overflow.")
        else: print("Scheduler finished, but may not have produced a valid output file.")
    else: print("Scheduler script failed to run completely.")
    print("========================================")