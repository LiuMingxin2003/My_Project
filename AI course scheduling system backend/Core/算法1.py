# ==============================================================================
# 算法1.py - 完整最终代码
# 版本: v_final_json_filtered_fixed
# 描述:
# - 使用 CP-SAT 区间变量进行排课
# - 通过 JSON 文件驱动规则应用
# - 最小化教室容量的总超员人数
# - 添加了按指定“开课院系”筛选任务的功能
# - 修正了 extract_solution 中的 AttributeError
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
        # 优先使用已有列名，若不存在则尝试重命名
        rename_map = {"工号": "teacher_id", "姓名": "teacher_name", "单位": "department"}
        df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns}, inplace=True)
        # df.rename(columns={"工号": "teacher_id", "姓名": "teacher_name", "单位": "department"}, inplace=True, errors='ignore') # 旧方式
        if "teacher_id" not in df.columns or "teacher_name" not in df.columns: raise ValueError("教师信息文件缺少 '工号'/'teacher_id' 或 '姓名'/'teacher_name' 列。")
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
        rename_map = {"班级编号": "class_id", "班级名称": "class_name", "班级人数": "student_count", "专业编号": "major_id", "专业方向": "major_direction", "指定教室": "fixed_room"}
        df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns}, inplace=True)
        # df.rename(columns={"班级编号": "class_id", "班级名称": "class_name", "班级人数": "student_count", "专业编号": "major_id", "专业方向": "major_direction", "指定教室": "fixed_room"}, inplace=True, errors='ignore') # 旧方式
        if "class_name" not in df.columns or "student_count" not in df.columns: raise ValueError("班级数据文件缺少 '班级名称'/'class_name' 或 '班级人数'/'student_count' 列。")
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
        rename_map = {"教室编号": "room_id", "教室名称": "room_name", "最大上课容纳人数": "capacity", "教室类型": "room_type"}
        df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns}, inplace=True)
        # df.rename(columns={"教室编号": "room_id", "教室名称": "room_name", "最大上课容纳人数": "capacity", "教室类型": "room_type"}, inplace=True, errors='ignore') # 旧方式
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
        # 检查必需列是否存在 (接受中文或英文名)
        required_cols_map = {
            "课程编号": "course_id", "课程名称": "course_name", "课程性质": "course_type",
            "任课教师": "teacher_name", "教学班组成": "class_string",
            "开课周次学时": "week_hour_string", "连排节次": "consecutive_periods",
            "开课院系": "department_name" # <<< 确保包含开课院系列
        }
        actual_required = []
        for cn_name, en_name in required_cols_map.items():
             if cn_name in df.columns:
                 df.rename(columns={cn_name: en_name}, inplace=True)
                 actual_required.append(en_name)
             elif en_name in df.columns:
                 actual_required.append(en_name)
             else:
                 # 如果开课院系不是绝对必需，可以调整这里的逻辑
                 if en_name == "department_name":
                     print(f"Warning: 排课任务文件缺少可选列: '{cn_name}'/'{en_name}'. Department filtering might not work.")
                     df[en_name] = None # 添加空列以避免后续错误
                 else:
                     raise ValueError(f"排课任务文件缺少必需列: '{cn_name}'/'{en_name}'")

        # 检查可选列
        optional_cols_map = {"指定教室": "specified_room", "指定教室类型": "specified_room_type"}
        for cn_name, en_name in optional_cols_map.items():
             if cn_name in df.columns:
                 df.rename(columns={cn_name: en_name}, inplace=True)
             elif en_name not in df.columns:
                 df[en_name] = None # 添加空列

        # 清理数据
        if 'teacher_name' in df.columns: df['teacher_name'] = df['teacher_name'].astype(str).str.strip()
        if 'specified_room' in df.columns: df['specified_room'] = df['specified_room'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() else None)
        if 'department_name' in df.columns: df['department_name'] = df['department_name'].astype(str).str.strip()

        return df
    except FileNotFoundError: print(f"错误：找不到文件 {filepath}"); raise
    except Exception as e: print(f"加载排课任务时出错: {e}"); raise

# ===================== 2. 数据预处理 (应用 JSON 规则 - 最终版) =====================

