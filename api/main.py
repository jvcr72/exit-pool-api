import hashlib
import logging
from typing import List
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.responses import HTMLResponse

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text, Table, MetaData

from .database import get_db, rls_transaction
from .models import Encuestador, Resultado

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExitPoll_API")

app = FastAPI(
    title="Exit Poll Municipal - Maneiro (Nueva Esparta)",
    description="Backend API for electoral synchronization with Row-Level Security (RLS) and SHA-256 validation.",
    version="1.0.0"
)

# Pydantic models for request validation
class VoteRecord(BaseModel):
    id_registrosnvoto: str = Field(..., example="vote-uuid-12345")
    timestamp: str = Field(..., description="ISO 8601 formatted timestamp", example="2026-05-28T19:54:17-04:00")
    latitud: float = Field(..., example=10.9984)
    longitud: float = Field(..., example=-63.8115)
    voto: str = Field(..., description="Candidate name or party selected", example="CANDIDATO_A")
    id_encuestador: str = Field(..., example="ENC-001")
    centro_votacion: str = Field(..., description="Voting center name", example="U.E. Nacional Bernardo Acosta")
    hash_validacion: str = Field(..., description="SHA-256 validation hash", example="a9f8...")

class SyncPayload(BaseModel):
    records: List[VoteRecord]

class SyncResponse(BaseModel):
    status: str
    message: str
    synced_count: int
    failed_records: List[dict] = []

def verify_sha256_integrity(record: VoteRecord) -> bool:
    # Mantenemos la normalización
    lat = f"{record.latitud:.6f}"
    lon = f"{record.longitud:.6f}"
    ts = record.timestamp.strip()
    
    # NUEVO: Imprimimos la cadena exacta que usamos para calcular
    validation_string = f"{record.id_encuestador}:{record.timestamp}:{lat}:{lon}:{record.voto}"
    print(f"DEBUG_VALIDATION_STRING: {validation_string}") 
    
    calculated_hash = hashlib.sha256(validation_string.encode("utf-8")).hexdigest()
    
    received_hash = record.hash_validacion.strip().lower()
    match = (calculated_hash == received_hash)
    
    if not match:
        logger.warning(f"Integrity check failed. Calc: {calculated_hash}, Recv: {received_hash}")
    return match
def authenticate_pollster(token: str, db: Session) -> str:
    if not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Esquema inválido")
    actual_token = token.split(" ")[1]

    # Usamos la tabla donde están tus tokens reales
    query = text("SELECT token_aud FROM encuestadores WHERE token_aud = :t")
    result = db.execute(query, {"t": actual_token}).fetchone()

    if not result:
        raise HTTPException(status_code=401, detail="Token no autorizado")

    return actual_token



