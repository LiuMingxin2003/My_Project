import pymysql
from pymysql.cursors import DictCursor

# 中文星期到数字映射
WEEKDAY_MAP = {
    "周一": 0, "周二": 1, "周三": 2,
    "周四": 3, "周五": 4, "周六": 5, "周日": 6
}


def Update_Schedule(origin_data, target_data):
    """
    更新课程时间安排
    :param origin_data: 原始时间信息 {classNumber: 节次, day: 星期, classroom: 教室}
    :param target_data: 目标时间信息 {classNumber: 节次, day: 星期, classroom: 教室}
    :return: 操作结果字典
    """
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
        # 转换时间参数
        origin_day = WEEKDAY_MAP[origin_data['day']]  # 添加缺失的 ]
        origin_period = origin_data['classNumber']  # 原节次
        classroom = origin_data['classroom']  # 教室编号

        target_day = WEEKDAY_MAP[target_data['day']]  # 添加缺失的 ]
        target_period = target_data['classNumber']  # 目标节次


        # 建立数据库连接
        conn = pymysql.connect(**db_config)

        try:
            with conn.cursor() as cursor:
                # === 第一步：验证原课程存在 ===
                check_origin_sql = """
                    SELECT `课程列表` 
                    FROM `课程表方案` 
                    WHERE 
                        `教室` = %s AND
                        `day_of_week` = %s AND 
                        `period` = %s
                """
                cursor.execute(check_origin_sql, (classroom, origin_day, origin_period))
                if not cursor.fetchone():
                    return {"status": "error", "message": "原课程不存在"}

                # === 第二步：检查目标时段可用性 ===
                check_target_sql = """
                    SELECT 1 
                    FROM `课程表方案` 
                    WHERE 
                        `教室` = %s AND
                        `day_of_week` = %s AND 
                        `period` = %s
                """
                cursor.execute(check_target_sql, (classroom, target_day, target_period))
                if cursor.fetchone():
                    return {"status": "error", "message": "目标时段已被占用"}

                # === 第三步：执行更新操作 ===
                update_sql = """
                    UPDATE `课程表方案`
                    SET 
                        `day_of_week` = %s,
                        `period` = %s
                    WHERE 
                        `教室` = %s AND
                        `day_of_week` = %s AND 
                        `period` = %s
                """
                cursor.execute(update_sql, (
                    target_day, target_period,  # 新值
                    classroom, origin_day, origin_period  # 条件
                ))

                # 提交事务
                conn.commit()

                return {
                    "status": "success",
                    "data": {
                        "from": f"{origin_data['day']} 第{origin_period}节",
                        "to": f"{target_data['day']} 第{target_period}节",
                        "classroom": classroom
                    }
                }

        except pymysql.Error as e:
            conn.rollback()
            return {"status": "error", "message": f"数据库操作失败: {str(e)}"}
        finally:
            conn.close()

    except KeyError as e:
        return {"status": "error", "message": f"无效的星期格式: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"系统错误: {str(e)}"}


# 使用示例
if __name__ == "__main__":
    # 测试数据
    origin = {
        "classNumber": 2,
        "day": "周四",
        "classroom": "QCGCZX3-306"
    }
    target = {
        "classNumber": 2,
        "day": "周三",
        "classroom": "QCGCZX3-306"
    }

    # 执行更新
    result = Update_Schedule(origin, target)
    print("操作结果:", result)

    # 测试错误情况
    error_test = Update_Schedule(origin, target)  # 重复更新
    print("冲突测试:", error_test)