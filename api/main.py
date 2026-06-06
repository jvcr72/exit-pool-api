import hashlib
import logging
import os
from typing import List
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .database import get_db, rls_transaction
from .models import Encuestador, Resultado

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExitPoll_API")

app = FastAPI(title="Exit Poll Municipal - Maneiro 2026")

# ... (Modelos Pydantic iguales) ...
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

class SyncResponse(BaseModel):
    status: str
    message: str
    synced_count: int
    failed_records: List[dict] = []

# ... (Funciones auxiliares iguales) ...
def verify_sha256_integrity(record: VoteRecord) -> bool:
    val_str = f"{record.id_encuestador}:{record.timestamp}:{record.latitud}:{record.longitud}:{record.voto}"
    calc_hash = hashlib.sha256(val_str.encode("utf-8")).hexdigest()
    return calc_hash == record.hash_validacion.strip().lower()

@app.post("/api/v1/sync", response_model=SyncResponse)
def sync_exit_poll(payload: SyncPayload, authorization: str = Header(...), db: Session = Depends(get_db)):
    try:
        # 1. Autenticación
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token inválido")
        token = authorization.split(" ")[1]
        pollster = db.query(Encuestador).filter(Encuestador.token_aud == token).first()
        if not pollster:
            raise HTTPException(status_code=401, detail="No autorizado")
        
        pollster_id = pollster.id
        synced = 0
        failed = []

        # 2. Transacción
        with rls_transaction(db, pollster_id) as session:
            for record in payload.records:
                if not verify_sha256_integrity(record):
                    failed.append({"id": record.id_registrosnvoto, "error": "Hash inválido"})
                    continue
                
                try:
                    new_vote = Resultado(
                        id_registrosnvoto=record.id_registrosnvoto,
                        timestamp=datetime.fromisoformat(record.timestamp),
                        latitud=record.latitud,
                        longitud=record.longitud,
                        voto=record.voto,
                        hash_validacion=record.hash_validacion,
                        id_encuestador=record.id_encuestador,
                        centro_votacion=record.centro_votacion
                    )
                    session.add(new_vote)
                    session.flush()
                    synced += 1
                except Exception as e:
                    failed.append({"id": record.id_registrosnvoto, "error": str(e)})
            
            session.commit()
            
        return SyncResponse(status="success", message="Sincronización completada", synced_count=synced, failed_records=failed)

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error BD: {str(e)}")
    
    finally:
        # ESTE ES EL CIERRE QUE RECLAMAS
        db.close()

# ... (Rutas HTML con ruta absoluta) ...
@app.get("/dashboard", response_class=HTMLResponse)
def read_dashboard():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/mobile", response_class=HTMLResponse)
def read_mobile():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mobile.html")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())