def preprocess_tasks(df_tasks: pd.DataFrame,
                     df_classes: pd.DataFrame,
                     df_teachers: pd.DataFrame,
                     df_rooms: pd.DataFrame,
                     room_capacity_dict_by_name: dict,
                     max_overall_capacity: float,
                     class_name_to_fixed_room_name: dict,
                     rules: dict) -> list:
    """
    预处理任务数据，应用 JSON 规则，为区间变量模型准备 task units。
    包含体育课/实验课识别逻辑。
    """
    print("Preprocessing tasks (Applying JSON Rules, Identifying PE/Lab)...")
    task_units = []
    task_unit_id_counter = 0
    missing_teachers = set(); missing_classes_in_specific_tasks = set()
    skipped_tasks_fixed_room_conflict = 0
    skipped_by_forbidden_teacher = 0; skipped_by_forbidden_course = 0

    # --- 从 rules 中获取配置 ---
    basic_rules = rules.get('basic', {})
    apply_fixed_classroom = basic_rules.get('fixedClassroom', True) # 保持之前逻辑，默认True
    force_consecutive_rule = basic_rules.get('continuousHours', True) # 保持之前逻辑，默认True
    time_rules_set = set(basic_rules.get('timeRules', []))
    sport_afternoon_only = 'sportAfternoon' in time_rules_set
    forbidden_rules = rules.get('forbidden', {})
    # 确保转换成字符串进行比较
    forbidden_teacher_ids = {str(tid).strip() for tid in forbidden_rules.get('teachers', [])}
    forbidden_course_ids = {str(cid).strip() for cid in forbidden_rules.get('courses', [])}
    print(f"Applying Rules: FixedClassroom={apply_fixed_classroom}, ForceConsecutive={force_consecutive_rule}, SportAfternoonOnly={sport_afternoon_only}")
    if forbidden_teacher_ids: print(f"  Forbidden Teacher IDs: {forbidden_teacher_ids}")
    if forbidden_course_ids: print(f"  Forbidden Course IDs: {forbidden_course_ids}")

    # --- 数据准备 ---
    teacher_name_to_id = pd.Series(df_teachers.teacher_id.values, index=df_teachers.teacher_name).to_dict()
    class_name_to_students = pd.Series(df_classes.student_count.values, index=df_classes.class_name).to_dict()
    all_class_names_list = df_classes["class_name"].tolist()
    print(f"Total number of unique classes found: {len(all_class_names_list)}")
    print(f"Using pre-calculated max room capacity: {max_overall_capacity}")

    # --- 检查列并设置默认值 (使用英文列名) ---
    if 'specified_room' not in df_tasks.columns: df_tasks['specified_room'] = None
    if 'week_hour_string' not in df_tasks.columns: df_tasks['week_hour_string'] = '1-1:1' # Example default
    if 'consecutive_periods' not in df_tasks.columns: df_tasks['consecutive_periods'] = 1
    df_tasks['consecutive_periods'] = pd.to_numeric(df_tasks['consecutive_periods'], errors='coerce').fillna(1).astype(int).apply(lambda x: max(1, x))

    # --- 过滤禁排课程/教师 ---
    # (注意：部门筛选已在 run_cp_sat_scheduler 中完成)
    initial_task_count = len(df_tasks)
    original_indices = df_tasks.index # 保存原始索引以便追踪

    if forbidden_course_ids:
        df_tasks = df_tasks[~df_tasks['course_id'].astype(str).isin(forbidden_course_ids)]
        skipped_by_forbidden_course = initial_task_count - len(df_tasks)
        initial_task_count = len(df_tasks)

    # 需要 teacher_id 列来进行教师禁排过滤，先映射
    df_tasks['teacher_id_temp'] = df_tasks['teacher_name'].map(teacher_name_to_id)
    if forbidden_teacher_ids:
        df_tasks = df_tasks[~df_tasks['teacher_id_temp'].astype(str).isin(forbidden_teacher_ids)]
        skipped_by_forbidden_teacher = initial_task_count - len(df_tasks)
        initial_task_count = len(df_tasks)

    # 如果没有任务了，直接返回
    if df_tasks.empty:
        print("No tasks remaining after applying forbidden rules.")
        return []

    print(f"Processing {len(df_tasks)} tasks after forbidden checks.")

    # --- 迭代处理任务 ---
    print("Processing tasks, identifying PE/Lab, creating task units:")
    for index in tqdm(original_indices.intersection(df_tasks.index), total=len(df_tasks), desc="Preprocessing Tasks"):
        row = df_tasks.loc[index] # 使用 .loc 获取行
        original_task_ref = f"orig_{index}"
        # --- 获取基本信息 (使用英文列名) ---
        c_id_raw = row.get("course_id"); c_name = row.get("course_name", "Unknown")
        t_name = row.get("teacher_name", "").strip(); course_nature = row.get("course_type", "")
        c_id = str(c_id_raw).strip() if pd.notna(c_id_raw) else f"UNKNOWN_{original_task_ref}"
        teacher_id = row.get("teacher_id_temp") # 使用前面映射好的 teacher_id

        # Double check teacher ID validity (should be valid after map, but good practice)
        if pd.isna(teacher_id):
             if t_name not in missing_teachers: missing_teachers.add(t_name); print(f"Teacher mapping failed for: {t_name}")
             continue # Skip if teacher ID couldn't be found

        # 解析周学时 H
        weekly_hours_str = str(row.get("week_hour_string", '1-1:1')).strip(); weekly_periods = 1
        match_hours = re.search(r':(\d+)$', weekly_hours_str)
        if match_hours:
            try: weekly_periods = max(1, int(match_hours.group(1)))
            except ValueError: weekly_periods = 1

        # 根据 continuousHours 规则决定连排 C
        consecutive_periods = 1
        if force_consecutive_rule: consecutive_periods = weekly_periods
        else: consecutive_periods = max(1, int(row.get('consecutive_periods', 1))); consecutive_periods = min(consecutive_periods, weekly_periods)

        required_room_type = None # 暂不使用指定教室类型列
        task_fixed_room_name = str(row.get("specified_room")).strip() if pd.notna(row.get("specified_room")) and str(row.get("specified_room")).strip() else None

        # --- 识别体育课和实验课 ---
        is_pe_course = False
        is_lab_course = False
        # (使用之前提供的逻辑)
        pe_nature_values = ["体育", "体育课"]
        lab_nature_values = ["实验", "实验课", "实践", "上机", "实训"]
        if course_nature in pe_nature_values: is_pe_course = True
        elif course_nature in lab_nature_values: is_lab_course = True
        else: # Check keywords if nature doesn't match
             pe_keywords = ["体育"]
             lab_keywords = ["实验", "实践", "上机", "实训"]
             if any(keyword in c_name for keyword in pe_keywords): is_pe_course = True
             elif any(keyword in c_name for keyword in lab_keywords): is_lab_course = True

        # --- 判断班级情况并确定处理组 (使用英文列名) ---
        class_list_str_raw = row.get("class_string");
        is_empty_or_nan = pd.isna(class_list_str_raw) or (isinstance(class_list_str_raw, str) and not class_list_str_raw.strip())
        task_groups_to_process = []

        # 情况一：必修课且教学班组成为空 -> 为所有班级创建任务
        # 注意：这可能导致大量任务单元，需要确认是否符合预期
        if course_nature == "必修课" and is_empty_or_nan:
            print(f"Warning: Mandatory course '{c_name}' ({c_id}) has no class assigned. Creating units for ALL classes.")
            for class_name in all_class_names_list:
                student_count = class_name_to_students.get(class_name)
                if student_count is not None and student_count > 0:
                    final_fixed_room_name = None
                    if apply_fixed_classroom: class_fixed_room_name = class_name_to_fixed_room_name.get(class_name); final_fixed_room_name = task_fixed_room_name if task_fixed_room_name else class_fixed_room_name
                    task_groups_to_process.append({"class_list": [class_name], "total_students": student_count, "group_ref": class_name, "effective_fixed_room_name": final_fixed_room_name})
        # 情况二：教学班组成不为空
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
                        # else: Class has 0 students, ignore? Or warn?
                    else:
                        if cl not in missing_classes_in_specific_tasks: missing_classes_in_specific_tasks.add(cl); task_missing_classes = True
                if apply_fixed_classroom and fixed_room_conflict: skipped_tasks_fixed_room_conflict += 1; continue
                if apply_fixed_classroom and not effective_fixed_room_name and first_class_fixed_room_name: effective_fixed_room_name = first_class_fixed_room_name
                if not task_missing_classes and valid_class_list and total_students > 0:
                    task_groups_to_process.append({"class_list": valid_class_list, "total_students": total_students, "group_ref": "_".join(sorted(valid_class_list)), "effective_fixed_room_name": effective_fixed_room_name if apply_fixed_classroom else None})
        # 情况三：非必修课且教学班组成空 -> 跳过？或警告？
        # else:
        #     print(f"Warning: Non-mandatory course '{c_name}' ({c_id}) has no class assigned. Skipping.")

        # --- 生成 task unit (根据 H 和 C 拆分) ---
        for group_info in task_groups_to_process:
            group_ref = group_info["group_ref"]; required_students = group_info["total_students"]
            effective_fixed_room_name = group_info["effective_fixed_room_name"]

            # 根据 H 和 C 生成单元
            units_to_create = []
            block_idx_gen = 0
            H = weekly_periods; C = consecutive_periods
            if C > H: C = H
            if H <= 0: continue

            if C >= H: units_to_create.append({"duration": H, "block_index": 0})
            else: # H > C >= 1
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
                    "duration": unit_info["duration"],
                    "course_id": c_id, "course_name": c_name, "teacher_id": str(teacher_id), # 确保 teacher_id 是字符串
                    "class_list": group_info["class_list"], "total_students": required_students,
                    "required_room_type": required_room_type, # 保持 None
                    "fixed_room_name": effective_fixed_room_name, # 名称或 None
                    "is_pe_course": is_pe_course,
                    "is_lab_course": is_lab_course
                    # "priority": ... # <<< 如果需要，这里需要添加从 rules 或课程信息计算出的优先级
                })
                task_unit_id_counter += 1
    # --- 结束主循环 ---

    # 清理临时列
    if 'teacher_id_temp' in df_tasks.columns:
         df_tasks.drop(columns=['teacher_id_temp'], inplace=True)


    # --- 打印警告 ---
    if missing_teachers: print(f"\nWarning Summary: Skipped tasks for teachers not found or failed mapping: {missing_teachers}")
    if missing_classes_in_specific_tasks: print(f"\nWarning Summary: Skipped/processed tasks involving specific classes not found in class list: {missing_classes_in_specific_tasks}")
    if skipped_tasks_fixed_room_conflict > 0: print(f"\nWarning Summary: Skipped {skipped_tasks_fixed_room_conflict} task groups due to conflicting fixed rooms within the same task.")
    if skipped_by_forbidden_teacher > 0: print(f"\nWarning Summary: Skipped {skipped_by_forbidden_teacher} tasks due to forbidden teacher.")
    if skipped_by_forbidden_course > 0: print(f"\nWarning Summary: Skipped {skipped_by_forbidden_course} tasks due to forbidden course.")

    print(f"\nPreprocessing finished. Generated {len(task_units)} weekly task units.")
    return task_units if task_units else [] # 确保返回列表

