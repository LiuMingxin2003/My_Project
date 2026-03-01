import pymysql
from pymysql import Error


def query_db(name):
    """根据姓名和工号从MySQL数据库查询员工信息

    Args:
        config (dict): 数据库配置字典
        name (str): 查询姓名
        employee_id (str): 查询工号

    Returns:
        dict/bool: 查询成功返回员工信息字典，失败返回False
    """
    conn = None
    try:
        db_config = {
            "host": "localhost",
            "user": "root",
            "password": "123456",
            "database": "select_system",
            "port": 3306
        }
        # 建立数据库连接
        conn = pymysql.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            port=db_config.get('port', 3306),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        # 使用上下文管理器管理游标
        with conn.cursor() as cursor:
            # 参数化查询防止SQL注入
            sql = """
                SELECT * FROM 课程库 
                WHERE 课程名称 = %s 
                LIMIT 1
            """
            cursor.execute(sql, (name))
            result = cursor.fetchone()

        return result if result else False

    except Error as e:
        print(f"数据库错误: {e}")
        return False
    finally:
        if conn and conn.open:
            conn.close()


# 使用示例
if __name__ == "__main__":
    # 数据库配置（实际使用中建议从环境变量读取）
    # 测试查询
    print(query_db("高等数学"))  # 返回匹配记录或False