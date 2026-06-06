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

# Nueva ruta para alimentar el Dashboard
@app.get("/api/v1/projections")
def get_projections(db: Session = Depends(get_db)):
    try:
        total_votos = db.query(Resultado).count()
        
        # Enviamos los datos con los nombres más comunes que el JS suele buscar
        return {
            "votos_registrados": total_votos,
            "votosRegistrados": total_votos,  # Por si busca en camelCase
            "censo_total": 0,
            "censoTotal": 0,
            "censo_muestreado": total_votos,
            "censoMuestreado": total_votos,
            "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
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