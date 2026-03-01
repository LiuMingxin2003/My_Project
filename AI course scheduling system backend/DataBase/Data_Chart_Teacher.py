import pymysql
from pymysql.cursors import DictCursor

def Teacher_Course_Distribution(teacher_id):
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
                # 1. 获取教师姓名
                teacher_query = """
                    SELECT `姓名` AS teacher_name 
                    FROM `教师信息` 
                    WHERE `工号` = %s
                """
                cursor.execute(teacher_query, (teacher_id,))
                teacher_info = cursor.fetchone()

                if not teacher_info:
                    return {"error": "教师ID不存在"}

                # 2. 查询周课程分布详情
                weekly_query = """
                    SELECT 
                        day_of_week AS weekday,
                        `课程编号` AS course_id,
                        `课程列表` AS course_name,
                        `教室` AS classroom
                    FROM `课程表方案`
                    WHERE `教师编号` = %s
                    ORDER BY day_of_week
                """
                cursor.execute(weekly_query, (teacher_id,))
                weekly_raw = cursor.fetchall()

                # 周映射关系（数据库0=周一，6=周日）
                WEEKDAY_MAP = {
                    0: "周一", 1: "周二", 2: "周三",
                    3: "周四", 4: "周五", 5: "周六", 6: "周日"
                }

                # 初始化周课程容器（保持顺序）
                weekly_dist = []
                for day_num in sorted(WEEKDAY_MAP.keys()):
                    # 过滤当天课程
                    day_courses = [
                        {
                            "course_id": str(course['course_id']),
                            "course_name": course['course_name'].strip(),
                            "classroom": course['classroom'].upper()
                        }
                        for course in weekly_raw
                        if course['weekday'] == day_num
                    ]

                    weekly_dist.append({
                        "weekday": WEEKDAY_MAP[day_num],
                        "course_count": len(day_courses),
                        "courses": day_courses
                    })

                # 3. 查询日课程分布详情
                daily_query = """
                    SELECT 
                        period,
                        `课程编号` AS course_id,
                        `课程列表` AS course_name,
                        `教室` AS classroom
                    FROM `课程表方案`
                    WHERE `教师编号` = %s
                    ORDER BY period
                """
                cursor.execute(daily_query, (teacher_id,))
                daily_raw = cursor.fetchall()

                # 时间段映射（数据库0=第1节，7=第8节）
                PERIOD_MAP = {i: f"第{i + 1}节" for i in range(8)}

                # 初始化日课程容器（保持顺序）
                daily_dist = []
                for period_num in sorted(PERIOD_MAP.keys()):
                    # 过滤当前节次课程
                    period_courses = [
                        {
                            "course_id": str(course['course_id']),
                            "course_name": course['course_name'].strip(),
                            "classroom": course['classroom'].upper()
                        }
                        for course in daily_raw
                        if course['period'] == period_num
                    ]

                    daily_dist.append({
                        "time_slot": PERIOD_MAP[period_num],
                        "course_count": len(period_courses),
                        "courses": period_courses
                    })

                return {
                    "teacher_name": teacher_info['teacher_name'],
                    "weekly_distribution": weekly_dist,
                    "daily_distribution": daily_dist
                }

    except pymysql.Error as e:
        print(f"⚠️ 数据库操作失败: {e}")
        return {"error": "数据库错误"}
    except Exception as e:
        print(f"⚠️ 发生未知错误: {e}")
        return {"error": "服务器内部错误"}

# 使用示例
if __name__ == "__main__":
    # 测试教师ID：130（假设存在测试数据）
    result = Teacher_Course_Distribution("327")
    if "error" not in result:
        print(f"👨🏫 教师 {result['teacher_name']} 课程分布")

        print("\n📅 周课程分布：")
        for day in result["weekly_distribution"]:
            print(f"{day['weekday']}: {day['course_count']}节课")
            for course in day['courses']:
                print(f"  课程编号：{course['course_id']}｜名称：{course['course_name']}｜教室：{course['classroom']}")

        print("\n⏰ 日时间段分布：")
        for slot in result["daily_distribution"]:
            print(f"{slot['time_slot']}: {slot['course_count']}节课")
            for course in slot['courses']:
                print(f"  课程编号：{course['course_id']}｜名称：{course['course_name']}｜教室：{course['classroom']}")
    else:
        print(f"错误: {result['error']}")