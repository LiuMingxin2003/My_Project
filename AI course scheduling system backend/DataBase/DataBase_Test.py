# query_script.py
import sys
from sqlalchemy import create_engine, text

def transform_data(input_data):
    """
    将课程数据转换为统一格式
    :param input_data: 输入元组 (课程编号, 课程名称)
    :return: 标准化字典格式
    """
    return {
            "name": input_data[1],         # 课程名称
            "id": input_data[0],           # 课程编号
    }
def get_table_mapping(key):
    """Key与中文表名映射"""
    mapping = {
        "course": "课程库",
        "teacher": "教师信息",
        "room": "教室信息"
    }
    return mapping.get(key)


def main(key, search_name):
    # =====================
    # 数据库配置（根据实际表结构修改）
    # =====================
    DATABASE_URL = "mysql+pymysql://root:123456@localhost/select_system"

    # 字段映射配置（使用中文字段名）
    FIELD_MAP = {
        "课程库": {  # 必须与get_table_mapping返回的中文表名一致
            "name_field": "课程名称",  # 名称字段
            "id_field": "课程编号"  # ID字段
        },
        "教室信息": {  # 必须与get_table_mapping返回的中文表名一致
            "name_field": "教室名称",  # 名称字段
            "id_field": "教室编号"  # ID字段
        },
        "教师信息": {
            "name_field": "姓名",
            "id_field": "工号"
        }
    }

    try:
        # 1. 参数校验
        if not key or not search_name:
            print("错误：缺少必要参数")
            return 'a'

        # 2. 获取中文表名
        table_name = get_table_mapping(key)
        if not table_name:
            print(f"错误：无效的key '{key}'")
            return 'a'

        # 3. 获取字段配置
        config = FIELD_MAP.get(table_name)
        if not config:
            print(f"错误：未配置表 '{table_name}' 的字段映射")
            return 'a'

        # 4. 连接数据库
        engine = create_engine(DATABASE_URL)

        # 5. 执行参数化查询
        with engine.connect() as conn:
            # 使用中文字段名和表名
            query = text(f"""
                SELECT 
                    `{config['id_field']}` AS id,
                    `{config['name_field']}` AS name
                FROM `{table_name}`
                WHERE `{config['name_field']}` = :name
            """)

            result = conn.execute(query, {"name": search_name})
            row = result.fetchone()
            # 如果未找到且是教师信息表，则按工号字段再次查询
            if not row and table_name == "教师信息":
                query = text(f"""
                          SELECT 
                              `{config['id_field']}` AS id,
                              `{config['name_field']}` AS name
                          FROM `{table_name}`
                          WHERE `{config['id_field']}` = :search_term
                      """)
                result = conn.execute(query, {"search_term": search_name})
                row = result.fetchone()

            return row

    except Exception as e:
        print(f"操作失败：{str(e)}")


if __name__ == "__main__":
    # 从命令行接收参数：python query_script.py course "高等数学

    result = main("teacher", "金龙")
    result1 = transform_data(result)
    print(result1)