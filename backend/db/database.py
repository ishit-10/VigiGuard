"""
Database connection and session management.
"""
import os
import sys
import yaml
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "backend", "config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

DATABASE_URL = config['database']['url']

# Ensure database directory exists
db_dir = os.path.dirname(DATABASE_URL.replace('sqlite:///', ''))
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    echo=config['database']['echo_sql'],
    pool_size=config['database']['pool_size'],
    max_overflow=config['database']['max_overflow'],
    connect_args={"check_same_thread": False} if 'sqlite' in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database - create all tables."""
    import backend.db.models  # noqa: F401 - Import models to register them
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized: {DATABASE_URL}")