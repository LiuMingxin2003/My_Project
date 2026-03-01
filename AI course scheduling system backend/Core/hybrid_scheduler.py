# ============================================================
# hybrid_scheduler.py
# 混合策略：遗传算法 + CP-SAT 修复器 (包含所有 Pylance 错误修正)
# 依赖: 算法1.py (提供加载和预处理功能)
#       scheduling_rules.json (提供规则)
# 版本: v_final_hybrid_fixed
# ============================================================
import pandas as pd
import random
import time
from collections import defaultdict
from tqdm import tqdm
import numpy as np
import json
import math
import copy # 用于深拷贝个体
import traceback # <<< 修正：添加导入
from typing import Dict, List, Optional, Tuple, Any, Set # <<< 修正：添加导入

# 导入 CP-SAT
from ortools.sat.python import cp_model

# 导入算法1中的函数
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

# ===================== 遗传算法核心类 (包含 Pylance 修正) =====================
class RevisedGeneticScheduler:
    def __init__(self,
                 task_units: List[Dict[str, Any]],
                 rules: Dict[str, Any],
                 room_capacity_dict_by_id: Dict[str, int],
                 room_name_to_id_map: Dict[str, str],
                 room_id_to_name_map: Dict[str, str],
                 all_room_ids: List[str],
                 teacher_name_to_id: Dict[str, str],
                 pop_size=200, elite_ratio=0.1, mutation_rate=0.15, crossover_rate=0.85, generations=500):
        print(f"Initializing RevisedGeneticScheduler: pop_size={pop_size}, generations={generations}, elite%={elite_ratio*100}, mutation%={mutation_rate*100}")
        self.task_units = task_units
        if not self.task_units: raise ValueError("Task units list cannot be empty!")
        self.task_unit_lookup = {tu['task_unit_id']: tu for tu in self.task_units}
        self.rules = rules
        self.room_capacity_dict_by_id = room_capacity_dict_by_id
        self.room_name_to_id_map = room_name_to_id_map
        self.room_id_to_name_map = room_id_to_name_map
        self.all_room_ids = all_room_ids
        self.teacher_name_to_id = teacher_name_to_id # <<< 实例属性
        self.teacher_id_to_name = {v:k for k,v in teacher_name_to_id.items()} # <<< 实例属性
        self.time_slots = [(d, p) for d in range(5) for p in range(8)]
        self.num_time_slots = len(self.time_slots)
        self.periods_per_day = 8
        self.pop_size = pop_size
        self.elite_size = int(pop_size * elite_ratio)
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.generations = generations
        self.basic_rules = self.rules.get('basic', {})
        self.apply_fixed_classroom = self.basic_rules.get('fixedClassroom', True) # <<< 实例属性
        self.time_rules_set = set(self.basic_rules.get('timeRules', []))
        self.sport_afternoon_only = 'sportAfternoon' in self.time_rules_set
        self.teacher_limits_rule = {item['teacherId']: item['limits'] for item in self.rules.get('teacherLimits', [])}
        self.teacher_time_constraints = {} # <<< 实例属性
        self._precompute_teacher_time_constraints()
        self.PENALTY_HARD_CONSTRAINT_VIOLATION = 100000
        self.PENALTY_CAPACITY_OVERFLOW_WEIGHT = 5

    def _precompute_teacher_time_constraints(self):
        for teacher_key, limits in self.teacher_limits_rule.items():
            teacher_id = None; teacher_id_str = str(teacher_key).strip()
            # *** 修正：使用 self. 访问实例属性 ***
            if teacher_id_str in self.teacher_id_to_name: teacher_id = teacher_id_str
            elif teacher_id_str in self.teacher_name_to_id: teacher_id = self.teacher_name_to_id[teacher_id_str]
            if teacher_id is None: continue
            allow_am = limits.get('morning', True)
            allow_pm = limits.get('afternoon', True)
            self.teacher_time_constraints[teacher_id] = {'allow_am': allow_am, 'allow_pm': allow_pm}

    def _get_valid_start_domain(self, task_unit) -> List[int]:
        duration = task_unit["duration"]; teacher_id = task_unit["teacher_id"]
        is_pe_course = task_unit.get("is_pe_course", False)
        if duration <= 0 or duration > self.num_time_slots: return []
        valid_starts = set(range(self.num_time_slots - duration + 1))
        # *** 修正：使用 self. 访问实例属性 ***
        teacher_constraints = self.teacher_time_constraints.get(teacher_id, {'allow_am': True, 'allow_pm': True})
        if not teacher_constraints['allow_am']: valid_starts = {s for s in valid_starts if not any(self.time_slots[s + i][1] < 4 for i in range(duration))}
        if not teacher_constraints['allow_pm']: valid_starts = {s for s in valid_starts if not any(self.time_slots[s + i][1] >= 4 for i in range(duration))}
        if is_pe_course and self.sport_afternoon_only: valid_starts = {s for s in valid_starts if all(self.time_slots[s + i][1] >= 4 for i in range(duration))}
        return sorted(list(valid_starts))

    def _initialize_individual(self) -> Dict[int, Tuple[int, str]]:
        individual = {}
        for task_unit in self.task_units:
            tu_id = task_unit["task_unit_id"]; duration = task_unit["duration"]; required_students = task_unit["total_students"]
            # *** 修正：使用 self.apply_fixed_classroom ***
            fixed_room_name = task_unit.get("fixed_room_name") if self.apply_fixed_classroom else None
            possible_room_ids = []; fixed_room_id = None
            if fixed_room_name:
                 # *** 修正：使用 self. 访问实例属性 ***
                fixed_room_id = self.room_name_to_id_map.get(fixed_room_name)
                if fixed_room_id and fixed_room_id in self.room_capacity_dict_by_id:
                     possible_room_ids = [fixed_room_id]
                else:
                     # *** 修正：使用 self.apply_fixed_classroom ***
                     if self.apply_fixed_classroom: individual[tu_id] = (-1, "INVALID_FIXED_ROOM"); continue
                     else: possible_room_ids = self.all_room_ids
            else: possible_room_ids = self.all_room_ids
            if not possible_room_ids: individual[tu_id] = (-1, "NO_ROOM_FOUND"); continue
            sufficient_rooms = [rid for rid in possible_room_ids if self.room_capacity_dict_by_id.get(rid, 0) >= required_students]
            if sufficient_rooms: chosen_room_id = random.choice(sufficient_rooms)
            elif possible_room_ids: chosen_room_id = random.choice(possible_room_ids)
            else: individual[tu_id] = (-1, "NO_ROOM_LOGIC_ERROR"); continue
            valid_start_indices = self._get_valid_start_domain(task_unit)
            if not valid_start_indices: chosen_start_idx = random.randint(0, self.num_time_slots - duration) if self.num_time_slots >= duration else 0
            else: chosen_start_idx = random.choice(valid_start_indices)
            individual[tu_id] = (chosen_start_idx, chosen_room_id)
        return individual

    def _calculate_fitness(self, individual: Dict[int, Tuple[int, str]]) -> float:
        total_penalty = 0.0
        teacher_schedule = defaultdict(list); room_schedule = defaultdict(list); class_schedule = defaultdict(list)
        teacher_weekly_tasks = defaultdict(int)
        for tu_id, assignment in individual.items():
            task_unit = self.task_unit_lookup.get(tu_id)
            if not task_unit or assignment is None: total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION * 100; continue
            start_idx, room_id = assignment; duration = task_unit['duration']; end_idx = start_idx + duration
            teacher_id = task_unit['teacher_id']; class_list = task_unit.get('class_list', []); required_students = task_unit['total_students']
            # *** 修正：使用 self.apply_fixed_classroom ***
            fixed_room_name = task_unit.get('fixed_room_name') if self.apply_fixed_classroom else None
            is_pe_course = task_unit.get('is_pe_course', False)
            if start_idx < 0 or end_idx > self.num_time_slots or room_id not in self.room_capacity_dict_by_id: total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION * 100; continue
            current_interval = (start_idx, end_idx)
            for s, e in teacher_schedule[teacher_id]:
                 if max(start_idx, s) < min(end_idx, e): total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION
            teacher_schedule[teacher_id].append(current_interval)
            for s, e in room_schedule[room_id]:
                 if max(start_idx, s) < min(end_idx, e): total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION
            room_schedule[room_id].append(current_interval)
            for class_name in class_list:
                 if isinstance(class_name, str) and class_name:
                      for s, e in class_schedule[class_name]:
                           if max(start_idx, s) < min(end_idx, e): total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION
                      class_schedule[class_name].append(current_interval)
            # *** 修正：使用 self.apply_fixed_classroom ***
            if self.apply_fixed_classroom and fixed_room_name:
                 expected_room_id = self.room_name_to_id_map.get(fixed_room_name)
                 if expected_room_id and room_id != expected_room_id: total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION
            # *** 修正：使用 self.teacher_time_constraints ***
            teacher_constraints = self.teacher_time_constraints.get(teacher_id)
            if teacher_constraints:
                 is_assigned_am = any(self.time_slots[start_idx + i][1] < 4 for i in range(duration) if 0 <= start_idx+i < self.num_time_slots)
                 is_assigned_pm = any(self.time_slots[start_idx + i][1] >= 4 for i in range(duration) if 0 <= start_idx+i < self.num_time_slots)
                 if not teacher_constraints['allow_am'] and is_assigned_am: total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION
                 if not teacher_constraints['allow_pm'] and is_assigned_pm: total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION
            # *** 修正：使用 self.sport_afternoon_only ***
            if is_pe_course and self.sport_afternoon_only:
                 if any(self.time_slots[start_idx + i][1] < 4 for i in range(duration) if 0 <= start_idx+i < self.num_time_slots): total_penalty += self.PENALTY_HARD_CONSTRAINT_VIOLATION
            room_cap = self.room_capacity_dict_by_id.get(room_id, 0)
            overflow = max(0, required_students - room_cap)
            total_penalty += overflow * self.PENALTY_CAPACITY_OVERFLOW_WEIGHT
            teacher_weekly_tasks[teacher_id] += 1
        for teacher_id_key, limits in self.teacher_limits_rule.items():
             teacher_id_target = None; teacher_id_str = str(teacher_id_key).strip()
             # *** 修正：使用 self. 访问实例属性 ***
             if teacher_id_str in self.teacher_id_to_name: teacher_id_target = teacher_id_str
             elif teacher_id_str in self.teacher_name_to_id: teacher_id_target = self.teacher_name_to_id[teacher_id_str]
             if teacher_id_target is None: continue
             weekly_max = limits.get('weeklyMax')
             if weekly_max is not None and teacher_weekly_tasks.get(teacher_id_target, 0) > weekly_max:
                  overflow_tasks = teacher_weekly_tasks.get(teacher_id_target, 0) - weekly_max
                  total_penalty += overflow_tasks * self.PENALTY_TEACHER_LOAD_VIOLATION
        return -total_penalty

    def _crossover(self, parent1: Dict, parent2: Dict) -> Dict: # 使用 Dict
        child = {}; keys = list(parent1.keys())
        if len(keys) <= 1: return parent1.copy()
        cross_point = random.randint(1, len(keys) - 1)
        for i, key in enumerate(keys): child[key] = parent1[key] if i < cross_point else parent2[key]
        for key in keys:
             if key not in child: child[key] = parent2[key] if i < cross_point else parent1[key] # Ensure all keys
        return child

    def _mutate(self, individual: Dict) -> Dict: # 使用 Dict
        mutated_individual = copy.deepcopy(individual)
        keys_to_mutate = [key for key in mutated_individual if random.random() < self.mutation_rate]
        task_unit_lookup = {tu['task_unit_id']: tu for tu in self.task_units}
        for tu_id in keys_to_mutate:
            task_unit = task_unit_lookup.get(tu_id)
            if not task_unit: continue
            current_start, current_room_id = mutated_individual[tu_id]
            if random.random() < 0.5: # Mutate time
                valid_starts = self._get_valid_start_domain(task_unit) # <<< 使用修正后的方法
                if len(valid_starts) > 1:
                    choices = [s for s in valid_starts if s != current_start]
                    if choices: new_start = random.choice(choices)
                    else: new_start = current_start
                    mutated_individual[tu_id] = (new_start, current_room_id)
            else: # Mutate room
                # *** 修正：使用 self.apply_fixed_classroom ***
                fixed_room_name = task_unit.get("fixed_room_name") if self.apply_fixed_classroom else None
                if fixed_room_name: continue # Don't mutate fixed room
                # *** 修正：使用 self.all_room_ids ***
                possible_room_ids = self.all_room_ids
                if len(possible_room_ids) > 1:
                    choices = [rid for rid in possible_room_ids if rid != current_room_id]
                    if choices: new_room_id = random.choice(choices)
                    else: new_room_id = current_room_id
                    mutated_individual[tu_id] = (current_start, new_room_id)
        return mutated_individual

    def run(self) -> tuple[Optional[Dict], float]: # 使用 Optional[Dict]
        # ... (run 方法的主体，包括调用 _calculate_fitness, _crossover, _mutate 的部分保持不变) ...
        print(f"Starting GA run ({self.generations} generations, {self.pop_size} population)...")
        population = [self._initialize_individual() for _ in range(self.pop_size)]
        best_fitness_overall = -float('inf'); best_individual_overall = None
        start_run_time = time.time()
        for generation in tqdm(range(self.generations), desc="GA Generations"):
            fitness = []
            for ind_idx, ind in enumerate(population):
                try: fit = self._calculate_fitness(ind)
                except Exception as e: print(f"\nError calculating fitness: {e}"); fit = -float('inf')
                fitness.append(fit)
            current_best_idx = np.argmax(fitness); current_best_fitness = fitness[current_best_idx]
            if current_best_fitness > best_fitness_overall:
                best_fitness_overall = current_best_fitness; best_individual_overall = copy.deepcopy(population[current_best_idx])
                if (generation + 1) % 10 == 0: print(f"\nGen {generation+1}: New best fitness = {best_fitness_overall:.2f}")
                if best_fitness_overall >= 0: print("Feasible solution (0 penalty) found by GA!"); break
            elif (generation + 1) % 50 == 0: print(f"Gen {generation+1}: Best fitness in pop = {current_best_fitness:.2f} (Overall best = {best_fitness_overall:.2f})")
            elite_indices = np.argsort(fitness)[-self.elite_size:]; elites = [copy.deepcopy(population[i]) for i in elite_indices]
            new_population = elites
            while len(new_population) < self.pop_size:
                t_size = min(5, self.pop_size)
                p1_idx = max(random.sample(range(self.pop_size), t_size), key=lambda i: fitness[i])
                p2_idx = max(random.sample(range(self.pop_size), t_size), key=lambda i: fitness[i])
                parent1 = population[p1_idx]; parent2 = population[p2_idx]
                if random.random() < self.crossover_rate: child = self._crossover(parent1, parent2)
                else: child = copy.deepcopy(random.choice([parent1, parent2]))
                mutated_child = self._mutate(child); new_population.append(mutated_child)
            population = new_population
        end_run_time = time.time(); print(f"\nGA run finished in {end_run_time - start_run_time:.2f} seconds.")
        if best_individual_overall is None and population: final_fitness = [self._calculate_fitness(ind) for ind in population]; final_best_idx = np.argmax(final_fitness); best_individual_overall = population[final_best_idx]; best_fitness_overall = final_fitness[final_best_idx]
        elif best_individual_overall: best_fitness_overall = self._calculate_fitness(best_individual_overall)
        else: return None, -float('inf')
        print(f"Final best fitness confirmed: {best_fitness_overall:.2f}")
        return best_individual_overall, best_fitness_overall


