import pymysql
from pymysql.cursors import DictCursor


def Classroom_Course_Distribution(classroom_id):
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
                # 1. 验证教室存在性
                classroom_check = """
                    SELECT `教室编号`, `教室名称` 
                    FROM `教室信息`
                    WHERE `教室编号` = %s
                """
                cursor.execute(classroom_check, (classroom_id,))
                classroom_info = cursor.fetchone()

                if not classroom_info:
                    return {"error": "教室不存在"}

                # 2. 查询课程数据（关联教师信息表）
                base_query = """
                    SELECT 
                        c.`day_of_week` AS weekday,
                        c.`period` AS time_slot,
                        c.`课程编号` AS course_id,
                        c.`课程列表` AS course_name,
                        c.`教师编号` AS teacher_id,
                        t.`姓名` AS teacher_name
                    FROM `课程表方案` c
                    LEFT JOIN `教师信息` t ON c.`教师编号` = t.`工号`
                    WHERE c.`教室` = %s
                """

                # 查询周分布
                weekly_query = base_query + " ORDER BY weekday"
                cursor.execute(weekly_query, (classroom_id,))
                weekly_raw = cursor.fetchall()

                # 修正代码
                weekdays = ["周一", "周二", "周三", "周四", "周五"]
                weekly_courses = {day: [] for day in range(0, 5)}  # 键 0-4
                for course in weekly_raw:
                    weekday = course['weekday']
                    weekly_courses[weekday].append({
                        "course_id": course['course_id'],
                        "course_name": course['course_name'],
                        "teacher_id": course['teacher_id'],
                        "teacher_name": course['teacher_name']  # 来自教师信息表
                    })

                weekly_dist = []
                for day_num in range(0, 5):  # 遍历 0-4
                    weekly_dist.append({
                        "weekday": weekdays[day_num],  # 直接使用索引
                        "course_count": len(weekly_courses[day_num]),
                        "courses": weekly_courses[day_num].copy()
                    })

                # 查询日分布
                daily_query = base_query + " ORDER BY period"
                cursor.execute(daily_query, (classroom_id,))
                daily_raw = cursor.fetchall()

                # 处理日课程数据
                time_slots = [f"第{i}节" for i in range(0, 8)]
                daily_courses = {slot: [] for slot in range(0, 8)}
                for course in daily_raw:
                    time_slot = course['time_slot']
                    daily_courses[time_slot].append({
                        "course_id": course['course_id'],
                        "course_name": course['course_name'],
                        "teacher_id": course['teacher_id'],
                        "teacher_name": course['teacher_name']  # 来自教师信息表
                    })

                daily_dist = []
                for slot_num in range(0, 8):
                    daily_dist.append({
                        "time_slot": time_slots[slot_num - 1],
                        "course_count": len(daily_courses[slot_num]),
                        "courses": daily_courses[slot_num].copy()
                    })

                return {
                    "classroom_id": classroom_info['教室编号'],
                    "classroom_name": classroom_info['教室名称'],
                    "weekly_distribution": weekly_dist,
                    "daily_distribution": daily_dist
                }

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        return {"error": "数据库操作失败"}
    except Exception as e:
        import traceback
        traceback.print_exc()  # 打印完整错误堆栈
        print(f"⚠️ 详细错误信息: {repr(e)}")
        return {"error": "服务器内部错误"}


# 使用示例
if __name__ == "__main__":
    # 测试教室编号查询
    result = Classroom_Course_Distribution("2#207")
    if "error" not in result:
        print(f"教室信息：{result['classroom_name']}（编号：{result['classroom_id']}）")

        print("\n周课程分布：")
        for day in result["weekly_distribution"]:
            print(f"{day['weekday']}: {day['course_count']}节课")
            for course in day['courses']:
                print(f"  课程：{course['course_name']}（{course['course_id']}）")
                print(f"  教师：{course['teacher_name']}（工号：{course['teacher_id']}）")

        print("\n时间段分布：")
        for slot in result["daily_distribution"]:
            print(f"{slot['time_slot']}: {slot['course_count']}节课")
            for course in slot['courses']:
                print(f"  课程：{course['course_name']}（{course['course_id']}）")
                print(f"  教师：{course['teacher_name']}（工号：{course['teacher_id']}）")
    else:
        print(f"查询失败：{result['error']}")