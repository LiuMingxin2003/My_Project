import pymysql
from pymysql.cursors import DictCursor


def Database_Course_Day():
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
                # 统计总任务数（去重）
                task_count_query = """
                    SELECT COUNT(DISTINCT task_id) AS total_tasks
                    FROM `课程表方案`
                """
                cursor.execute(task_count_query)
                task_count = cursor.fetchone()['total_tasks']

                # 统计周课程分布（按星期分组）
                weekly_dist_query = """
                    SELECT 
                        day_of_week AS weekday,
                        COUNT(*) AS course_count
                    FROM `课程表方案`
                    GROUP BY day_of_week
                    ORDER BY day_of_week
                """
                cursor.execute(weekly_dist_query)
                weekly_data = cursor.fetchall()

                # 处理周课程分布数据
                weekdays = ["周一", "周二", "周三", "周四", "周五"]
                processed_weekly = []

                # 初始化每日数据（确保包含所有工作日）
                for day in range(0, 5):
                    found = next((item for item in weekly_data if item['weekday'] == day), None)
                    processed_weekly.append({
                        "weekday": weekdays[day - 1],
                        "course_count": found['course_count'] if found else 0
                    })

                return {
                    "total_tasks": task_count,
                    "weekly_distribution": processed_weekly
                }

    except pymysql.Error as e:
        print(f"⚠️ 数据库操作失败: {e}")
        return None
    except Exception as e:
        print(f"⚠️ 发生未知错误: {e}")
        return None


# 使用示例
if __name__ == "__main__":
    result = Database_Course_Day()
    if result:
        print("📊 任务统计结果")
        print(f"\n📌 总任务数: {result['total_tasks']}")
        print("\n🗓️ 周课程分布：")
        for day in result["weekly_distribution"]:
            print(f"{day['weekday']}: 课程数 {day['course_count']}")
    else:
        print("统计失败，请检查数据库连接和日志")