# ===================== 冲突检测函数 (不变) =====================
# (保持上次的 detect_conflicts 函数)
def detect_conflicts(schedule: Dict[int, Tuple[int, str]], task_units: List[Dict[str, Any]], rules: Dict[str, Any], room_capacity_dict_by_id: Dict[str, int], room_name_to_id_map: Dict[str, str], teacher_id_to_name: Dict[str, str], teacher_time_constraints: Dict[str, Dict[str, bool]]) -> Tuple[List[Dict], Set[int]]:
    print("\n--- Detecting Hard Conflicts in GA Solution ---")
    conflicts = []; conflicting_task_unit_ids = set()
    task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units}
    time_slots = [(d, p) for d in range(5) for p in range(8)]; num_time_slots = len(time_slots)
    basic_rules = rules.get('basic', {}); apply_fixed_classroom = basic_rules.get('fixedClassroom', True)
    time_rules_set = set(basic_rules.get('timeRules', [])); sport_afternoon_only = 'sportAfternoon' in time_rules_set
    teacher_limits_rule = {item['teacherId']: item['limits'] for item in rules.get('teacherLimits', [])}
    teacher_schedule = defaultdict(list); room_schedule = defaultdict(list); class_schedule = defaultdict(list)
    teacher_weekly_tasks = defaultdict(int); checked_overlaps = defaultdict(set)

    for tu_id, assignment in schedule.items():
        task_unit = task_unit_lookup.get(tu_id)
        if not task_unit or assignment is None: continue
        start_idx, room_id = assignment; duration = task_unit['duration']; end_idx = start_idx + duration
        teacher_id = task_unit['teacher_id']; class_list = task_unit.get('class_list', [])
        fixed_room_name = task_unit.get('fixed_room_name') if apply_fixed_classroom else None
        is_pe_course = task_unit.get('is_pe_course', False)
        if start_idx < 0 or end_idx > num_time_slots or room_id not in room_capacity_dict_by_id: conflicts.append({'type': 'Invalid Assignment', 'task_unit_id': tu_id}); conflicting_task_unit_ids.add(tu_id); continue
        current_interval = (start_idx, end_idx, tu_id)
        for s, e, other_tu_id in teacher_schedule[teacher_id]:
             if max(start_idx, s) < min(end_idx, e): conflict_pair = tuple(sorted((tu_id, other_tu_id)));
             if conflict_pair not in checked_overlaps['teacher']: conflicts.append({'type': 'Teacher Conflict', 'teacher_id': teacher_id, 'tasks': [tu_id, other_tu_id]}); conflicting_task_unit_ids.add(tu_id); conflicting_task_unit_ids.add(other_tu_id); checked_overlaps['teacher'].add(conflict_pair)
        teacher_schedule[teacher_id].append(current_interval)
        for s, e, other_tu_id in room_schedule[room_id]:
             if max(start_idx, s) < min(end_idx, e): conflict_pair = tuple(sorted((tu_id, other_tu_id)));
             if conflict_pair not in checked_overlaps['room']: conflicts.append({'type': 'Room Conflict', 'room_id': room_id, 'tasks': [tu_id, other_tu_id]}); conflicting_task_unit_ids.add(tu_id); conflicting_task_unit_ids.add(other_tu_id); checked_overlaps['room'].add(conflict_pair)
        room_schedule[room_id].append(current_interval)
        for class_name in class_list:
            if isinstance(class_name, str) and class_name:
                for s, e, other_tu_id in class_schedule[class_name]:
                     if max(start_idx, s) < min(end_idx, e): conflict_pair = tuple(sorted((tu_id, other_tu_id)));
                     if conflict_pair not in checked_overlaps[f'class_{class_name}']: conflicts.append({'type': 'Class Conflict', 'class_name': class_name, 'tasks': [tu_id, other_tu_id]}); conflicting_task_unit_ids.add(tu_id); conflicting_task_unit_ids.add(other_tu_id); checked_overlaps[f'class_{class_name}'].add(conflict_pair)
                class_schedule[class_name].append(current_interval)
        if apply_fixed_classroom and fixed_room_name:
            expected_room_id = room_name_to_id_map.get(fixed_room_name)
            if not expected_room_id or room_id != expected_room_id: conflicts.append({'type': 'Fixed Room Violation', 'task_unit_id': tu_id}); conflicting_task_unit_ids.add(tu_id)
        teacher_constraints = teacher_time_constraints.get(teacher_id)
        if teacher_constraints:
            is_assigned_am = any(time_slots[start_idx + i][1] < 4 for i in range(duration) if 0 <= start_idx+i < num_time_slots)
            is_assigned_pm = any(time_slots[start_idx + i][1] >= 4 for i in range(duration) if 0 <= start_idx+i < num_time_slots)
            if not teacher_constraints['allow_am'] and is_assigned_am: conflicts.append({'type': 'Teacher Time Violation', 'task_unit_id': tu_id}); conflicting_task_unit_ids.add(tu_id)
            if not teacher_constraints['allow_pm'] and is_assigned_pm: conflicts.append({'type': 'Teacher Time Violation', 'task_unit_id': tu_id}); conflicting_task_unit_ids.add(tu_id)
        if is_pe_course and sport_afternoon_only:
            if any(time_slots[start_idx + i][1] < 4 for i in range(duration) if 0 <= start_idx+i < num_time_slots): conflicts.append({'type': 'PE Time Violation', 'task_unit_id': tu_id}); conflicting_task_unit_ids.add(tu_id)
        teacher_weekly_tasks[teacher_id] += 1
    for teacher_id_key, limits in teacher_limits_rule.items():
         teacher_id_target = None; teacher_id_str = str(teacher_id_key).strip()
         if teacher_id_str in teacher_id_to_name: teacher_id_target = teacher_id_str
         elif teacher_id_str in teacher_name_to_id: teacher_id_target = teacher_name_to_id[teacher_id_str]
         if teacher_id_target is None: continue
         weekly_max = limits.get('weeklyMax')
         if weekly_max is not None and teacher_weekly_tasks.get(teacher_id_target, 0) > weekly_max:
              conflicts.append({'type': 'Teacher Load Violation', 'teacher_id': teacher_id_target, 'limit_type': 'weekly'})
              for tu_id, assignment in schedule.items(): # Mark all tasks by this teacher as conflicting
                   if task_unit_lookup.get(tu_id, {}).get('teacher_id') == teacher_id_target: conflicting_task_unit_ids.add(tu_id)
         # (Daily/AM/PM limits not checked here)
    print(f"Conflict detection finished. Found {len(conflicts)} hard conflicts involving {len(conflicting_task_unit_ids)} task units.")
    return conflicts, conflicting_task_unit_ids


