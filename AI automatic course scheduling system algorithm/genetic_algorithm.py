import pandas as pd
import random
from typing import List, Dict
import numpy as np
from collections import defaultdict
import 算法1

# ===================== 遗传算法核心类 =====================
class GeneticScheduler:
    def __init__(self, tasks: List[Dict], rooms: pd.DataFrame,
                 teachers: pd.DataFrame, classes: pd.DataFrame,
                 pop_size=100, elite_ratio=0.1, mutation_rate=0.2,
                 generations=200):
        """
        初始化遗传算法参数
        """
        self.tasks = tasks
        self.rooms = rooms.set_index('room_id').to_dict('index')
        self.teachers = {row['teacher_id']: row for _, row in teachers.iterrows()}
        self.classes = classes.set_index('class_name').to_dict('index')

        # 时间槽定义（同原CP模型）
        self.time_slots = [(d, p) for d in range(5) for p in range(8)]
        self.room_ids = list(rooms['room_id'])

        # 遗传算法参数
        self.pop_size = pop_size
        self.elite_size = int(pop_size * elite_ratio)
        self.mutation_rate = mutation_rate
        self.generations = generations

        # 缓存数据结构
        self.teacher_tasks = defaultdict(list)  # {teacher_id: [task_ids]}
        for task in tasks:
            self.teacher_tasks[task['teacher_id']].append(task['task_id'])

    def _initialize_individual(self) -> Dict[int, tuple]:
        """生成随机个体（需满足教室类型约束）"""
        individual = {}
        for task in self.tasks:
            # 筛选符合教室类型的候选教室
            valid_rooms = [r_id for r_id in self.room_ids
                           if self.rooms[r_id]['room_type'] == task.get('required_room_type', '')]
            if not valid_rooms:
                valid_rooms = self.room_ids  # 若无指定则放宽

            # 随机选择时间和教室
            time_idx = random.choice(range(len(self.time_slots)))
            room_id = random.choice(valid_rooms)
            individual[task['task_id']] = (time_idx, room_id)
        return individual

    def _calculate_fitness(self, individual: Dict) -> float:
        """计算适应度：排课数量 - 约束违反惩罚"""
        penalty = 0
        scheduled = 0

        # 冲突检测数据结构
        teacher_time = defaultdict(set)  # {teacher_id: {time_idx}}
        room_time = defaultdict(set)  # {room_id: {time_idx}}
        class_time = defaultdict(set)  # {class_name: {time_idx}}

        for task in self.tasks:
            t_id = task['task_id']
            time_idx, room_id = individual[t_id]

            # 检查教室容量
            if task['total_students'] > self.rooms[room_id]['capacity']:
                penalty += 10  # 容量超限惩罚
                continue

            # 记录教师时间冲突
            teacher_id = task['teacher_id']
            if time_idx in teacher_time[teacher_id]:
                penalty += 5  # 教师冲突惩罚
            else:
                teacher_time[teacher_id].add(time_idx)

            # 记录教室时间冲突
            if time_idx in room_time[room_id]:
                penalty += 5  # 教室冲突惩罚
            else:
                room_time[room_id].add(time_idx)

            # 记录班级时间冲突
            for class_name in task['class_list']:
                if time_idx in class_time[class_name]:
                    penalty += 2  # 班级冲突惩罚
                else:
                    class_time[class_name].add(time_idx)

            scheduled += 1  # 成功排课计数

        return scheduled - penalty

    def _mutate(self, individual: Dict) -> Dict:
        """变异操作：随机修改部分基因"""
        for t_id in individual:
            if random.random() < self.mutation_rate:
                task = next(t for t in self.tasks if t['task_id'] == t_id)
                new_time = random.choice(range(len(self.time_slots)))
                new_room = random.choice(
                    [r_id for r_id in self.room_ids
                     if self.rooms[r_id]['room_type'] == task.get('required_room_type', '')]
                )
                individual[t_id] = (new_time, new_room)
        return individual

    def _crossover(self, parent1: Dict, parent2: Dict) -> Dict:
        """单点交叉：随机选择交叉点交换任务分配"""
        cross_point = random.randint(1, len(self.tasks) - 1)
        child = {}
        task_ids = list(parent1.keys())
        for i in range(len(task_ids)):
            if i < cross_point:
                child[task_ids[i]] = parent1[task_ids[i]]
            else:
                child[task_ids[i]] = parent2[task_ids[i]]
        return child

    def run(self) -> Dict:
        """执行遗传算法主流程"""
        # 初始化种群
        population = [self._initialize_individual() for _ in range(self.pop_size)]

        for generation in range(self.generations):
            # 评估适应度
            fitness = [self._calculate_fitness(ind) for ind in population]

            # 精英选择
            elite_indices = np.argsort(fitness)[-self.elite_size:]
            elites = [population[i] for i in elite_indices]

            # 生成新一代
            new_population = elites.copy()

            # 锦标赛选择与交叉
            while len(new_population) < self.pop_size:
                # 选择父代
                candidates = random.sample(range(len(population)), 5)
                parent1 = population[max(candidates, key=lambda x: fitness[x])]
                candidates = random.sample(range(len(population)), 5)
                parent2 = population[max(candidates, key=lambda x: fitness[x])]

                # 交叉产生子代
                child = self._crossover(parent1, parent2)
                new_population.append(child)

            # 变异
            population = [self._mutate(ind) for ind in new_population]

            # 输出当前最优
            best_fitness = max(fitness)
            print(f"Generation {generation}: Best Fitness = {best_fitness}")

        # 提取最优解
        best_idx = np.argmax([self._calculate_fitness(ind) for ind in population])
        return population[best_idx]


# ===================== 修改后的主函数 =====================
def main():
    # 1. 数据加载（与原代码相同）
    df_teachers = 算法1.load_teacher_info("./test_data/教师信息.xlsx")
    df_classes = 算法1.load_class_info("./test_data/班级数据.xls")
    df_rooms = 算法1.load_room_info("./test_data/教室信息.xls")
    df_tasks = 算法1.load_task_info("./test_data/排课任务.xlsx")

    # 2. 预处理（与原代码相同）
    tasks_preprocessed = 算法1.preprocess_tasks(df_tasks, df_classes, df_teachers)

    # 3. 遗传算法优化
    scheduler = GeneticScheduler(
        tasks_preprocessed,
        df_rooms,
        df_teachers,
        df_classes,
        pop_size=50,
        generations=100
    )
    best_solution = scheduler.run()

    # 4. 解格式转换
    final_solution = []
    for task in tasks_preprocessed:
        t_id = task['task_id']
        time_idx, r_id = best_solution[t_id]
        day, period = scheduler.time_slots[time_idx]
        final_solution.append({
            "task_id": t_id,
            "课程编号": task['course_id'],
            "教师编号": task['teacher_id'],
            "课程列表": task['class_list'],
            "教室": r_id,
            "day_of_week": day,
            "period": period
        })

        df = pd.DataFrame(final_solution)

        # 保存为 Excel 文件
        output_file = "课程表方案.xlsx"  # 可自定义文件名
        df.to_excel(output_file, index=False)  # index=False 表示不保存行索引

        print(f"数据已成功保存至 {output_file}")

    # 5. 节假日调整（与原代码相同）
    holiday_list = [2]  # 示例：周三放假
    final_solution = 算法1.holiday_reschedule(final_solution, holiday_list, None)

    return {
        "status": "optimized",
        "solution": final_solution,
        "fitness": scheduler._calculate_fitness(best_solution)
    }

# 其他辅助函数（holiday_reschedule等）保持与原代码相同
if __name__ == "__main__":
    result = main()
    print(result)