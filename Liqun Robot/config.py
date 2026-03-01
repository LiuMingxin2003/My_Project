# 配置参数

APP_NAME = "我的Python程序"

VERSION = "1.0.0"

# 数据库配置 -- 这个不写也没事

DB_CONFIG = {

    "host": "localhost",

    "port": 5432,

    "database": "myapp"

}

# API配置

API_CONFIG = {

    "api_key": "sk-e6752d4c81d740a6b172007d276c6aea",

    "base_url": "https://api.deepseek.com"

}

# 服务器配置

SERVER_CONFIG = {

    "host": "0.0.0.0",  # 监听所有网络接口

    "port": 4200,

    "debug": False  # 生产环境关闭调试模式

}