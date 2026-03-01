import pymysql
from pymysql.cursors import DictCursor


def Show_Able(classroom_id):
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

                # 2. 查询所有课程时间段（包含完整课程信息）
                time_query = """
                    SELECT `day_of_week`, `period`
                    FROM `课程表方案`
                    WHERE `教室` = %s
                """
                cursor.execute(time_query, (classroom_id,))
                occupied_slots = cursor.fetchall()

                # 3. 初始化占用字典（周一到周日，每天1-8节）
                occupied = {i: {"periods": set(), "courses": []} for i in range(7)}
                for slot in occupied_slots:
                    # 转换数据库字段到前端格式
                    day = slot['day_of_week']  # 数据库存储0-6
                    period = slot['period'] + 1  # 转换为1-8节

                    if 0 <= day <= 6 and 1 <= period <= 8:
                        # 记录占用时段
                        occupied[day]["periods"].add(period)
                        # 记录完整课程信息

                # 4. 计算可用时间段并整理课程信息
                weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                available_time = []
                full_schedule = []

                for day in range(7):
                    # 处理可用时段
                    all_slots = set(range(1, 9))
                    free_slots = sorted(all_slots - occupied[day]["periods"])

                    available_time.append({
                        "weekday": weekdays[day],
                        "available_slots": [f"第{p}节" for p in free_slots],
                        "available_count": len(free_slots)
                    })

                    # 整理完整课表
                    for course in occupied[day]["courses"]:
                        full_schedule.append({
                            "weekday": weekdays[day],
                            **course
                        })

                return {
                    "status": "success",
                    "classroom_id": classroom_info['教室编号'],
                    "classroom_name": classroom_info['教室名称'],
                    "available_time": available_time,
                    "full_schedule": full_schedule
                }

    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        return {"error": "数据库操作失败"}
    except Exception as e:
        print(f"服务器错误: {str(e)}")
        return {"error": "服务器内部错误"}

# 使用示例
if __name__ == "__main__":
    result = Show_Able("JXL318")
    if "error" not in result:
        print(f"教室信息：{result['classroom_name']}（编号：{result['classroom_id']}）")
        print("\n可用时间段分布：")
        for day in result["available_time"]:
            slots = "、".join(day['available_slots']) if day['available_slots'] else "无"
            print(f"{day['weekday']}: 共{day['available_count']}个空闲时段 → {slots}")
    else:
        print(f"查询失败：{result['error']}")