@app.get("/", response_class=HTMLResponse)
def read_root():
    """
    Returns the visual exit poll portal landing page.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Exit Poll Maneiro 2026 - Portal</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            body {
                background-color: #0b0f19;
                color: #f3f4f6;
                font-family: 'Outfit', sans-serif;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 1.5rem;
                background-image: radial-gradient(at 50% 50%, rgba(59, 130, 246, 0.15) 0px, transparent 50%);
            }
            .portal-card {
                background: rgba(17, 24, 39, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 24px;
                padding: 3rem 2rem;
                max-width: 500px;
                width: 100%;
                text-align: center;
                backdrop-filter: blur(12px);
                box-shadow: 0 20px 50px rgba(0,0,0,0.3);
            }
            h1 {
                font-size: 2.2rem;
                font-weight: 700;
                margin-bottom: 0.5rem;
                background: linear-gradient(to right, #3b82f6, #60a5fa);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            p {
                color: #9ca3af;
                font-size: 1rem;
                margin-bottom: 2.5rem;
            }
            .btn-group {
                display: flex;
                flex-direction: column;
                gap: 1.2rem;
            }
            .btn-portal {
                display: block;
                padding: 1.2rem;
                border-radius: 12px;
                text-decoration: none;
                font-weight: 600;
                font-size: 1.1rem;
                transition: all 0.2s;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            .btn-dashboard {
                background: #3b82f6;
                color: white;
                box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
            }
            .btn-dashboard:hover {
                background: #2563eb;
                transform: translateY(-2px);
            }
            .btn-mobile {
                background: rgba(255, 255, 255, 0.03);
                color: #f3f4f6;
            }
            .btn-mobile:hover {
                background: rgba(255, 255, 255, 0.08);
                transform: translateY(-2px);
            }
        </style>
    </head>
    <body>
        <div class="portal-card">
            <h1>Exit Poll Maneiro 2026</h1>
            <p>Selecciona la aplicación a la que deseas acceder</p>
            <div class="btn-group">
                <a href="/dashboard" class="btn-portal btn-dashboard">📊 Centro de Control (Dashboard)</a>
                <a href="/mobile" class="btn-portal btn-mobile">📱 Captura de Votos (Móvil)</a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)


@app.post("/api/v1/sync", response_model=SyncResponse)
def sync_exit_poll(
    payload: SyncPayload,
    authorization: str = Header(..., description="Bearer <token_aud>"),
    db: Session = Depends(get_db)
):
    # 1. Authenticate pollster
    pollster_id = authenticate_pollster(authorization, db)
    logger.info(f"Pollster '{pollster_id}' authenticated successfully.")
    
    synced_records = 0
    failed_list = []
    
    # Use RLS-scoped transaction context manager
    # Ensures database operates under 'app.current_pollster_id = pollster_id'
    try:
        with rls_transaction(db, pollster_id) as session:
            for record in payload.records:
                # 2. Check if this record belongs to the authenticated pollster
                # (Even if they try to bypass, database RLS policies will reject it,
                # but API level checking provides a cleaner error description).
                if record.id_encuestador != pollster_id:
                    failed_list.append({
                        "id_registrosnvoto": record.id_registrosnvoto,
                        "error": f"Unauthorized: Pollster ID mismatch. Authenticated as '{pollster_id}' but record lists '{record.id_encuestador}'"
                    })
                    continue
                
                # 3. Verify SHA-256 integrity
                if not verify_sha256_integrity(record):
                    failed_list.append({
                        "id_registrosnvoto": record.id_registrosnvoto,
                        "error": "Data integrity verification failed. Computed SHA-256 does not match hash_validacion."
                    })
                    continue
                
                # Parse timestamp
                try:
                    parsed_time = datetime.fromisoformat(record.timestamp)
                except ValueError:
                    failed_list.append({
                        "id_registrosnvoto": record.id_registrosnvoto,
                        "error": f"Invalid timestamp format: '{record.timestamp}'. Must be ISO 8601"
                    })
                    continue
                
                # 4. Insert record into DB using a transaction savepoint
                # If Postgres RLS is bypassed or fails, the policy will throw a DB error.
                try:
                    with session.begin_nested():
                        db_record = Resultado(
                            id_registrosnvoto=record.id_registrosnvoto,
                            timestamp=parsed_time,
                            latitud=record.latitud,
                            longitud=record.longitud,
                            voto=record.voto,
                            hash_validacion=record.hash_validacion,
                            id_encuestador=record.id_encuestador,
                            centro_votacion=record.centro_votacion
                        )
                        session.add(db_record)
                        session.flush() # Forces SQL execution to trigger savepoint check

                    synced_records += 1
                except Exception as db_err:
                    # Capture RLS Policy violation or Unique constraint error
                    db_err_msg = str(db_err.orig).replace('\n', ' ') if hasattr(db_err, 'orig') else str(db_err)
                    logger.error(f"Failed DB insert for record {record.id_registrosnvoto}: {db_err_msg}")
                    failed_list.append({
                        "id_registrosnvoto": record.id_registrosnvoto,
                        "error": f"Database insertion failed: {db_err_msg}"
                    })


                    
    except Exception as trans_err:
        logger.exception("Transaction rolled back due to error:")
        # Return error response
        return SyncResponse(
            status="error",
            message="Synchronization transaction failed and was rolled back.",
            synced_count=0,
            failed_records=[{"error": str(trans_err)}]
        )
        
    return SyncResponse(
        status="success",
        message="Sync processed successfully.",
        synced_count=synced_records,
        failed_records=failed_list
    )

@app.get("/api/v1/projections")
def get_projections():
    """
    Returns unweighted vs. weighted vote projections from the cloud database.
    Since this is the analyst's global dashboard query, it operates at the root level,
    bypassing RLS policies by using the primary DATABASE_URL connection.
    """
    from .database import DATABASE_URL
    from analysis.weighting import calculate_weighted_projection
    return calculate_weighted_projection(DATABASE_URL)

@app.get("/dashboard", response_class=HTMLResponse)
def read_dashboard():
    """
    Returns the visual exit poll control panel dashboard web app.
    """
    import os
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/mobile", response_class=HTMLResponse)
def read_mobile():
    """
    Returns the visual mobile capture exit poll application.
    """
    import os
    html_path = os.path.join(os.path.dirname(__file__), "mobile.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)


