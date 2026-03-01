import pymysql
from pymysql.cursors import DictCursor

def Teacher_Utilization():
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
                # 查询教师排课数据
                query = """
                    SELECT 
                        t.`姓名` AS teacher_name,
                        COUNT(DISTINCT c.`day_of_week`, c.`period`) AS total_courses
                    FROM `课程表方案` c
                    INNER JOIN `教师信息` t 
                        ON c.`教师编号` = t.`工号`
                    GROUP BY t.`工号`, t.`姓名`
                """
                cursor.execute(query)
                data = cursor.fetchall()

                if not data:
                    return {
                        "avg_courses": 0.0,
                        "top_teachers": []
                    }

                # 计算总平均值
                total_courses = sum(item['total_courses'] for item in data)
                total_teachers = len(data)
                avg_courses = total_courses / total_teachers if total_teachers > 0 else 0

                # 获取前十教师
                sorted_teachers = sorted(data,
                                      key=lambda x: x['total_courses'],
                                      reverse=True)[:10]

                return {
                    "avg_courses": round(avg_courses, 2),  # 总平均排课
                    "top_teachers": [{
                        "teacher": item['teacher_name'],
                        "courses": item['total_courses']
                    } for item in sorted_teachers]
                }

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        return None
    except Exception as e:
        print(f"系统错误: {e}")
        return None

# 使用示例
if __name__ == "__main__":
    result = Teacher_Utilization()
    if result:
        print("📚 教师排课统计结果")
        print(f"\n📊 教师平均周排课量: {result['avg_courses']}节")
        print("\n🏆 排课量前十教师:")
        for i, item in enumerate(result["top_teachers"], 1):
            print(f"{i}. {item['teacher']}: {item['courses']}节")
    else:
        print("统计失败")