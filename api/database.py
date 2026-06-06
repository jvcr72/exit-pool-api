import os
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Fetch database URL from environment variable or default to local Postgres
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/exitpoll")

# SQLite fallback check (primarily for local mock testing environments)
is_sqlite = DATABASE_URL.startswith("sqlite")

# Configure database engine
if is_sqlite:
    # SQLite configuration needs check_same_thread=False for FastAPI
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Postgres engine with standard connection pool settings
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True, 
        pool_size=10, 
        max_overflow=20
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base for ORM models
Base = declarative_base()

def get_db():
    """FastAPI Dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def rls_transaction(db, pollster_id: str):
    """
    Context manager to run transactions with PostgreSQL Row-Level Security (RLS).
    Sets 'app.current_pollster_id' locally in the transaction scope.
    """
    in_trans = db.in_transaction()
    if not in_trans:
        transaction = db.begin()
    
    try:
        if not is_sqlite:
            # Set transaction-local configuration for PostgreSQL RLS
            db.execute(
                text("SELECT set_config('app.current_pollster_id', :pollster_id, true)"),
                {"pollster_id": pollster_id}
            )
        else:
            # SQLite fallback logger/stub
            pass
            
        yield db
        
        # Commit at the appropriate level
        if not in_trans:
            transaction.commit()
        else:
            db.commit()
    except Exception as e:
        if not in_trans:
            transaction.rollback()
        else:
            db.rollback()
        raise e

