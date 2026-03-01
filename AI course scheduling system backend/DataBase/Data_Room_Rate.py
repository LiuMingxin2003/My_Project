import pymysql
from pymysql.cursors import DictCursor


def Chart_Room_Rate():
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
        # 使用上下文管理器管理连接
        with pymysql.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                # 查询每个教室的时间段占用情况（使用中文列名）
                query = """
                    SELECT 
                        `教室` AS classroom,
                        COUNT(DISTINCT `day_of_week`, `period`) AS occupied_slots
                    FROM `课程表方案`
                    GROUP BY `教室`
                """
                cursor.execute(query)
                data = cursor.fetchall()

                # 计算利用率
                classroom_utils = []
                for item in data:
                    utilization = (item['occupied_slots'] / 40) * 100  # 每周总时间段数 = 5天×8节
                    classroom_utils.append((item['classroom'], utilization))

                # 按利用率排序取前十
                classroom_utils.sort(key=lambda x: x[1], reverse=True)
                top_10 = classroom_utils[:10]

                # 计算总利用率
                total_occupied = sum(item['occupied_slots'] for item in data)
                total_classrooms = len(data)
                total_utilization = (total_occupied / (total_classrooms * 40)) * 100 if total_classrooms > 0 else 0

                # 返回结果字典
                return {
                    "top_10": [{"classroom": c[0], "utilization": f"{c[1]:.2f}%"} for c in top_10],
                    "total_utilization": f"{total_utilization:.2f}%"
                }

    except pymysql.Error as e:
        print(f"⚠️ 数据库操作失败: {e}")
        return None
    except Exception as e:
        print(f"⚠️ 发生未知错误: {e}")
        return None


# 使用示例
if __name__ == "__main__":
    result = Chart_Room_Rate()
    if result:
        print("🏫 教室利用率统计结果 🏫")
        print("\n🔝 利用率前十教室：")
        for i, item in enumerate(result["top_10"], 1):
            print(f"{i}. {item['classroom']}: {item['utilization']}")

        print(f"\n📊 总平均教室利用率: {result['total_utilization']}")
    else:
        print("统计失败，请检查数据库连接和日志")