# ===================== CP-SAT 修复器函数 (修正参数传递) =====================
def build_and_solve_cp_repair_model(
                    original_schedule: Dict[int, Tuple[int, str]],
                    conflicting_tu_ids: Set[int],
                    task_units: List[Dict[str, Any]],
                    rules: Dict[str, Any],
                    room_capacity_dict_by_id: Dict[str, int],
                    room_name_to_id_map: Dict[str, str],
                    all_room_ids: List[str],
                    df_teachers: pd.DataFrame, # 需要教师信息
                    df_classes: pd.DataFrame,  # 需要班级信息
                    # *** 添加缺失的参数 ***
                    time_slots: List[Tuple[int, int]],
                    num_time_slots: int,
                    teacher_id_to_name: Dict[str, str],
                    teacher_time_constraints: Dict[str, Dict[str, bool]]
                    ) -> Optional[Dict[int, Tuple[int, str]]]:
    """
    构建并求解 CP-SAT 子模型来修复冲突 (简化版)。
    """
    print(f"\n--- Attempting CP-SAT Repair for {len(conflicting_tu_ids)} conflicting task units ---")
    if not conflicting_tu_ids: return {}

    model = cp_model.CpModel(); solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0 # 修复时间限制
    solver.parameters.log_search_progress = False

    task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units}
    basic_rules = rules.get('basic', {}); apply_fixed_classroom = basic_rules.get('fixedClassroom', True)
    time_rules_set = set(basic_rules.get('timeRules', [])); sport_afternoon_only = 'sportAfternoon' in time_rules_set
    teacher_limits_rule = {item['teacherId']: item['limits'] for item in rules.get('teacherLimits', [])}

    # --- 变量创建 (只为冲突的任务) ---
    all_intervals_repair = defaultdict(dict)
    presence_literals_repair = defaultdict(list)
    overflow_vars_repair = []
    possible_to_schedule_conflicting = True # 标记是否所有冲突任务都有可能安排

    print(f"Creating repair variables for {len(conflicting_tu_ids)} task units...")
    morning_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if p < 4}
    afternoon_slots = {ts_idx for ts_idx, (d, p) in enumerate(time_slots) if p >= 4}

    for tu_id in conflicting_tu_ids:
        task_unit = task_unit_lookup.get(tu_id)
        if not task_unit: continue
        duration = task_unit["duration"]; required_students = task_unit["total_students"]
        teacher_id = task_unit["teacher_id"]; fixed_room_name = task_unit.get("fixed_room_name") if apply_fixed_classroom else None
        is_pe_course = task_unit.get("is_pe_course", False)

        if duration <= 0 or duration > num_time_slots: continue

        possible_room_ids = []
        if fixed_room_name:
            fixed_room_id = room_name_to_id_map.get(fixed_room_name)
            if fixed_room_id and fixed_room_id in room_capacity_dict_by_id: possible_room_ids = [fixed_room_id]
            else: possible_to_schedule_conflicting = False; break # 固定教室无效，无法修复
        else: possible_room_ids = all_room_ids
        if not possible_room_ids: possible_to_schedule_conflicting = False; break

        task_presences = []
        # *** 修正：使用传入的 teacher_time_constraints ***
        teacher_constraints = teacher_time_constraints.get(teacher_id, {'allow_am': True, 'allow_pm': True})
        for room_id in possible_room_ids:
            room_cap = room_capacity_dict_by_id.get(room_id, 0)
            overflow_amount = max(0, required_students - room_cap)

            valid_starts = set(range(num_time_slots - duration + 1))
            if not teacher_constraints['allow_am']: valid_starts = {s for s in valid_starts if not any(time_slots[s + i][1] < 4 for i in range(duration))}
            if not teacher_constraints['allow_pm']: valid_starts = {s for s in valid_starts if not any(time_slots[s + i][1] >= 4 for i in range(duration))}
            if is_pe_course and sport_afternoon_only: valid_starts = {s for s in valid_starts if all(time_slots[s + i][1] >= 4 for i in range(duration))}
            if not valid_starts: continue
            start_domain = cp_model.Domain.FromValues(list(valid_starts))

            presence_var = model.NewBoolVar(f'presence_repair_{tu_id}_{room_id}')
            start_var = model.NewIntVarFromDomain(start_domain, f'start_repair_{tu_id}_{room_id}')
            interval_var = model.NewOptionalFixedSizeIntervalVar(start=start_var, size=duration, is_present=presence_var, name=f'interval_repair_{tu_id}_{room_id}')
            all_intervals_repair[(tu_id, room_id)] = interval_var
            task_presences.append(presence_var)
            overflow_var = model.NewIntVar(0, overflow_amount, f'overflow_repair_{tu_id}_{room_id}')
            model.Add(overflow_var == overflow_amount).OnlyEnforceIf(presence_var)
            model.Add(overflow_var == 0).OnlyEnforceIf(presence_var.Not())
            overflow_vars_repair.append(overflow_var)

        if not task_presences: possible_to_schedule_conflicting = False; break # 如果某个冲突任务找不到任何有效安排
        presence_literals_repair[tu_id] = task_presences

    if not possible_to_schedule_conflicting:
         print("CP Repair Error: At least one conflicting task unit has no valid placement options. Cannot repair.")
         return None

    print(f"Created repair variables.")

    # --- 添加约束 ---
    # 1. 每个冲突任务必须分配一次
    for tu_id in conflicting_tu_ids:
        if tu_id in presence_literals_repair and presence_literals_repair[tu_id]:
             model.AddExactlyOne(presence_literals_repair[tu_id])

    # 2. NoOverlap 约束 (!!!极其简化，仅考虑冲突任务之间!!!)
    print("  - Adding simplified NoOverlap constraints for repairing tasks...")
    intervals_in_room_repair = defaultdict(list); intervals_for_teacher_repair = defaultdict(list); intervals_for_class_repair = defaultdict(list)
    for (tu_id, room_id), interval_var in all_intervals_repair.items():
         if tu_id in conflicting_tu_ids: # 只添加冲突任务的 interval
              task_unit = task_unit_lookup.get(tu_id);
              if not task_unit: continue
              teacher_id = task_unit["teacher_id"]; class_list = task_unit.get("class_list", [])
              intervals_in_room_repair[room_id].append(interval_var)
              intervals_for_teacher_repair[teacher_id].append(interval_var)
              for class_name in class_list:
                   if isinstance(class_name, str) and class_name: intervals_for_class_repair[class_name].append(interval_var)
    for intervals in intervals_in_room_repair.values(): model.AddNoOverlap(intervals)
    for intervals in intervals_for_teacher_repair.values(): model.AddNoOverlap(intervals)
    for intervals in intervals_for_class_repair.values(): model.AddNoOverlap(intervals)
    print("    - Applied simplified NoOverlap (WARNING: Interactions with fixed tasks NOT fully checked)")

    # 3. 目标：可行性优先，可加入最小化超员
    if overflow_vars_repair:
         total_overflow_repair = model.NewIntVar(0, sum(v.Proto().domain[-1] for v in overflow_vars_repair), 'total_overflow_repair')
         model.Add(total_overflow_repair == sum(overflow_vars_repair))
         model.Minimize(total_overflow_repair)

    # --- 求解修复模型 ---
    print("Solving repair subproblem...")
    status = solver.Solve(model)
    print(f"Repair solver status: {solver.StatusName()}")

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        repaired_assignments = {}
        for (tu_id, room_id), interval_var in all_intervals_repair.items():
             # 确保只提取正在修复的任务的结果
             if tu_id in conflicting_tu_ids and solver.Value(interval_var.PresenceLiteral()) == 1:
                 start_idx = solver.Value(interval_var.StartExpr())
                 repaired_assignments[tu_id] = (start_idx, room_id)
        print(f"Repair successful, found new assignments for {len(repaired_assignments)} task units.")
        # 验证是否所有冲突任务都被重新分配了
        if len(repaired_assignments) != len(conflicting_tu_ids):
             print("Warning: Not all conflicting tasks were reassigned during repair.")
             # 你可能需要决定如何处理未被修复的任务（例如保留GA的解，或标记为失败）
             # 为了简单，我们只返回成功修复的部分
        return repaired_assignments
    else:
        print("CP-SAT repair failed to find a feasible solution for the conflicting tasks.")
        return None


