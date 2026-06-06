from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, func
from .database import Base

class Encuestador(Base):
    __tablename__ = 'encuestadores'
    
    id = Column(String(50), primary_key=True)
    token_aud = Column(String(255), unique=True, nullable=False)
    estado_conexion = Column(String(50), default='desconectado')
    created_at = Column(DateTime(timezone=True), default=func.now())

class Resultado(Base):
    __tablename__ = 'resultados'
    
    id_registrosnvoto = Column(String(50), primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    latitud = Column(Numeric(10, 8), nullable=False)
    longitud = Column(Numeric(11, 8), nullable=False)
    voto = Column(String(100), nullable=False)
    hash_validacion = Column(String(64), nullable=False)
    id_encuestador = Column(String(50), ForeignKey('encuestadores.id'), nullable=False)
    centro_votacion = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
