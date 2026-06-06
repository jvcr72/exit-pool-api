import os

TEST_DB_FILE = "exitpoll_test.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_FILE}"
EXCEL_FILE = "mock_votantes.xlsx"

# Override database URL for testing immediately before imports
os.environ["DATABASE_URL"] = TEST_DB_URL

import sqlite3
import hashlib
import json
from datetime import datetime
from fastapi.testclient import TestClient

# Import our system modules
from etl.generate_mock_excel import generate_mock_excel
from etl.etl_ingesta import run_etl
from api.main import app
from api.database import SessionLocal, engine, Base
from analysis.weighting import calculate_weighted_projection


def setup_sqlite_database():
    """Reads schema.sql, strips Postgres-only syntax, and applies it to SQLite."""
    print("Setting up local SQLite database for verification...")
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)
        
    conn = sqlite3.connect(TEST_DB_FILE)
    cursor = conn.cursor()
    
    schema_path = os.path.join("db", "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    # Remove Postgres-specific commands that SQLite doesn't support
    statements = schema_sql.split(";")
    for stmt in statements:
        stmt_clean = stmt.strip()
        if not stmt_clean:
            continue
        # Skip RLS features not supported by SQLite
        if any(keyword in stmt_clean.upper() for keyword in ["ROW LEVEL SECURITY", "POLICY", "SET LOCAL"]):
            print(f"Skipping Postgres-specific SQL statement: {stmt_clean[:50]}...")
            continue
        try:
            cursor.execute(stmt_clean)
        except Exception as e:
            print(f"Error running SQL statement: {stmt_clean[:50]}...")
            print(e)
            
    conn.commit()
    conn.close()

def seed_pollsters():
    """Seeds pollsters in the database for API testing."""
    print("Seeding pollsters...")
    conn = sqlite3.connect(TEST_DB_FILE)
    cursor = conn.cursor()
    
    # Insert two test pollsters
    cursor.execute(
        "INSERT INTO encuestadores (id, token_aud, estado_conexion) VALUES (?, ?, ?)",
        ("ENC-001", "token-maneiro-001", "desconectado")
    )
    cursor.execute(
        "INSERT INTO encuestadores (id, token_aud, estado_conexion) VALUES (?, ?, ?)",
        ("ENC-002", "token-maneiro-002", "desconectado")
    )
    
    conn.commit()
    conn.close()

def test_api_sync():
    """Uses FastAPI TestClient to test security and validation checks on api/v1/sync."""
    print("\n--- Testing API Sync Endpoint ---")
    client = TestClient(app)
    
    # 1. Test Authorization check
    print("1. Sending request without token...")
    resp = client.post("/api/v1/sync", json={"records": []})
    assert resp.status_code == 422, f"Expected 422 for missing headers, got {resp.status_code}"
    print("   [OK] Missing token caught correctly.")
    
    print("2. Sending request with invalid token...")
    resp = client.post(
        "/api/v1/sync", 
        headers={"Authorization": "Bearer invalid-token"}, 
        json={"records": []}
    )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    print("   [OK] Invalid token rejected correctly.")
    
    # 3. Synchronize valid exit poll record
    print("3. Synchronizing a valid vote record...")
    # Record parameters
    id_voto = "voto-uuid-999"
    timestamp = "2026-05-28T20:00:00-04:00"
    lat = 10.9984
    lng = -63.8115
    voto_candidato = "CANDIDATO_A"
    id_encuestador = "ENC-001"
    centro = "U.E. Nacional Bernardo Acosta"
    
    # Calculate valid SHA-256
    val_string = f"{id_encuestador}:{timestamp}:{lat}:{lng}:{voto_candidato}"
    valid_hash = hashlib.sha256(val_string.encode("utf-8")).hexdigest()
    
    payload = {
        "records": [
            {
                "id_registrosnvoto": id_voto,
                "timestamp": timestamp,
                "latitud": lat,
                "longitud": lng,
                "voto": voto_candidato,
                "id_encuestador": id_encuestador,
                "centro_votacion": centro,
                "hash_validacion": valid_hash
            }
        ]
    }
    
    resp = client.post(
        "/api/v1/sync",
        headers={"Authorization": "Bearer token-maneiro-001"},
        json=payload
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    resp_json = resp.json()
    assert resp_json["status"] == "success"
    assert resp_json["synced_count"] == 1
    print("   [OK] Valid record successfully synchronized!")
    
    # 4. Synchronize record with invalid hash signature (Integrity check fail)
    print("4. Synchronizing a record with a corrupted hash...")
    payload_corrupt = payload.copy()
    payload_corrupt["records"][0]["id_registrosnvoto"] = "voto-uuid-888"
    payload_corrupt["records"][0]["hash_validacion"] = "fakehash123"
    
    resp = client.post(
        "/api/v1/sync",
        headers={"Authorization": "Bearer token-maneiro-001"},
        json=payload_corrupt
    )
    assert resp.status_code == 200
    resp_json = resp.json()
    assert resp_json["synced_count"] == 0
    assert len(resp_json["failed_records"]) == 1
    assert "integrity verification failed" in resp_json["failed_records"][0]["error"].lower()
    print("   [OK] Integrity check correctly blocked corrupted hash.")
    
    # 5. Synchronize record for a different pollster (RLS/Auth boundary validation)
    print("5. Synchronizing record belonging to ENC-002 using ENC-001's token...")
    payload_wrong_user = payload.copy()
    payload_wrong_user["records"][0]["id_registrosnvoto"] = "voto-uuid-777"
    payload_wrong_user["records"][0]["id_encuestador"] = "ENC-002"  # Belongs to ENC-002
    
    # Recalculate hash for ENC-002
    val_string = f"ENC-002:{timestamp}:{lat}:{lng}:{voto_candidato}"
    wrong_user_hash = hashlib.sha256(val_string.encode("utf-8")).hexdigest()
    payload_wrong_user["records"][0]["hash_validacion"] = wrong_user_hash
    
    resp = client.post(
        "/api/v1/sync",
        headers={"Authorization": "Bearer token-maneiro-001"},  # Authenticated as ENC-001
        json=payload_wrong_user
    )
    assert resp.status_code == 200
    resp_json = resp.json()
    assert resp_json["synced_count"] == 0
    assert len(resp_json["failed_records"]) == 1
    assert "pollster id mismatch" in resp_json["failed_records"][0]["error"].lower()
    print("   [OK] Pollster ID mismatch blocked successfully.")

def add_mock_votes_for_weighting():
    """Adds a distributed set of votes across centers to demonstrate weighting calculations."""
    print("\nAdding distributed votes to test weighting calculations...")
    client = TestClient(app)
    
    # We want to create bias in the sample:
    # Center A: U.E. Nacional Bernardo Acosta (large census, say 30 voters in mock)
    # Center B: U.E. Colegío El Ángel (small census, say 10 voters in mock)
    # If candidate X gets 90% in Center B (small) but only 10% in Center A (large)
    # An unweighted total would bias towards wherever we took more samples.
    # We will simulate more samples in Center B (the small center), which is typical of biased polling.
    
    # Let's count voters per center in db
    conn = sqlite3.connect(TEST_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT centro_votacion, COUNT(*) FROM votantes GROUP BY centro_votacion")
    centers = cursor.fetchall()
    print("Mock census count per center in DB:")
    for c, count in centers:
        print(f"  - {c}: {count} registered voters")
        
    # We will insert votes directly for simplicity and speed
    # ENC-001 votes in Center A
    # ENC-002 votes in Center B
    # Let's say:
    # Center A ("U.E. Nacional Bernardo Acosta"):
    # - CANDIDATO_A: 8 votes
    # - CANDIDATO_B: 2 votes
    # Center B ("U.E. Colegío El Ángel"):
    # - CANDIDATO_A: 1 vote
    # - CANDIDATO_B: 9 votes (CANDIDATO_B dominates here)
    
    votes = [
        # Center A
        ("v-a1", "2026-05-28T10:00:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a2", "2026-05-28T10:01:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a3", "2026-05-28T10:02:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a4", "2026-05-28T10:03:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a5", "2026-05-28T10:04:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a6", "2026-05-28T10:05:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a7", "2026-05-28T10:06:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a8", "2026-05-28T10:07:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a9", "2026-05-28T10:08:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        ("v-a10", "2026-05-28T10:09:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-001", "U.E. Nacional Bernardo Acosta"),
        
        # Center B
        ("v-b1", "2026-05-28T11:00:00-04:00", 10.9, -63.8, "CANDIDATO_A", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b2", "2026-05-28T11:01:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b3", "2026-05-28T11:02:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b4", "2026-05-28T11:03:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b5", "2026-05-28T11:04:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b6", "2026-05-28T11:05:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b7", "2026-05-28T11:06:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b8", "2026-05-28T11:07:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b9", "2026-05-28T11:08:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
        ("v-b10", "2026-05-28T11:09:00-04:00", 10.9, -63.8, "CANDIDATO_B", "ENC-002", "U.E. Colegío El Ángel"),
    ]
    
    # Unweighted total:
    # Total votes = 20.
    # CANDIDATO_A: 9 votes (45%)
    # CANDIDATO_B: 11 votes (55%)
    
    # Let's insert them using DB cursor to populate easily
    for id_v, ts, lat, lng, candidate, enc, center in votes:
        val_string = f"{enc}:{ts}:{lat}:{lng}:{candidate}"
        h = hashlib.sha256(val_string.encode("utf-8")).hexdigest()
        cursor.execute(
            "INSERT INTO resultados (id_registrosnvoto, timestamp, latitud, longitud, voto, hash_validacion, id_encuestador, centro_votacion) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (id_v, datetime.fromisoformat(ts), lat, lng, candidate, h, enc, center)
        )
        
    conn.commit()
    conn.close()
    print("   [OK] Mock votes added.")

def verify_weighting_output():
    """Runs the weighting logic and compares unweighted vs. weighted outcomes."""
    print("\n--- Running Weighting Calculation ---")
    results = calculate_weighted_projection(TEST_DB_URL)
    
    print("\nWeighting Calculation Output:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # Validate structure
    assert results["status"] == "success"
    assert "unweighted_results" in results
    assert "weighted_projection" in results
    print("\n   [OK] Weighting computation ran successfully!")

def run_tests():
    # 1. Generate Excel mock file
    print("Step 1: Generating mock Excel...")
    generate_mock_excel(EXCEL_FILE)
    
    # 2. Setup SQLite database
    setup_sqlite_database()
    
    # 3. Run ETL ingestion
    print("\nStep 2: Running ETL Ingestion script on mock Excel...")
    success, fails = run_etl(EXCEL_FILE, TEST_DB_URL)
    print(f"Ingested {success} records, failed {fails}.")
    
    # Check that database is populated
    conn = sqlite3.connect(TEST_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM votantes")
    voter_count = cursor.fetchone()[0]
    conn.close()
    print(f"Verified database has {voter_count} voters.")
    assert voter_count > 0, "No voters loaded into database!"
    
    # 4. Seed pollsters
    seed_pollsters()
    
    # 5. Run API sync tests
    test_api_sync()
    
    # 6. Test weighting calculations
    add_mock_votes_for_weighting()
    verify_weighting_output()
    
    print("\n" + "="*40)
    print(" ALL SYSTEM VERIFICATIONS PASSED SUCCESSFULLY! ")
    print("="*40 + "\n")

if __name__ == "__main__":
    run_tests()
