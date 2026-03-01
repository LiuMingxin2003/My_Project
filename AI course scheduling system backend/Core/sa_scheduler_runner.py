# ============================================================
# sa_scheduler_runner.py
# 使用模拟退火算法求解排课问题 (包含所有修正)
# 依赖: 算法1.py (提供加载和预处理功能)
#       scheduling_rules.json (提供规则)
import pandas as pd
import random
import time
from collections import defaultdict
from tqdm import tqdm
import numpy as np
import json
import math
import copy # 用于深拷贝个体
import traceback
from typing import Dict, List, Optional, Tuple, Any, Set

try:
    import 算法1
    required_funcs = ['load_teacher_info', 'load_class_info', 'load_room_info', 'load_task_info', 'preprocess_tasks']
    if not all(hasattr(算法1, fname) for fname in required_funcs):
        raise ImportError("算法1.py 文件缺少必要的加载或预处理函数。")
except ImportError as e:
    print(f"错误：无法导入或在 '算法1.py' 中找到必要函数: {e}")
    exit()
except Exception as e:
    print(f"导入或检查 '算法1.py' 时发生错误: {e}")
    exit()

# ===================== 模拟退火核心类 (包含所有修正) =====================
class SimulatedAnnealingScheduler:
    def __init__(self,
                 task_units: List[Dict[str, Any]],
                 rules: Dict[str, Any],
                 room_capacity_dict_by_id: Dict[str, int],
                 room_name_to_id_map: Dict[str, str],
                 room_id_to_name_map: Dict[str, str],
                 all_room_ids: List[str],
                 teacher_name_to_id: Dict[str, str],
                 # --- SA 参数 (需要仔细调整!) ---
                 initial_temp=10000.0,
                 cooling_rate=0.995,
                 min_temp=0.1,
                 max_iterations_per_temp=1500): # 增加每次迭代次数
        """初始化模拟退火调度器"""
        print(f"Initializing SAScheduler: T_init={initial_temp}, T_min={min_temp}, alpha={cooling_rate}, iters/temp={max_iterations_per_temp}")

        self.task_units = task_units
        if not self.task_units: raise ValueError("Task units list cannot be empty!")
        self.task_unit_lookup = {tu['task_unit_id']: tu for tu in self.task_units}

        self.rules = rules
        self.room_capacity_dict_by_id = room_capacity_dict_by_id
        self.room_name_to_id_map = room_name_to_id_map
        self.room_id_to_name_map = room_id_to_name_map
        self.all_room_ids = all_room_ids
        self.teacher_name_to_id = teacher_name_to_id
        self.teacher_id_to_name = {v:k for k,v in teacher_name_to_id.items()}

        self.time_slots = [(d, p) for d in range(5) for p in range(8)] # 保持 8 节课，如果需要晚上，这里要改
        self.num_time_slots = len(self.time_slots)
        self.periods_per_day = 8 # 保持 8 节课

        # SA 参数
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        self.min_temp = min_temp
        self.max_iterations_per_temp = max_iterations_per_temp

        # 从规则中提取常用设置
        self.basic_rules = self.rules.get('basic', {})
        self.apply_fixed_classroom = self.basic_rules.get('fixedClassroom', True)
        self.time_rules_set = set(self.basic_rules.get('timeRules', []))
        self.sport_afternoon_only = 'sportAfternoon' in self.time_rules_set
        self.teacher_limits_rule = {item['teacherId']: item['limits'] for item in self.rules.get('teacherLimits', [])}

        self.teacher_time_constraints = {}
        self._precompute_teacher_time_constraints()

        # 定义惩罚权重 (硬约束惩罚要远大于软约束)
        self.COST_HARD_CONSTRAINT_VIOLATION = 1000000 # 提高惩罚
        self.COST_CAPACITY_OVERFLOW_WEIGHT = 10      # 提高超员惩罚

    def _precompute_teacher_time_constraints(self):
        """根据 rules['teacherLimits'] 预计算教师时间限制"""
        for teacher_key, limits in self.teacher_limits_rule.items():
            teacher_id = None; teacher_id_str = str(teacher_key).strip()
            # 使用 self. 访问实例属性
            if teacher_id_str in self.teacher_id_to_name: teacher_id = teacher_id_str
            elif teacher_id_str in self.teacher_name_to_id: teacher_id = self.teacher_name_to_id[teacher_id_str]
            if teacher_id is None: continue
            allow_am = limits.get('morning', True)
            allow_pm = limits.get('afternoon', True)
            self.teacher_time_constraints[teacher_id] = {'allow_am': allow_am, 'allow_pm': allow_pm}

    def _get_valid_start_domain(self, task_unit) -> List[int]:
        """获取有效的开始时间索引列表"""
        duration = task_unit["duration"]; teacher_id = task_unit["teacher_id"]
        is_pe_course = task_unit.get("is_pe_course", False)
        if duration <= 0 or duration > self.num_time_slots: return []
        valid_starts = set(range(self.num_time_slots - duration + 1))
        teacher_constraints = self.teacher_time_constraints.get(teacher_id, {'allow_am': True, 'allow_pm': True})
        # 使用 self.time_slots 访问
        if not teacher_constraints['allow_am']: valid_starts = {s for s in valid_starts if not any(self.time_slots[s + i][1] < 4 for i in range(duration))}
        if not teacher_constraints['allow_pm']: valid_starts = {s for s in valid_starts if not any(self.time_slots[s + i][1] >= 4 for i in range(duration))}
        if is_pe_course and self.sport_afternoon_only: valid_starts = {s for s in valid_starts if all(self.time_slots[s + i][1] >= 4 for i in range(duration))}
        return sorted(list(valid_starts))

    def _generate_initial_solution(self) -> Dict[int, Tuple[int, str]]:
        """生成初始随机解"""
        individual = {}
        for task_unit in self.task_units:
            tu_id = task_unit["task_unit_id"]; duration = task_unit["duration"]; required_students = task_unit["total_students"]
            fixed_room_name = task_unit.get("fixed_room_name") if self.apply_fixed_classroom else None
            possible_room_ids = []; fixed_room_id = None
            if fixed_room_name:
                fixed_room_id = self.room_name_to_id_map.get(fixed_room_name)
                if fixed_room_id and fixed_room_id in self.room_capacity_dict_by_id: possible_room_ids = [fixed_room_id]
                else:
                     if self.apply_fixed_classroom: individual[tu_id] = (-1, "INVALID_FIXED_ROOM"); continue
                     else: possible_room_ids = self.all_room_ids
            else: possible_room_ids = self.all_room_ids
            if not possible_room_ids: individual[tu_id] = (-1, "NO_ROOM_FOUND"); continue
            # 初始化时优先选容量足够的
            sufficient_rooms = [rid for rid in possible_room_ids if self.room_capacity_dict_by_id.get(rid, 0) >= required_students]
            chosen_room_id = random.choice(sufficient_rooms) if sufficient_rooms else random.choice(possible_room_ids)
            valid_start_indices = self._get_valid_start_domain(task_unit)
            chosen_start_idx = random.choice(valid_start_indices) if valid_start_indices else (random.randint(0, self.num_time_slots - duration) if self.num_time_slots >= duration else 0)
            individual[tu_id] = (chosen_start_idx, chosen_room_id)
        return individual


    def calculate_cost(self, schedule: Dict[int, Tuple[int, str]]) -> float:
        """计算当前调度方案的总成本（惩罚值）"""
        # (与 RevisedGeneticScheduler 的 _calculate_fitness 逻辑相同，返回正值)
        total_penalty = 0.0
        teacher_schedule = defaultdict(list); room_schedule = defaultdict(list); class_schedule = defaultdict(list)
        teacher_weekly_tasks = defaultdict(int)
        for tu_id, assignment in schedule.items():
            task_unit = self.task_unit_lookup.get(tu_id)
            if not task_unit or assignment is None: total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION * 100; continue
            start_idx, room_id = assignment; duration = task_unit['duration']; end_idx = start_idx + duration
            teacher_id = task_unit['teacher_id']; class_list = task_unit.get('class_list', []); required_students = task_unit['total_students']
            fixed_room_name = task_unit.get('fixed_room_name') if self.apply_fixed_classroom else None
            is_pe_course = task_unit.get('is_pe_course', False)
            if start_idx < 0 or end_idx > self.num_time_slots or room_id not in self.room_capacity_dict_by_id: total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION * 100; continue
            current_interval = (start_idx, end_idx)
            for s, e in teacher_schedule[teacher_id]:
                 if max(start_idx, s) < min(end_idx, e): total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION
            teacher_schedule[teacher_id].append(current_interval)
            for s, e in room_schedule[room_id]:
                 if max(start_idx, s) < min(end_idx, e): total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION
            room_schedule[room_id].append(current_interval)
            for class_name in class_list:
                 if isinstance(class_name, str) and class_name:
                      for s, e in class_schedule[class_name]:
                           if max(start_idx, s) < min(end_idx, e): total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION
                      class_schedule[class_name].append(current_interval)
            if self.apply_fixed_classroom and fixed_room_name:
                 expected_room_id = self.room_name_to_id_map.get(fixed_room_name)
                 if expected_room_id and room_id != expected_room_id: total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION
            teacher_constraints = self.teacher_time_constraints.get(teacher_id)
            if teacher_constraints:
                 is_assigned_am = any(self.time_slots[start_idx + i][1] < 4 for i in range(duration) if 0 <= start_idx+i < self.num_time_slots)
                 is_assigned_pm = any(self.time_slots[start_idx + i][1] >= 4 for i in range(duration) if 0 <= start_idx+i < self.num_time_slots)
                 if not teacher_constraints['allow_am'] and is_assigned_am: total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION
                 if not teacher_constraints['allow_pm'] and is_assigned_pm: total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION
            if is_pe_course and self.sport_afternoon_only:
                 if any(self.time_slots[start_idx + i][1] < 4 for i in range(duration) if 0 <= start_idx+i < self.num_time_slots): total_penalty += self.COST_HARD_CONSTRAINT_VIOLATION
            room_cap = self.room_capacity_dict_by_id.get(room_id, 0)
            overflow = max(0, required_students - room_cap)
            total_penalty += overflow * self.COST_CAPACITY_OVERFLOW_WEIGHT
            teacher_weekly_tasks[teacher_id] += 1
        for teacher_id_key, limits in self.teacher_limits_rule.items():
             teacher_id_target = None; teacher_id_str = str(teacher_id_key).strip()
             if teacher_id_str in self.teacher_id_to_name: teacher_id_target = teacher_id_str
             elif teacher_id_str in self.teacher_name_to_id: teacher_id_target = self.teacher_name_to_id[teacher_id_str]
             if teacher_id_target is None: continue
             weekly_max = limits.get('weeklyMax')
             if weekly_max is not None and teacher_weekly_tasks.get(teacher_id_target, 0) > weekly_max:
                  overflow_tasks = teacher_weekly_tasks.get(teacher_id_target, 0) - weekly_max
                  total_penalty += overflow_tasks * self.COST_HARD_CONSTRAINT_VIOLATION
        return total_penalty # <<< 返回正的惩罚值 (成本)

    def _generate_neighbor(self, current_solution: Dict[int, Tuple[int, str]]) -> Dict[int, Tuple[int, str]]:
        """生成一个邻域解 (随机选择一个任务并改变其时间或教室) - 修正版"""
        neighbor = copy.deepcopy(current_solution)
        if not self.task_units: return neighbor

        valid_tu_ids = list(neighbor.keys())
        if not valid_tu_ids: return neighbor
        tu_id_to_change = random.choice(valid_tu_ids)

        task_unit = self.task_unit_lookup.get(tu_id_to_change)
        if not task_unit: return neighbor

        current_start, current_room_id = neighbor[tu_id_to_change]

        # *** 修正：分开获取有效开始时间和可选教室 ***
        valid_starts = self._get_valid_start_domain(task_unit)

        fixed_room_name = task_unit.get("fixed_room_name") if self.apply_fixed_classroom else None
        possible_room_ids = []
        if fixed_room_name:
            fixed_room_id = self.room_name_to_id_map.get(fixed_room_name)
            if fixed_room_id and fixed_room_id in self.room_capacity_dict_by_id:
                 possible_room_ids = [fixed_room_id]
            else: possible_room_ids = [current_room_id] if current_room_id in self.room_capacity_dict_by_id else []
        else: possible_room_ids = self.all_room_ids

        can_change_room = not fixed_room_name and len(possible_room_ids) > 1
        can_change_time = len(valid_starts) > 1

        if can_change_time and (not can_change_room or random.random() < 0.7): # 更大概率改时间
            choices = [s for s in valid_starts if s != current_start]
            if choices: new_start = random.choice(choices)
            else: new_start = current_start
            neighbor[tu_id_to_change] = (new_start, current_room_id)
        elif can_change_room: # 改教室
            choices = [rid for rid in possible_room_ids if rid != current_room_id]
            if choices: new_room_id = random.choice(choices)
            else: new_room_id = current_room_id
            neighbor[tu_id_to_change] = (current_start, new_room_id)
        # else: 无法改变

        return neighbor

    def run(self) -> tuple[Optional[Dict[int, Tuple[int, str]]], float]: # 使用 Optional, Tuple, Dict
        """执行模拟退火主流程"""
        print(f"Starting SA run: T_init={self.initial_temp}, T_min={self.min_temp}, alpha={self.cooling_rate}, iters/temp={self.max_iterations_per_temp}")
        start_run_time = time.time()

        current_solution = self._generate_initial_solution()
        current_cost = self.calculate_cost(current_solution)
        best_solution = copy.deepcopy(current_solution)
        best_cost = current_cost
        current_temp = self.initial_temp

        print(f"Initial cost: {current_cost:.2f}")

        generation = 0
        # TQDM for temperature steps
        temp_steps = 0
        if self.cooling_rate < 1 and self.initial_temp > self.min_temp :
             try:
                  temp_steps = int(math.log(self.min_temp / self.initial_temp) / math.log(self.cooling_rate))
             except ValueError: # Avoid log(0) or negative values
                  temp_steps = 1000 # Fallback large number
        elif self.initial_temp <= self.min_temp:
             temp_steps = 1
        else: # alpha >= 1, should not happen in typical SA
             temp_steps = self.generations # Use generations as a fallback limit


        with tqdm(total=temp_steps, desc="SA Temperature") as pbar_temp:
            while current_temp > self.min_temp:
                accepted_moves = 0
                for i in range(self.max_iterations_per_temp):
                    neighbor_solution = self._generate_neighbor(current_solution)
                    neighbor_cost = self.calculate_cost(neighbor_solution)
                    delta_cost = neighbor_cost - current_cost

                    if delta_cost < 0 or random.random() < math.exp(-delta_cost / current_temp):
                        current_solution = neighbor_solution
                        current_cost = neighbor_cost
                        accepted_moves += 1
                        if current_cost < best_cost:
                            best_solution = copy.deepcopy(current_solution)
                            best_cost = current_cost
                            print(f"\nNew best cost found: {best_cost:.2f} at Temp: {current_temp:.2f} (Iter {i})")
                            # if best_cost == 0: # 可选：找到0成本解提前结束
                            #    print("Feasible solution (0 cost) found by SA!")
                            #    break
                if best_cost == 0: break

                current_temp *= self.cooling_rate # 降温
                pbar_temp.update(1)
                pbar_temp.set_postfix({"Cost": f"{current_cost:.0f}", "Best": f"{best_cost:.0f}", "Accepts": f"{accepted_moves}"})


        end_run_time = time.time()
        print(f"\nSA run finished in {end_run_time - start_run_time:.2f} seconds.")
        # 再次计算最优成本以确保一致性
        if best_solution:
             best_cost = self.calculate_cost(best_solution)
        print(f"Final best cost (penalty) confirmed: {best_cost:.2f}")

        return best_solution, best_cost