# ===================== 3. 构建 CP 模型 (应用 JSON 规则 - 修正版) =====================
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
    修正：包含 PresenceLiteral 错误的修正。
    """
    print("Building CP-SAT model (Applying JSON Rules - Fixed)...")
    model = cp_model.CpModel()

    # --- 1. 基础数据准备 ---
    time_slots = [(d, p) for d in range(5) for p in range(10)] # 10 节课
    num_time_slots = len(time_slots) # 50
    periods_per_day = 10
    morning_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if p < 4}
    afternoon_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if 4 <= p < 8}
    evening_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if p >= 8}

    if not all_room_ids: raise ValueError("教室 ID 列表为空!")
    basic_rules = rules.get('basic', {})
    apply_fixed_classroom = basic_rules.get('fixedClassroom', True) # Default True
    time_rules_set = set(basic_rules.get('timeRules', []))
    sport_afternoon_only = 'sportAfternoon' in time_rules_set
    # Night/Lab rules might need checking here too, depending on implementation
    lab_night_only = 'labNightOnly' in time_rules_set # Example

    teacher_limits_rule = {str(item['teacherId']).strip(): item['limits'] # Ensure keys are strings
                           for item in rules.get('teacherLimits', [])
                           if 'teacherId' in item and 'limits' in item}

    # 获取教师 ID 到 Name 的映射
    if "teacher_id" not in df_teachers.columns or "teacher_name" not in df_teachers.columns: raise ValueError("教师信息缺少列")
    teacher_id_to_name = pd.Series(df_teachers.teacher_name.values, index=df_teachers.teacher_id.astype(str)).to_dict() # ID must be string for lookup

    print(f"Applying Rules: FixedClassroom={apply_fixed_classroom}, SportAfternoonOnly={sport_afternoon_only}, LabNightOnly={lab_night_only}")
    if teacher_limits_rule: print(f"  Teacher Limits Found for IDs: {list(teacher_limits_rule.keys())}")

    # --- 2. 按原始任务分组 (如果需要可以保留，当前模型不直接使用) ---
    # task_units_by_original = defaultdict(list);
    # for task_unit in task_units_preprocessed: task_units_by_original[task_unit['original_task_ref']].append(task_unit)

    # --- 3. 构造变量 (应用规则剪枝, 修正 PresenceLiteral 存储) ---
    print("Creating interval variables (Applying rule-based pruning)...")
    all_assignments_data = defaultdict(dict) # key: (tu_id, room_id) -> {'interval': interval_var, 'presence': presence_var}
    presence_literals_per_task = defaultdict(list)
    task_units_with_no_valid_assignment = set()
    all_overflow_vars = []
    overflow_vars_map = {} # key: (tu_id, room_id) -> overflow_var
    max_possible_total_overflow = 0

    task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units_preprocessed} # Precompute lookup

    for task_unit in tqdm(task_units_preprocessed, desc="Creating Variables"):
        try:
            tu_id = task_unit["task_unit_id"]; duration = task_unit["duration"]
            required_students = task_unit["total_students"]; teacher_id = str(task_unit["teacher_id"]) # Ensure string
            fixed_room_name = task_unit.get("fixed_room_name") if apply_fixed_classroom else None
            is_pe_course = task_unit.get("is_pe_course", False)
            is_lab_course = task_unit.get("is_lab_course", False) # Get lab flag

            if duration <= 0 or duration > num_time_slots: task_units_with_no_valid_assignment.add(tu_id); continue

            possible_room_ids = []
            if fixed_room_name:
                fixed_room_id = room_name_to_id_map.get(fixed_room_name)
                if fixed_room_id and fixed_room_id in room_capacity_dict_by_id: possible_room_ids = [fixed_room_id]
                else: task_units_with_no_valid_assignment.add(tu_id); print(f"TU {tu_id}: Fixed room '{fixed_room_name}' invalid."); continue
            else: possible_room_ids = all_room_ids

            if not possible_room_ids: task_units_with_no_valid_assignment.add(tu_id); print(f"TU {tu_id}: No possible rooms."); continue

            task_presences = []
            # --- 获取此教师的特定时间限制 ---
            teacher_limit = teacher_limits_rule.get(teacher_id) # Use ID string
            teacher_allow_am = True; teacher_allow_pm = True; teacher_allow_evening = True # Add evening
            if teacher_limit:
                # Check boolean flags first
                if teacher_limit.get('morning') == False: teacher_allow_am = False
                if teacher_limit.get('afternoon') == False: teacher_allow_pm = False
                if teacher_limit.get('evening') == False: teacher_allow_evening = False # Check for potential 'evening' key

                # More specific checks (e.g., amMax == 0 implies morning=False) could be added if needed
                # if teacher_limit.get('amMax') == 0: teacher_allow_am = False
                # etc.
            # --- 结束获取教师限制 ---

            found_valid_option = False # Track if any room/time combo is valid
            for room_id in possible_room_ids:
                room_cap = room_capacity_dict_by_id.get(room_id, 0)
                overflow_amount = max(0, required_students - room_cap)
                max_possible_total_overflow += overflow_amount

                # --- 时间剪枝 ---
                valid_starts = set(range(num_time_slots - duration + 1))
                # 1. 教师通用时间限制
                if not teacher_allow_am: valid_starts = {s for s in valid_starts if not any(s + i in morning_slots for i in range(duration))}
                if not teacher_allow_pm: valid_starts = {s for s in valid_starts if not any(s + i in afternoon_slots for i in range(duration))}
                if not teacher_allow_evening: valid_starts = {s for s in valid_starts if not any(s + i in evening_slots for i in range(duration))}
                # 2. 体育课时间限制 (只允许下午/晚上?) - Check exact definition needed
                if is_pe_course and sport_afternoon_only:
                     # Allow afternoon OR evening? Or just afternoon? Assuming afternoon OR evening for now.
                     allowed_pe_slots = afternoon_slots.union(evening_slots)
                     valid_starts = {s for s in valid_starts if all(s + i in allowed_pe_slots for i in range(duration))}
                     # If strictly afternoon (4-7):
                     # valid_starts = {s for s in valid_starts if all(s + i in afternoon_slots for i in range(duration))}
                # 3. 实验课时间限制 (只允许晚上)
                if is_lab_course and lab_night_only:
                    valid_starts = {s for s in valid_starts if all(s + i in evening_slots for i in range(duration))}

                if not valid_starts: continue # 如果此房间没有有效的开始时间了
                start_domain = cp_model.Domain.FromValues(list(valid_starts))
                # --- 结束时间剪枝 ---

                found_valid_option = True # At least one room/time is possible

                # --- 创建变量 ---
                presence_var = model.NewBoolVar(f'presence_{tu_id}_{room_id}')
                start_var = model.NewIntVarFromDomain(start_domain, f'start_{tu_id}_{room_id}')
                interval_var = model.NewOptionalFixedSizeIntervalVar(start=start_var, size=duration, is_present=presence_var, name=f'interval_{tu_id}_{room_id}')

                assignment_key = (tu_id, room_id)
                all_assignments_data[assignment_key] = {'interval': interval_var, 'presence': presence_var}
                task_presences.append(presence_var)

                # --- 创建超员变量 (并存储映射) ---
                overflow_var = model.NewIntVar(0, overflow_amount, f'overflow_{tu_id}_{room_id}')
                model.Add(overflow_var == overflow_amount).OnlyEnforceIf(presence_var)
                model.Add(overflow_var == 0).OnlyEnforceIf(presence_var.Not())
                all_overflow_vars.append(overflow_var)
                overflow_vars_map[assignment_key] = overflow_var

            if task_presences:
                presence_literals_per_task[tu_id] = task_presences
            elif not found_valid_option: # Only mark as impossible if no room/time combo worked
                 task_units_with_no_valid_assignment.add(tu_id)
                 print(f"TU {tu_id}: No valid room/time option found after pruning.")


        except KeyError as e: print(f"\n>>> BUILD KeyError: {e} in task_unit: {task_unit}"); raise
        except Exception as e: print(f"\n>>> BUILD Error: {e} processing {task_unit}"); traceback.print_exc(); raise # Print traceback

    if task_units_with_no_valid_assignment: print(f"\nWarning Summary: {len(task_units_with_no_valid_assignment)} task units have NO valid assignment options after pruning.")
    print(f"Created {len(all_assignments_data)} optional assignment variables (task-room combos).")
    print(f"Created {len(all_overflow_vars)} overflow variables.")

    # --- 4. 添加约束 ---
    print("Adding constraints...")
    # (H0) ExactlyOne Room Assignment Per Task Unit
    print("  - Adding Task Assignment (ExactlyOne Room)..."); assigned_task_unit_count = 0
    unassigned_tasks = set(task_unit_lookup.keys()) # Start with all task unit IDs
    for tu_id, presence_vars in presence_literals_per_task.items():
        if tu_id in task_units_with_no_valid_assignment:
             unassigned_tasks.discard(tu_id) # Remove impossible tasks
             continue
        if presence_vars:
             model.AddExactlyOne(presence_vars);
             assigned_task_unit_count += 1
             unassigned_tasks.discard(tu_id) # Remove tasks that *can* be assigned
    print(f"  - ExactlyOne constraints added for {assigned_task_unit_count} task units.")
    if unassigned_tasks: # Should be empty if all tasks were processed
        print(f"CRITICAL Warning: {len(unassigned_tasks)} task units seem unprocessed or missing presence literals: {list(unassigned_tasks)[:20]}...")
    if task_units_with_no_valid_assignment:
        print(f"INFO: {len(task_units_with_no_valid_assignment)} tasks cannot be assigned due to rule conflicts or invalid data.")

    # (H1, H2, H3) NoOverlap Constraints
    print("  - Adding NoOverlap constraints for Resources...")
    intervals_in_room=defaultdict(list); intervals_for_teacher=defaultdict(list); intervals_for_class=defaultdict(list)
    for key, data in all_assignments_data.items():
        tu_id, room_id = key
        interval_var = data['interval']
        task_unit = task_unit_lookup.get(tu_id);
        if not task_unit: continue
        teacher_id = str(task_unit["teacher_id"]); class_list = task_unit.get("class_list", []) # Ensure teacher ID is string
        intervals_in_room[room_id].append(interval_var)
        intervals_for_teacher[teacher_id].append(interval_var)
        for class_name in class_list:
            if isinstance(class_name, str) and class_name: intervals_for_class[class_name].append(interval_var)
    print("    - Applying NoOverlap for rooms..."); [model.AddNoOverlap(intervals) for intervals in intervals_in_room.values() if len(intervals) > 1]
    print("    - Applying NoOverlap for teachers...");[model.AddNoOverlap(intervals) for intervals in intervals_for_teacher.values() if len(intervals) > 1]
    print("    - Applying NoOverlap for classes..."); [model.AddNoOverlap(intervals) for intervals in intervals_for_class.values() if len(intervals) > 1]

    # (H_Load) 教师负载约束 (Weekly Only - Daily/AM/PM remain unimplemented in CP-SAT)
    print("  - Adding Teacher weekly load constraints from rules...")
    active_limit_teachers = 0
    # Create overall presence vars per task unit (needed for summing load)
    task_presence_vars = {} # tu_id -> overall_presence_BoolVar
    for tu_id, presence_vars_list in presence_literals_per_task.items():
        if presence_vars_list: # Only if there are options
             task_presence_vars[tu_id] = model.NewBoolVar(f'task_present_{tu_id}')
             model.AddMaxEquality(task_presence_vars[tu_id], presence_vars_list)

    teacher_task_presences = defaultdict(list)
    for tu_id, task_unit in task_unit_lookup.items():
        if tu_id in task_presence_vars: # Only consider tasks that can be scheduled
             teacher_id = str(task_unit.get("teacher_id")) # Ensure string
             teacher_task_presences[teacher_id].append(task_presence_vars[tu_id])

    # --- Loop through teacher limits defined in rules ---
    for teacher_id_key, limits in teacher_limits_rule.items():
        teacher_id_target = str(teacher_id_key).strip() # Assume key is ID

        # --- Apply limits only if the teacher has tasks in the model ---
        if teacher_id_target in teacher_task_presences:
            weekly_max = limits.get('weeklyMax')
            if weekly_max is not None:
                model.Add(sum(teacher_task_presences[teacher_id_target]) <= weekly_max)
                print(f"    - Weekly load constraint (<= {weekly_max} tasks) added for Teacher ID: {teacher_id_target}")
                active_limit_teachers += 1
            # else: # Optional: Print if no weekly limit found
            #      print(f"    - No weeklyMax found for teacher {teacher_id_target}")

            # --- Placeholder for unimplemented daily/am/pm limits ---
            if limits.get('dailyMax') is not None: print(f"    - NOTE: Daily Max constraint for teacher {teacher_id_target} NOT IMPLEMENTED in CP-SAT model.")
            if limits.get('amMax') is not None: print(f"    - NOTE: AM Max constraint for teacher {teacher_id_target} NOT IMPLEMENTED in CP-SAT model.")
            if limits.get('pmMax') is not None: print(f"    - NOTE: PM Max constraint for teacher {teacher_id_target} NOT IMPLEMENTED in CP-SAT model.")
        # --- Removed redundant check against forbidden_teacher_ids here ---
        # else: # Teacher ID from rules has no tasks associated in the model
              # This could be because they were filtered (forbidden or no tasks for dept)
              # or simply have no tasks in the current filtered task list.
              # print(f"    - Warning: Teacher {teacher_id_target} from limits rule has no schedulable tasks found.") # Optional warning

    if active_limit_teachers == 0: print("    - No specific teacher load limits applied from rules (check teacher IDs in JSON/Tasks).")
    

    # --- 5. 设置优化目标：最小化总超员量 ---
    print("  - Setting Objective: Minimize Total Capacity Overflow...")
    if all_overflow_vars:
        # Ensure safe upper bound calculation
        try:
             safe_upper_bound = sum(ov.Proto().domain[-1] for ov in all_overflow_vars if hasattr(ov, 'Proto') and ov.Proto().domain)
             if safe_upper_bound == 0: # If all individual max overflows are 0, but vars exist
                 safe_upper_bound = sum(tu['total_students'] for tu in task_units_preprocessed if 'total_students' in tu)
        except Exception: # Fallback if accessing Proto fails
             safe_upper_bound = sum(tu['total_students'] for tu in task_units_preprocessed if 'total_students' in tu) * len(all_room_ids) # Crude upper bound

        total_overflow_var = model.NewIntVar(0, int(safe_upper_bound), 'total_overflow')
        model.Add(total_overflow_var == sum(all_overflow_vars))
        model.Minimize(total_overflow_var)
        print(f"    - Objective set. Max possible overflow approx: {safe_upper_bound}")
    else: print("    - No overflow variables created. No overflow objective added.")

    print("Model building complete.")
    # --- meta_data (修正版) ---
    if 'room_id' in df_rooms.columns and 'room_name' in df_rooms.columns: room_id_to_name_map = pd.Series(df_rooms.room_name.values, index=df_rooms.room_id.astype(str)).to_dict() # Ensure string index
    else: room_id_to_name_map = {}

    meta_data = {
        "task_units": task_units_preprocessed,
        "time_slots": time_slots,
        "all_assignments_data": all_assignments_data,
        "overflow_vars_map": overflow_vars_map,
        "room_id_to_name": room_id_to_name_map,
        "presence_literals_per_task": presence_literals_per_task, # Used by extract_solution
        "task_unit_lookup": task_unit_lookup # Pass lookup for convenience
    }
    return model, None, meta_data # Return None for x_vars as it's not used

# ===================== 4. 解读模型解 (修正 PresenceLiteral 错误) =====================
def extract_solution(solver: cp_model.CpSolver, x_vars: dict, meta_data: dict) -> list:
    """
    读取CP-SAT使用区间变量的解 (修正 PresenceLiteral 错误)。
    """
    print("Extracting solution from Interval Variable model (Fixed PresenceLiteral Error)...")
    task_units = meta_data["task_units"]; time_slots = meta_data["time_slots"]
    all_assignments_data = meta_data.get("all_assignments_data", {})
    overflow_vars_map = meta_data.get("overflow_vars_map", {})
    room_id_to_name = meta_data.get("room_id_to_name", {}); solution = []
    presence_literals_per_task = meta_data.get('presence_literals_per_task', {})
    task_unit_lookup = meta_data.get("task_unit_lookup", {}) # Get lookup
    if not task_unit_lookup: # Rebuild if missing
         task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units}

    if not task_units or solver.StatusName() not in ["OPTIMAL", "FEASIBLE"]:
        print("No solution to extract or solver status not Optimal/Feasible.")
        return []

    start_time_ext = time.time(); assigned_task_unit_count = 0; total_schedule_overflow = 0
    print("Extracting assignments and overflow:")
    processed_tu_ids = set() # 用于确保 overflow 只加一次

    for key, data in tqdm(all_assignments_data.items(), desc="Extracting Solution"):
        tu_id, room_id = key
        interval_var = data['interval']
        presence_var = data['presence']

        # --- 正确的检查方式 ---
        try:
            is_present = solver.BooleanValue(presence_var)
        except Exception as e:
             print(f"Warning: Could not evaluate presence for ({tu_id},{room_id}): {e}. Skipping.")
             continue # Skip if presence cannot be determined

        if is_present:
            task_unit = task_unit_lookup.get(tu_id);
            if not task_unit:
                print(f"Warning: Task unit data not found for tu_id {tu_id} during extraction. Skipping.")
                continue

            try:
                 start_idx = solver.Value(interval_var.StartExpr()); duration = task_unit["duration"]
            except Exception as e:
                  print(f"Warning: Could not get start/duration for ({tu_id},{room_id}): {e}. Skipping assignment.")
                  continue # Skip if start time cannot be determined

            room_name = room_id_to_name.get(str(room_id), str(room_id)); # Ensure lookup uses string ID
            current_task_overflow = 0
            overflow_var = overflow_vars_map.get(key)

            if overflow_var is not None:
                try: current_task_overflow = solver.Value(overflow_var)
                except Exception as e: print(f"Warning: Could not get overflow value for {key}: {e}")

            # 累加 overflow 和计数
            if tu_id not in processed_tu_ids:
                total_schedule_overflow += current_task_overflow
                assigned_task_unit_count += 1
                processed_tu_ids.add(tu_id)

            # 展开时间点
            for i in range(duration):
                ts_idx = start_idx + i
                if 0 <= ts_idx < len(time_slots):
                    day, period = time_slots[ts_idx]
                    solution.append({
                        "task_unit_id": tu_id, "original_task_ref": task_unit.get("original_task_ref", "N/A"),
                        "duration": duration, "course_id": task_unit.get("course_id", "N/A"),
                        "course_name": task_unit.get("course_name", "N/A"), "teacher_id": task_unit.get("teacher_id", "N/A"),
                        "class_list": task_unit.get("class_list", []), "room_id": str(room_id), "room_name": room_name, # Ensure room_id is string
                        "day_of_week": day, "period": period, "is_start_period": (i == 0),
                        "student_overflow": current_task_overflow
                    })
                else:
                     print(f"Warning: Calculated time slot index {ts_idx} is out of bounds (0-{len(time_slots)-1}) for task {tu_id}.")


    end_time_ext = time.time()
    num_tasks_in_model = len(presence_literals_per_task) # Tasks with potential assignments
    print(f"Solution extraction complete. Extracted assignments for {assigned_task_unit_count} task units in {end_time_ext - start_time_ext:.2f} seconds.")
    print(f"Sum of Overflows for assigned tasks from extracted solution: {total_schedule_overflow}")
    try:
        objective_value = solver.ObjectiveValue()
        print(f"Solver Objective Value (min total overflow): {objective_value}")
        # Sanity check
        if abs(total_schedule_overflow - objective_value) > 1e-6:
             print(f"Warning: Extracted overflow ({total_schedule_overflow}) differs from solver objective ({objective_value}). Check extraction logic.")
    except Exception as e:
         print(f"Could not retrieve solver objective value: {e}")

    if assigned_task_unit_count < num_tasks_in_model:
         print(f"Warning: Assigned task units ({assigned_task_unit_count}) < potentially assignable task units ({num_tasks_in_model}). Some tasks might be unassigned in the solution.")
         # Potentially list unassigned tasks by checking processed_tu_ids against presence_literals_per_task keys

    return solution


# ===================== 7. 主函数 (CP-SAT + JSON 规则 + 部门筛选 + 修正) =====================
def run_cp_sat_scheduler():
    """
    使用 CP-SAT 进行排课的主流程。
    包含：读取 JSON 规则, 筛选指定开课院系的任务, 最小化超员, 应用修正。
    """
    print("--- Starting CP-SAT Scheduler (Applying JSON Rules & Department Filter - Fixed) ---")
    start_total_time = time.time()

    # --- 0. 读取 JSON 规则 ---
    rules_file = "scheduling_rules.json"
    try:
        with open(rules_file, 'r', encoding='utf-8') as f:
            rules = json.load(f).get("schedulingRules", {})
        print(f"--- Loaded Scheduling Rules from {rules_file} ---")
    except FileNotFoundError:
        print(f"Error: Scheduling rules file '{rules_file}' not found. Using default behaviors.")
        rules = {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {rules_file}: {e}. Using default behaviors.")
        rules = {}
    except Exception as e:
        print(f"Error loading rules: {e}. Using default behaviors.")
        rules = {}

    # --- 文件路径 和 筛选参数 ---
    teacher_file = "教师信息.xlsx"; class_file = "班级数据.xls"
    room_file = "教室信息.xls"; task_file = "排课任务.xlsx"
    target_department = "汽车与智能交通学院" # <<< 要筛选的目标院系
    # <<< !!! 再次确认这个列名是 'department_name' 还是 '开课院系' !!! >>>
    # 假设 load_task_info 已将其重命名为 'department_name'
    department_column = "department_name"
    output_file = f"课程表方案_CP_SAT_{target_department.replace(' ','_')}.xlsx"

    # --- 1. 数据加载 和 筛选 ---
    print("\n--- Step 1: Loading Data & Filtering Tasks ---")
    load_start = time.time()
    try:
        df_teachers = load_teacher_info(teacher_file)
        df_classes = load_class_info(class_file)
        df_rooms = load_room_info(room_file)
        df_tasks = load_task_info(task_file)
        if df_rooms.empty or df_teachers.empty or df_classes.empty or df_tasks.empty:
             print("错误：一个或多个输入数据文件为空或加载失败。"); return None

        print(f"Data loaded. Original task count: {len(df_tasks)}")

        # --- 执行部门筛选 ---
        if department_column in df_tasks.columns:
            original_count = len(df_tasks)
            df_tasks = df_tasks[df_tasks[department_column] == target_department].copy()
            filtered_count = len(df_tasks)
            print(f"--- Filtered Tasks for Department: '{target_department}' ---")
            print(f"Tasks remaining after filtering: {filtered_count} (out of {original_count})")
            if filtered_count == 0:
                print(f"Warning: No tasks found for the department '{target_department}'.")
                # 决定是退出还是继续
                # return {"status": "NO_TASKS_FOR_DEPT"}
        else:
            print(f"Error: Column '{department_column}' not found in tasks file. Cannot filter by department.")
            print(f"Available columns: {df_tasks.columns.tolist()}")
            return None

    except Exception as e: print(f"数据加载或筛选时出错: {e}"); traceback.print_exc(); return None
    load_end = time.time(); print(f"Data Loading and Filtering completed in {load_end - load_start:.2f} seconds.")

    # --- 1.5 创建查找字典 ---
    print("\n--- Step 1.5: Creating Lookups ---")
    try:
        # 使用 .get() 增加鲁棒性
        room_capacity_dict_by_name = pd.Series(df_rooms.capacity.values, index=df_rooms.get('room_name', pd.Series(dtype=str))).to_dict()
        room_capacity_dict_by_id = pd.Series(df_rooms.capacity.values, index=df_rooms.get('room_id', pd.Series(dtype=str)).astype(str)).to_dict() # Ensure ID is string key
        room_name_to_id_map = pd.Series(df_rooms.get('room_id', pd.Series(dtype=str)).astype(str).values, index=df_rooms.get('room_name', pd.Series(dtype=str))).to_dict()
        room_id_to_name_map = pd.Series(df_rooms.get('room_name', pd.Series(dtype=str)).values, index=df_rooms.get('room_id', pd.Series(dtype=str)).astype(str)).to_dict() # Ensure ID is string key
        all_room_ids = df_rooms["room_id"].astype(str).tolist() if 'room_id' in df_rooms else []
        max_overall_capacity = df_rooms['capacity'].max() if not df_rooms.empty and 'capacity' in df_rooms else 0
        print(f"Created room lookups. Max capacity: {max_overall_capacity}")

        class_name_to_fixed_room_name = {}
        if 'fixed_room' in df_classes.columns and 'class_name' in df_classes.columns:
            for index, row in df_classes.iterrows():
                class_name = row['class_name']
                fixed_room_name = row.get('fixed_room') # Already cleaned in load_class_info
                if class_name and fixed_room_name:
                    if fixed_room_name not in room_capacity_dict_by_name: print(f"Warning: Fixed room name '{fixed_room_name}' for class '{class_name}' not found. Ignored.")
                    else: class_name_to_fixed_room_name[class_name] = fixed_room_name
            print(f"Created class-to-fixed-room lookup for {len(class_name_to_fixed_room_name)} classes.")
        else: print("Warning: 'fixed_room' column not found. Class fixed room constraint ignored.")
    except Exception as e: print(f"创建查找字典时出错: {e}"); traceback.print_exc(); return None

    # --- 2. 预处理 ---
    print("\n--- Step 2: Preprocessing Tasks ---")
    preprocess_start = time.time()
    tasks_preprocessed = []
    if not df_tasks.empty: # Only preprocess if tasks exist
        try:
            tasks_preprocessed = preprocess_tasks(
                df_tasks, df_classes, df_teachers, df_rooms,
                room_capacity_dict_by_name, max_overall_capacity,
                class_name_to_fixed_room_name,
                rules
            )
            if tasks_preprocessed is None: print("错误：预处理函数返回了 None。"); return None
            elif not tasks_preprocessed: print("信息：预处理未生成任何有效的任务单元。")
            else: print(f"Preprocessing complete. Generated {len(tasks_preprocessed)} task units.")
        except Exception as e: print(f"任务预处理出错: {e}"); traceback.print_exc(); return None
    else:
        print("Skipping preprocessing because no tasks remained after filtering.")
    preprocess_end = time.time(); print(f"Task Preprocessing step completed in {preprocess_end - preprocess_start:.2f} seconds.")

    # --- 如果没有任务单元，则停止 ---
    if not tasks_preprocessed:
        print("No task units to schedule. Exiting.")
        end_total_time = time.time(); print(f"\nTotal script execution time (stopped early): {end_total_time - start_total_time:.2f} seconds.")
        return {"status": "NO_TASKS_TO_SCHEDULE"}

    # --- 3. 构建 CP 模型 ---
    print("\n--- Step 3: Building CP-SAT Model ---")
    build_start = time.time()
    try:
        model, _, meta_data = build_cp_model(
            tasks_preprocessed, df_rooms, df_teachers, df_classes,
            room_capacity_dict_by_id, room_name_to_id_map,
            all_room_ids, rules
        )
    except Exception as e: print(f"构建 CP 模型时出错: {e}"); traceback.print_exc(); return None
    build_end = time.time(); print(f"Model Building completed in {build_end - build_start:.2f} seconds.")

    # --- 4. 求解 ---
    print("\n--- Step 4: Solving the Model ---")
    solver = cp_model.CpSolver();
    # --- 求解参数设置 ---
    solver.parameters.max_time_in_seconds = 1200.0 # 增加到 20 分钟
    solver.parameters.num_search_workers = 8    # 使用 8 核
    solver.parameters.log_search_progress = True
    # solver.parameters.relative_gap_limit = 0.01 # 优化目标差距限制示例
    # --- 结束参数设置 ---
    solve_start_time = time.time()
    status = cp_model.UNKNOWN
    try: status = solver.Solve(model)
    except Exception as e: print(f"调用 solver.Solve 时发生错误: {e}"); traceback.print_exc(); return None # Print traceback
    solve_end_time = time.time()
    status_name = solver.StatusName(status)
    print(f"Solving attempt finished in {solve_end_time - solve_start_time:.2f}s (Solver Wall Time: {solver.WallTime():.2f}s). Status: {status_name}")

    # --- 5. 处理结果 ---
    print("\n--- Step 5: Processing Results ---")
    process_start = time.time()
    result_data = {"status": status_name}
    solution_list = [] # 初始化
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"Solution found! Status: {status_name}");
        try:
             print(f"Objective value (minimized total overflow): {solver.ObjectiveValue()}")
        except Exception as e:
             print(f"Could not retrieve objective value: {e}")
        # 传递 room_id_to_name_map (确保 key 是 string)
        meta_data['room_id_to_name'] = {str(k): v for k, v in room_id_to_name_map.items()}
        solution_list = extract_solution(solver, None, meta_data)
        if solution_list:
            try:
                df_solution = pd.DataFrame(solution_list); df_solution.to_excel(output_file, index=False, engine='openpyxl')
                print(f"Solution successfully saved to {output_file}"); result_data["output_file"] = output_file
            except Exception as e: print(f"Error saving solution: {e}"); result_data["status"] = "ERROR_SAVING"
        else: print("Error: Solution extraction returned empty list despite Feasible/Optimal status."); result_data["status"] = "ERROR_EXTRACTING"
    # elif status == cp_model.INFEASIBLE: print("Solver proved infeasible...") # 已在求解后打印
    # elif status == cp_model.MODEL_INVALID: print("Error: Invalid model.") # 已在求解后打印
    # else: print(f"Solver finished: {status_name}. No solution found.") # 已在求解后打印

    process_end = time.time(); print(f"Result Processing completed in {process_end - process_start:.2f} seconds.")
    end_total_time = time.time(); print(f"\nTotal script execution time: {end_total_time - start_total_time:.2f} seconds.")
    return result_data

# ===================== 主程序入口 =====================
if __name__ == "__main__":
    print("========================================")
    print(" Starting Course Scheduling using CP-SAT (Filtered + Fixed)")
    print("========================================")
    final_result = run_cp_sat_scheduler()
    print("\n--- Final Summary ---")
    if final_result:
        print(f"Final Status: {final_result.get('status', 'N/A')}")
        if "output_file" in final_result:
            print(f"Output File: {final_result.get('output_file')}")
            print("\nNext Step: Check Excel for schedule and 'student_overflow'. Verify constraints.")
        elif final_result.get('status') == 'INFEASIBLE':
            print("The problem is infeasible for the filtered tasks and specified rules.")
        elif final_result.get('status') == 'NO_TASKS_TO_SCHEDULE':
             print("No tasks were available for scheduling after filtering.")
        else: print("Scheduler finished, but may not have produced a valid output file or solution.")
    else: print("Scheduler script failed to run completely or returned None.")
    print("========================================")