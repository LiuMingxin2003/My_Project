import pymysql
from pymysql.cursors import DictCursor


def get_all_classroom_schedules():
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
                # 1. 获取所有教室信息
                classrooms_query = """
                    SELECT DISTINCT `教室` AS classroom 
                    FROM `课程表方案`
                    WHERE `教室` IS NOT NULL AND `教室` != ''
                    ORDER BY `教室`
                """
                cursor.execute(classrooms_query)
                classrooms = [row['classroom'] for row in cursor.fetchall()]

                if not classrooms:
                    return {"error": "没有教室数据"}

                final_result = {"classrooms": []}

                # 2. 获取所有课程数据（按教室）
                schedule_query = """
                    SELECT 
                        `教室` AS classroom,
                        day_of_week AS weekday,
                        period AS time_slot,
                        GROUP_CONCAT(DISTINCT `课程列表` SEPARATOR '; ') AS courses,
                        GROUP_CONCAT(DISTINCT `教师编号` SEPARATOR ', ') AS teacher_ids
                    FROM `课程表方案`
                    GROUP BY classroom, weekday, time_slot
                    ORDER BY classroom, weekday, time_slot
                """
                cursor.execute(schedule_query)
                schedule_data = cursor.fetchall()

                # 3. 按教室组织数据
                weekdays = ["周一", "周二", "周三", "周四", "周五"]
                time_slots = [f"第{i}节" for i in range(1, 9)]

                for classroom in classrooms:
                    # 筛选当前教室的数据
                    classroom_data = [d for d in schedule_data if d['classroom'] == classroom]

                    # 构建周分布
                    weekly_dist = []
                    for day in weekdays:
                        day_courses = [d for d in classroom_data if d['weekday'] == day]
                        weekly_dist.append({
                            "weekday": day,
                            "course_count": sum(len(d['courses'].split('; ')) for d in day_courses),
                            "time_slots": [
                                {
                                    "time_slot": d['time_slot'],
                                    "courses": d['courses'].split('; '),
                                    "teacher_ids": d['teacher_ids'].split(', ')
                                } for d in day_courses
                            ]
                        })

                    # 构建日分布
                    daily_dist = []
                    for slot in time_slots:
                        slot_num = int(slot[1])
                        slot_data = [d for d in classroom_data if d['time_slot'] == slot_num]
                        daily_dist.append({
                            "time_slot": slot,
                            "course_count": sum(len(d['courses'].split('; ')) for d in slot_data),
                            "courses": [
                                {
                                    "weekday": d['weekday'],
                                    "courses": d['courses'].split('; '),
                                    "teacher_ids": d['teacher_ids'].split(', ')
                                } for d in slot_data
                            ]
                        })

                    final_result["classrooms"].append({
                        "classroom": classroom,
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
    result = get_all_classroom_schedules()

    if "error" not in result:
        for classroom in result["classrooms"]:
            print(f"\n🏫 教室：{classroom['classroom']}")

            print("\n📅 周课程分布：")
            for day in classroom["weekly_distribution"]:
                print(f"{day['weekday']}: {day['course_count']}节课")
                for time_slot in day["time_slots"]:
                    print(f"  {time_slot['time_slot']}：")
                    for course, teacher_id in zip(time_slot['courses'], time_slot['teacher_ids']):
                        print(f"    · {course}（教师ID：{teacher_id}）")

            print("\n⏰ 日时间段分布：")
            for slot in classroom["daily_distribution"]:
                print(f"{slot['time_slot']}: {slot['course_count']}节课")
                for course_info in slot["courses"]:
                    print(f"  {course_info['weekday']}：")
                    for course, teacher_id in zip(course_info['courses'], course_info['teacher_ids']):
                        print(f"    · {course}（教师ID：{teacher_id}）")
            print("\n" + "=" * 60)
    else:
        print(f"错误: {result['error']}")