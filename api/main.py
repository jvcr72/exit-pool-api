import hashlib
import logging
from typing import List
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from .database import get_db, rls_transaction
from .models import Resultado

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExitPoll_API")

app = FastAPI(
    title="Exit Poll Maneiro 2026",
    version="1.0.0"
)

class VoteRecord(BaseModel):
    id_registrosnvoto: str
    timestamp: str
    latitud: float
    longitud: float
    voto: str
    id_encuestador: str
    centro_votacion: str
    hash_validacion: str

class SyncPayload(BaseModel):
    records: List[VoteRecord]

def verify_sha256_integrity(record: VoteRecord) -> bool:
    lat = f"{record.latitud:.6f}"
    lon = f"{record.longitud:.6f}"
    validation_string = f"{record.id_encuestador}:{record.timestamp}:{lat}:{lon}:{record.voto}"
    calculated_hash = hashlib.sha256(validation_string.encode("utf-8")).hexdigest()
    return calculated_hash == record.hash_validacion.strip().lower()

def authenticate_pollster(token: str, db: Session) -> str:
    if not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Esquema inválido")
    actual_token = token.split(" ")[1]
    query = text("SELECT token_aud FROM encuestadores WHERE token_aud = :t")
    result = db.execute(query, {"t": actual_token}).fetchone()
    if not result:
        raise HTTPException(status_code=401, detail="Token no autorizado")
    return actual_token

@app.get("/")
def read_root():
    return HTMLResponse(content="<h1>Exit Poll API Activa</h1>")

@app.post("/api/v1/sync")
def sync_exit_poll(
    payload: SyncPayload,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    pollster_id = authenticate_pollster(authorization, db)
    synced_records = 0
    failed_list = []
    
    try:
        with rls_transaction(db, pollster_id) as session:
            for record in payload.records:
                if not verify_sha256_integrity(record):
                    failed_list.append({"id": record.id_registrosnvoto, "error": "Integridad fallida"})
                    continue
                
                try:
                    with session.begin_nested():
                        db_record = Resultado(
                            id_registrosnvoto=record.id_registrosnvoto,
                            timestamp=datetime.fromisoformat(record.timestamp),
                            latitud=record.latitud,
                            longitud=record.longitud,
                            voto=record.voto,
                            hash_validacion=record.hash_validacion,
                            id_encuestador=record.id_encuestador,
                            centro_votacion=record.centro_votacion
                        )
                        session.add(db_record)
                        session.flush()
                    synced_records += 1
                except Exception as e:
                    failed_list.append({"id": record.id_registrosnvoto, "error": str(e)})
                    
    except Exception as trans_err:
        return {"status": "error", "message": str(trans_err)}

    return {
        "status": "success",
        "message": "Sincronizado correctamente",
        "synced_count": synced_records,
        "failed_records": failed_list
    }