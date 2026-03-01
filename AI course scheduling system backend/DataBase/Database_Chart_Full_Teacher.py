import pymysql
from pymysql.cursors import DictCursor


def get_all_teachers_courses():
    db_config = {
        "host": "localhost",
        "user": "root",
        "password": "123456",
        "database": "select_system",
        "port": 3306,
        "charset": 'utf8mb4',
        "cursorclass": DictCursor
    }

    try:
        with pymysql.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                # 1. 获取所有教师信息
                teachers_query = """
                    SELECT `工号` AS teacher_id, `姓名` AS teacher_name 
                    FROM `教师信息`
                """
                cursor.execute(teachers_query)
                all_teachers = cursor.fetchall()

                if not all_teachers:
                    return {"error": "没有教师信息"}

                final_result = {"teachers": []}

                # 2. 获取所有课程数据（周分布）
                weekly_query = """
                    SELECT 
                        `教师编号`,
                        day_of_week AS weekday,
                        `课程编号` AS course_id,
                        `课程列表` AS course_name,
                        `教室` AS classroom
                    FROM `课程表方案`
                    ORDER BY `教师编号`, day_of_week
                """
                cursor.execute(weekly_query)
                weekly_raw = cursor.fetchall()

                # 3. 获取所有课程数据（日分布）
                daily_query = """
                    SELECT 
                        `教师编号`,
                        period AS time_slot,
                        `课程编号` AS course_id,
                        `课程列表` AS course_name,
                        `教室` AS classroom
                    FROM `课程表方案`
                    ORDER BY `教师编号`, period
                """
                cursor.execute(daily_query)
                daily_raw = cursor.fetchall()

                # 处理每个教师的课程数据
                for teacher in all_teachers:
                    teacher_id = teacher['teacher_id']
                    teacher_name = teacher['teacher_name']

                    # 处理周课程分布
                    weekdays = ["周一", "周二", "周三", "周四", "周五"]
                    weekly_courses = {day: [] for day in range(1, 6)}

                    # 筛选当前教师的周课程
                    teacher_weekly = [c for c in weekly_raw if c['教师编号'] == teacher_id]
                    for course in teacher_weekly:
                        weekday = course['weekday']
                        if weekday in weekly_courses:
                            weekly_courses[weekday].append({
                                "course_id": course['course_id'],
                                "course_name": course['course_name'],
                                "classroom": course['classroom']
                            })

                    weekly_dist = []
                    for day_num in range(1, 6):
                        courses = weekly_courses[day_num]
                        weekly_dist.append({
                            "weekday": weekdays[day_num - 1],
                            "course_count": len(courses),
                            "courses": courses.copy()
                        })

                    # 处理日课程分布
                    time_slots = [f"第{i}节" for i in range(1, 9)]
                    daily_courses = {slot: [] for slot in range(1, 9)}

                    # 筛选当前教师的日课程
                    teacher_daily = [c for c in daily_raw if c['教师编号'] == teacher_id]
                    for course in teacher_daily:
                        time_slot = course['time_slot']
                        if time_slot in daily_courses:
                            daily_courses[time_slot].append({
                                "course_id": course['course_id'],
                                "course_name": course['course_name'],
                                "classroom": course['classroom']
                            })

                    daily_dist = []
                    for slot_num in range(1, 9):
                        courses = daily_courses[slot_num]
                        daily_dist.append({
                            "time_slot": time_slots[slot_num - 1],
                            "course_count": len(courses),
                            "courses": courses.copy()
                        })

                    # 添加到最终结果
                    final_result["teachers"].append({
                        "teacher_id": teacher_id,
                        "teacher_name": teacher_name,
                        "weekly_distribution": weekly_dist,
                        "daily_distribution": daily_dist
                    })

                return final_result

    except pymysql.Error as e:
        print(f"⚠️ 数据库操作失败: {e}")
        return {"error": "数据库错误"}
    except Exception as e:
        print(f"⚠️ 发生未知错误: {e}")
        return {"error": "服务器内部错误"}


# 使用示例
if __name__ == "__main__":
    result = get_all_teachers_courses()

    if "error" not in result:
        for teacher in result["teachers"]:
            print(f"\n👨🏫 教师 {teacher['teacher_name']}（工号：{teacher['teacher_id']}）课程分布")

            print("\n📅 周课程分布：")
            for day in teacher["weekly_distribution"]:
                print(f"{day['weekday']}: {day['course_count']}节课")
                for course in day['courses']:
                    print(f"  课程编号：{course['course_id']}｜名称：{course['course_name']}｜教室：{course['classroom']}")

            print("\n⏰ 日时间段分布：")
            for slot in teacher["daily_distribution"]:
                print(f"{slot['time_slot']}: {slot['course_count']}节课")
                for course in slot['courses']:
                    print(f"  课程编号：{course['course_id']}｜名称：{course['course_name']}｜教室：{course['classroom']}")
            print("\n" + "=" * 60)
    else:
        print(f"错误: {result['error']}")