# ===================== 主函数 (运行 SA) =====================
def main_sa():
    """主函数，运行模拟退火进行排课"""
    # --- 读取 JSON 规则 ---
    rules_file = "../../../../Documents/WeChat Files/wxid_1pibyllig21w21/FileStorage/File/2025-04/scheduling_rules.json"; rules = {}
    try:
        with open(rules_file, 'r', encoding='utf-8') as f: rules = json.load(f).get("schedulingRules", {})
        print(f"--- Loaded Scheduling Rules from {rules_file} ---")
    except Exception as e: print(f"Error loading rules: {e}. Using empty rules.")

    print("--- Starting Simulated Annealing Scheduler ---")
    start_total_time = time.time()

    # --- 文件路径 ---
    teacher_file = "教师信息.xlsx"; class_file = "班级数据.xls"; room_file = "教室信息.xls"; task_file = "排课任务.xlsx"
    output_file = "课程表方案_SA_MinPenalty.xlsx" # 新文件名

    # --- 1. 数据加载 (调用 算法1.py 中的函数) ---
    print("\n--- Step 1: Loading Data ---"); load_start = time.time()
    try:
        df_teachers = 算法1.load_teacher_info(teacher_file); df_classes = 算法1.load_class_info(class_file)
        df_rooms = 算法1.load_room_info(room_file); df_tasks = 算法1.load_task_info(task_file)
        if df_rooms.empty or df_teachers.empty or df_classes.empty or df_tasks.empty: return None
    except Exception as e: print(f"数据加载出错: {e}"); traceback.print_exc(); return None
    load_end = time.time(); print(f"Data Loading completed in {load_end - load_start:.2f} seconds.")

    # --- 1.5 创建查找字典 ---
    print("\n--- Step 1.5: Creating Lookups ---")
    try:
        room_capacity_dict_by_name = pd.Series(df_rooms.capacity.values, index=df_rooms.room_name).to_dict()
        room_capacity_dict_by_id = pd.Series(df_rooms.capacity.values, index=df_rooms.room_id).to_dict()
        room_name_to_id_map = pd.Series(df_rooms.room_id.values, index=df_rooms.room_name).to_dict()
        room_id_to_name_map = pd.Series(df_rooms.room_name.values, index=df_rooms.room_id).to_dict()
        all_room_ids = df_rooms["room_id"].tolist()
        max_overall_capacity = df_rooms['capacity'].max() if not df_rooms.empty else 0
        class_name_to_fixed_room_name = {}
        if '固定教室' in df_classes.columns and 'class_name' in df_classes.columns:
            for index, row in df_classes.iterrows():
                 class_name = row['class_name']; fixed_room_name = str(row['固定教室']).strip() if pd.notna(row['固定教室']) and str(row['固定教室']).strip() else None
                 if class_name and fixed_room_name:
                      if fixed_room_name not in room_capacity_dict_by_name: print(f"Warning: Fixed room name '{fixed_room_name}' ignored.")
                      else: class_name_to_fixed_room_name[class_name] = fixed_room_name
        teacher_name_to_id = pd.Series(df_teachers.teacher_id.values, index=df_teachers.teacher_name).to_dict()
        teacher_id_to_name = {v:k for k,v in teacher_name_to_id.items()}
    except Exception as e: print(f"创建查找字典时出错: {e}"); traceback.print_exc(); return None
    # --- 结束创建字典 ---

    # --- 2. 预处理 (调用 算法1.py 中的函数) ---
    print("\n--- Step 2: Preprocessing Tasks ---")
    preprocess_start = time.time()
    try:
        # *** 调用 算法1.py 中的 preprocess_tasks ***
        task_units = 算法1.preprocess_tasks(
            df_tasks, df_classes, df_teachers, df_rooms,
            room_capacity_dict_by_name, max_overall_capacity,
            class_name_to_fixed_room_name,
            rules
        )
        if task_units is None or not task_units: print("错误：预处理失败或未生成任务。"); return None
    except Exception as e: print(f"任务预处理出错: {e}"); traceback.print_exc(); return None
    preprocess_end = time.time(); print(f"Task Preprocessing completed in {preprocess_end - preprocess_start:.2f} seconds.")

    # --- 3. 初始化并运行模拟退火算法 ---
    print("\n--- Step 3: Running Simulated Annealing ---")
    sa_start = time.time()
    best_sa_solution = None; best_sa_cost = float('inf')
    try:
        scheduler = SimulatedAnnealingScheduler( # <<< 使用 SA 类
            task_units=task_units, rules=rules,
            room_capacity_dict_by_id=room_capacity_dict_by_id,
            room_name_to_id_map=room_name_to_id_map, room_id_to_name_map=room_id_to_name_map,
            all_room_ids=all_room_ids, teacher_name_to_id=teacher_name_to_id,
            # --- SA 参数 (可调整) ---
            initial_temp=100000.0, # 提高初始温度
            cooling_rate=0.997,   # 慢速冷却
            min_temp=0.01,
            max_iterations_per_temp=2000 # 增加迭代次数
            # ------------------------
        )
        best_sa_solution, best_sa_cost = scheduler.run()
    except Exception as e: print(f"模拟退火运行时出错: {e}"); traceback.print_exc()
    sa_end = time.time(); print(f"SA Execution completed in {sa_end - sa_start:.2f} seconds.")

    if not best_sa_solution: print("SA failed to produce a solution."); return None
    print(f"SA Best Cost (Penalty): {best_sa_cost:.2f}")

    # --- 4. 转换 SA 解为输出格式 ---
    print("\n--- Step 4: Converting SA Solution ---")
    solution_list = []
    final_calculated_overflow = 0
    task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units}
    time_slots = scheduler.time_slots

    for tu_id, assignment in best_sa_solution.items():
        if assignment is None: continue
        start_idx, room_id = assignment
        task_unit = task_unit_lookup.get(tu_id)
        if not task_unit or start_idx < 0 or isinstance(room_id, str) and room_id.startswith("NO_ROOM"): continue
        duration = task_unit["duration"]; required_students = task_unit["total_students"]
        room_cap = room_capacity_dict_by_id.get(room_id, 0); overflow = max(0, required_students - room_cap)
        room_name = room_id_to_name_map.get(room_id, str(room_id))
        is_first = True
        for i in range(duration):
            ts_idx = start_idx + i
            if 0 <= ts_idx < len(time_slots):
                day, period = time_slots[ts_idx]
                solution_list.append({
                    "task_unit_id": tu_id, "original_task_ref": task_unit.get("original_task_ref", "N/A"),
                    "block_index": task_unit.get("block_index", 0), "duration": duration,
                    "course_id": task_unit.get("course_id", "N/A"), "course_name": task_unit.get("course_name", "N/A"),
                    "teacher_id": task_unit.get("teacher_id", "N/A"), "class_list": task_unit.get("class_list", []),
                    "room_id": room_id, "room_name": room_name, "day_of_week": day, "period": period,
                    "is_start_period": (i == 0), "student_overflow": overflow
                })
                if is_first: final_calculated_overflow += overflow; is_first = False

    print(f"Solution conversion complete. Total calculated overflow: {final_calculated_overflow}")
    print(f"SA Best Cost (Penalty): {best_sa_cost}") # 再次打印最终成本

    # --- 5. 保存结果 ---
    print("\n--- Step 5: Saving Results ---")
    if solution_list:
        try:
            df_solution = pd.DataFrame(solution_list)
            df_solution.sort_values(by=['day_of_week', 'period', 'room_id', 'task_unit_id'], inplace=True)
            df_solution.to_excel(output_file, index=False)
            print(f"SA Solution successfully saved to {output_file}")
            result_data = {"status": "SA_Completed", "output_file": output_file, "best_cost": best_sa_cost, "calculated_overflow": final_calculated_overflow}
        except Exception as e: print(f"Error saving SA solution: {e}"); result_data = {"status": "ERROR_SAVING_SA", "best_cost": best_sa_cost}
    else: print("Error: No valid assignments found in the best SA solution."); result_data = {"status": "SA_NO_ASSIGNMENTS", "best_cost": best_sa_cost}

    end_total_time = time.time()
    print(f"\nTotal SA script execution time: {end_total_time - start_total_time:.2f} seconds.")
    return result_data

# --- 主程序入口 ---
if __name__ == "__main__":
    print("========================================")
    print(" Starting Course Scheduling using SIMULATED ANNEALING") # 更新标题
    print("========================================")
    final_result = main_sa() # 调用 SA 主函数
    print("\n--- Final Summary ---")
    if final_result:
        print(f"Final Status: {final_result.get('status', 'N/A')}")
        if "output_file" in final_result:
            print(f"Output File: {final_result.get('output_file')}")
            print(f"Best Cost (Penalty): {final_result.get('best_cost', 'N/A'):.2f}")
            print(f"Calculated Overflow in Best Solution: {final_result.get('calculated_overflow', 'N/A')}")
            print("\nNext Step: Check Excel for schedule and 'student_overflow'. Use Check.py VERY carefully to verify hard constraints.")
        else: print("SA finished, but may not have produced an output file.")
    else: print("SA Scheduler script failed to run completely.")
    print("========================================")