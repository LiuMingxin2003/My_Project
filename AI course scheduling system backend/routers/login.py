from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, select
from sqlalchemy.orm import sessionmaker, declarative_base
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta

from routers.Chart_Course_Day import router

# ----------------------
# 数据库配置 (MySQL)
# ----------------------
MYSQL_USER = "root"
MYSQL_PASSWORD = "123456"
MYSQL_HOST = "localhost"
MYSQL_PORT = "3306"
MYSQL_DB = "select_system"

SQLALCHEMY_DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@"
    f"{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ----------------------
# 数据库模型
# ----------------------
class User(Base):
    __tablename__ = "user"

    username = Column(String(50), primary_key=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # 用户角色：admin/teacher/student


# 创建表（首次运行时执行）
Base.metadata.create_all(bind=engine)

# ----------------------
# 安全配置
# ----------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SECRET_KEY = "your-secret-key-here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# ----------------------
# Pydantic模型
# ----------------------
class LoginRequest(BaseModel):
    username: str
    password: str  # 前端传过来的 SHA256 加密字符串



class Token(BaseModel):
    access_token: str
    token_type: str


# ----------------------
# 工具函数
# ----------------------
def verify_password(plain_password: str, hashed_password: str):
    """直接对比 SHA-256 哈希值"""
    return plain_password == hashed_password  # 直接字符串对比


def get_password_hash(password: str):
    """密码哈希存储（使用 bcrypt）"""
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ----------------------
# 依赖项
# ----------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------
# 路由处理
# ----------------------
@router.post("/login")
async def login(login_data: LoginRequest, db=Depends(get_db)):
    # 只通过用户名查询用户（移除角色过滤）
    user = db.execute(
        select(User).where(User.username == login_data.username)
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"  # 统一错误提示
        )

    # 密码验证（保持双重哈希验证）
    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"  # 统一错误提示
        )

    # 生成包含用户实际角色的JWT
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}  # 仍返回实际角色信息
    )

    return {"access_token": access_token, "token_type": "bearer"}
