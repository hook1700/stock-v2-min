"""SQLite数据库连接管理"""
from sqlalchemy import create_engine, event, text as import_text
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import settings

DATABASE_URL = f"sqlite:///{settings.DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """启用SQLite WAL模式和忙等待"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    """初始化数据库，创建所有表"""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    from backend.models import (
        StockPool, StockDailyData, StockRecommendation, SectorAnalysis,
        SectorStockPick, SchedulerLog
    )
    Base.metadata.create_all(bind=engine)

    # 迁移：为已存在的表添加新字段（SQLite不支持IF NOT EXISTS列，需try）
    _migrate_add_columns()


def _migrate_add_columns():
    """增量迁移：添加新版本所需的字段"""
    migrations = [
        "ALTER TABLE sector_analysis ADD COLUMN ma_signal VARCHAR(15) DEFAULT 'HOLD'",
        "ALTER TABLE sector_stock_picks ADD COLUMN signal_type VARCHAR(20) DEFAULT 'SECTOR_BUY'",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(import_text(sql))
                conn.commit()
            except Exception:
                # 字段已存在，忽略
                conn.rollback()


def get_db():
    """FastAPI依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
