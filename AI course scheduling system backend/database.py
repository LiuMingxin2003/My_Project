from pydantic_settings import BaseSettings
from aiomysql import connect

class DBSettings(BaseSettings):
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "select_system"

    class Config:
        env_file = ".env"
        env_prefix = "DB_"

async def get_connection():
    settings = DBSettings()
    return await connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        db=settings.database
    )