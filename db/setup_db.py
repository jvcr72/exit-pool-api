import os
import sys
from sqlalchemy import create_engine, text

def setup_db(db_url):
    print("Connecting to cloud database...")
    engine = create_engine(db_url)
    
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    print(f"Reading schema from: {schema_path}")
    
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    # Split queries by semicolon to execute them sequentially
    statements = schema_sql.split(";")
    
    with engine.begin() as connection:
        print("Executing schema setup...")
        for stmt in statements:
            stmt_clean = stmt.strip()
            if not stmt_clean:
                continue
            try:
                connection.execute(text(stmt_clean))
            except Exception as e:
                print(f"Failed to execute statement: {stmt_clean[:50]}...")
                print(f"Error: {e}")
                raise e
                
    print("\n[SUCCESS] PostgreSQL schema and RLS policies initialized successfully in Neon Cloud Database!")

if __name__ == "__main__":
    # URL retrieved from db_url.txt
    db_url = "postgresql://neondb_owner:npg_OCG0F7mzWASg@ep-polished-glitter-apkoqi87.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require"
    setup_db(db_url)
