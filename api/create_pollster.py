import secrets
import sys
import os
from sqlalchemy import create_engine, text

def read_db_url():
    # Attempt to read from the db_url.txt in the db directory
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "db", "db_url.txt"),
        os.path.join(os.path.dirname(__file__), "db", "db_url.txt"),
        "db/db_url.txt",
        "db_url.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
                
    # Fallback to environment variable
    return os.getenv("DATABASE_URL")

def create_pollster(pollster_id):
    db_url = read_db_url()
    if not db_url:
        print("[ERROR] Database URL not found. Ensure db_url.txt is in the project directories or set DATABASE_URL environment variable.")
        sys.exit(1)
        
    engine = create_engine(db_url)
    
    # Generate a cryptographically secure 32-character hex token
    token = secrets.token_hex(16)
    
    query = text("""
        INSERT INTO encuestadores (id, token_aud, estado_conexion) 
        VALUES (:id, :token, 'desconectado')
        ON CONFLICT (id) DO UPDATE SET token_aud = :token, estado_conexion = 'desconectado'
    """)
    
    try:
        with engine.begin() as connection:
            connection.execute(query, {"id": pollster_id, "token": token})
        print("\n" + "="*50)
        print(" ENCUESTADOR REGISTRADO EXITOSAMENTE EN LA NUBE ")
        print("="*50)
        print(f"ID Encuestador:  {pollster_id}")
        print(f"Token de Acceso: {token}")
        print(f"Estado Inicial:  desconectado")
        print("="*50)
        print("Guarda este token de acceso de manera segura. Se requerirá en la cabecera HTTP:")
        print(f"Authorization: Bearer {token}")
        print("="*50 + "\n")
    except Exception as e:
        print(f"[ERROR] Failed to register pollster in database: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python api/create_pollster.py [ID_ENCUESTADOR]")
        print("Ejemplo: python api/create_pollster.py ENC-001")
        sys.exit(1)
        
    pollster_id = sys.argv[1].strip()
    create_pollster(pollster_id)
