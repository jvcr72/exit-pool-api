import os
import sys
import uvicorn

def read_db_url():
    possible_paths = [
        "db/db_url.txt",
        "db_url.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    return None

def start_server():
    db_url = read_db_url()
    if not db_url:
        print("[ERROR] Database URL file 'db/db_url.txt' not found.")
        print("Please configure Neon connection first.")
        sys.exit(1)
        
    # Inject database URL into environment variables
    os.environ["DATABASE_URL"] = db_url
    print(f"[CONFIG] Loaded Neon Cloud Database connection.")
    print("[SERVER] Starting FastAPI server on http://localhost:8000")
    print("[SERVER] API documentation available at http://localhost:8000/docs")
    
    # Run Uvicorn server (port 8000, accessible from other devices in the local network)
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    start_server()