# ===================== 主函数 (运行 GA + CP Repair) =====================
def main_hybrid():
    """主函数，运行 GA + CP Repair"""
    # --- 1. 加载规则和数据 ---
    rules_file = "scheduling_rules.json"; rules = {}
    try:
        with open(rules_file, 'r', encoding='utf-8') as f: rules = json.load(f).get("schedulingRules", {})
        print(f"--- Loaded Scheduling Rules from {rules_file} ---")
    except Exception as e: print(f"Error loading rules: {e}. Using empty rules.")

    print("--- Starting Hybrid Scheduler (GA + CP Repair) ---")
    start_total_time = time.time()
    teacher_file = "教师信息.xlsx"; class_file = "班级数据.xls"; room_file = "教室信息.xls"; task_file = "排课任务.xlsx"
    output_file_ga = "课程表方案_GA_Initial.xlsx" # GA 初始解
    output_file_final = "课程表方案_Hybrid_Repaired.xlsx" # 修复后最终解

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
        teacher_id_to_name = {v:k for k,v in teacher_name_to_id.items()} # <<< 需要这个
    except Exception as e: print(f"创建查找字典时出错: {e}"); traceback.print_exc(); return None
    # --- 结束创建字典 ---

    # --- 2. 预处理 (调用 算法1.py 中的函数) ---
    print("\n--- Step 2: Preprocessing Tasks ---")
    preprocess_start = time.time()
    try:
        task_units = 算法1.preprocess_tasks(
            df_tasks, df_classes, df_teachers, df_rooms,
            room_capacity_dict_by_name, max_overall_capacity,
            class_name_to_fixed_room_name,
            rules
        )
        if task_units is None or not task_units: print("错误：预处理失败或未生成任务。"); return None
    except Exception as e: print(f"任务预处理出错: {e}"); traceback.print_exc(); return None
    preprocess_end = time.time(); print(f"Task Preprocessing completed in {preprocess_end - preprocess_start:.2f} seconds.")

    # --- 3. 运行遗传算法获取初始解 ---
    print("\n--- Step 3: Running Genetic Algorithm ---")
    ga_start = time.time(); best_ga_solution = None; best_ga_fitness = -float('inf')
    try:
        scheduler = RevisedGeneticScheduler(
            task_units=task_units, rules=rules,
            room_capacity_dict_by_id=room_capacity_dict_by_id,
            room_name_to_id_map=room_name_to_id_map, room_id_to_name_map=room_id_to_name_map,
            all_room_ids=all_room_ids, teacher_name_to_id=teacher_name_to_id,
            pop_size=200, generations=100 # 减少代数以便快速获得初始解进行测试
        )
        best_ga_solution, best_ga_fitness = scheduler.run()
    except Exception as e: print(f"遗传算法运行时出错: {e}"); traceback.print_exc()
    ga_end = time.time(); print(f"GA Execution completed in {ga_end - ga_start:.2f} seconds.")

    if not best_ga_solution: print("GA failed to produce a solution."); return None
    print(f"GA Best Fitness (Negative Penalty): {best_ga_fitness:.2f}")

    # --- 4. 冲突检测 ---
    print("\n--- Step 4: Detecting Conflicts in GA Solution ---")
    # *** 需要从 GA 实例中获取 teacher_time_constraints ***
    conflicts, conflicting_tu_ids = detect_conflicts(
        best_ga_solution, task_units, rules,
        room_capacity_dict_by_id, room_name_to_id_map, teacher_id_to_name,
        scheduler.teacher_time_constraints # <<< 从 scheduler 实例获取
    )

    # --- 5. CP-SAT 修复 ---
    final_schedule = best_ga_solution # 默认使用 GA 解
    if conflicting_tu_ids:
         print("\n--- Step 5: Attempting CP-SAT Repair ---")
         repair_start = time.time()
         # *** 传递缺失的参数给修复函数 ***
         repaired_part = build_and_solve_cp_repair_model(
             original_schedule=best_ga_solution, conflicting_tu_ids=conflicting_tu_ids,
             task_units=task_units, rules=rules,
             room_capacity_dict_by_id=room_capacity_dict_by_id,
             room_name_to_id_map=room_name_to_id_map, all_room_ids=all_room_ids,
             df_teachers=df_teachers, df_classes=df_classes,
             time_slots=scheduler.time_slots, # <<< 传递 time_slots
             num_time_slots=scheduler.num_time_slots, # <<< 传递 num_time_slots
             teacher_id_to_name=teacher_id_to_name, # <<< 传递 teacher_id_to_name
             teacher_time_constraints=scheduler.teacher_time_constraints # <<< 传递 teacher_time_constraints
         )
         repair_end = time.time(); print(f"CP Repair attempt finished in {repair_end - repair_start:.2f} seconds.")
         if repaired_part:
              print("Merging repaired assignments...")
              final_schedule = best_ga_solution.copy(); final_schedule.update(repaired_part)
         else: print("CP Repair failed. Using initial GA solution.")
    else: print("No hard conflicts detected in GA solution!")

    # --- 6. 转换并保存最终解 ---
    print("\n--- Step 6: Converting and Saving Final Solution ---")
    # ... (与上版本相同) ...
    solution_list = []; final_calculated_overflow = 0
    task_unit_lookup = {tu['task_unit_id']: tu for tu in task_units}
    time_slots_final = scheduler.time_slots # 使用 scheduler 的时间槽

    for tu_id, assignment in final_schedule.items():
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
            if 0 <= ts_idx < len(time_slots_final):
                day, period = time_slots_final[ts_idx]
                solution_list.append({
                    "task_unit_id": tu_id, "original_task_ref": task_unit.get("original_task_ref", "N/A"),
                    "block_index": task_unit.get("block_index", 0), "duration": duration,
                    "course_id": task_unit.get("course_id", "N/A"), "course_name": task_unit.get("course_name", "N/A"),
                    "teacher_id": task_unit.get("teacher_id", "N/A"), "class_list": task_unit.get("class_list", []),
                    "room_id": room_id, "room_name": room_name, "day_of_week": day, "period": period,
                    "is_start_period": (i == 0), "student_overflow": overflow
                })
                if is_first: final_calculated_overflow += overflow; is_first = False

    print(f"Final schedule conversion complete. Total calculated overflow: {final_calculated_overflow}")
    print(f"GA Best Fitness (Negative Penalty): {best_ga_fitness}")

    # --- 7. 保存结果 ---
    print("\n--- Step 7: Saving Results ---") # 改为 Step 7
    if solution_list:
        try:
            df_solution = pd.DataFrame(solution_list)
            df_solution.sort_values(by=['day_of_week', 'period', 'room_id', 'task_unit_id'], inplace=True)
            df_solution.to_excel(output_file_final, index=False)
            print(f"Final Hybrid Solution successfully saved to {output_file_final}")
            result_data = {"status": "Hybrid_Completed", "output_file": output_file_final, "final_overflow": final_calculated_overflow}
        except Exception as e: print(f"Error saving final solution: {e}"); result_data = {"status": "ERROR_SAVING_HYBRID"}
    else: print("Error: No valid assignments in final schedule."); result_data = {"status": "HYBRID_NO_ASSIGNMENTS"}

    end_total_time = time.time()
    print(f"\nTotal Hybrid script execution time: {end_total_time - start_total_time:.2f} seconds.")
    return result_data

# --- 主程序入口 ---
if __name__ == "__main__":
    print("========================================")
    print(" Starting Course Scheduling using HYBRID (GA + CP Repair)")
    print("========================================")
    final_result = main_hybrid() # 调用混合主函数
    print("\n--- Final Summary ---")
    if final_result:
        print(f"Final Status: {final_result.get('status', 'N/A')}")
        if "output_file" in final_result:
            print(f"Output File: {final_result.get('output_file')}")
            print(f"Calculated Overflow in Final Solution: {final_result.get('final_overflow', 'N/A')}")
            print("\nNext Step: Check Excel VERY carefully. Use Check.py to verify hard constraints (it might still fail).")
        else: print("Hybrid scheduler finished, but may not have produced an output file.")
    else: print("Hybrid script failed to run completely.")
    print("========================================")