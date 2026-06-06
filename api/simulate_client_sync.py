import hashlib
import uuid
import httpx
import json
from datetime import datetime, timezone

# Server URL (Local endpoint running in background)
SERVER_URL = "http://localhost:8000/api/v1/sync"

# Pollster configuration (Registered in Step 2)
POLLSTER_ID = "ENC-001"
BEARER_TOKEN = "ab896e51488ac65d715a1660052e3378"

def generate_signed_vote(voto_candidato, centro_votacion, lat, lng):
    """
    Simulates a vote registered in the mobile app, generating
    all fields and computing the SHA-256 integrity hash.
    """
    id_voto = f"vote-{uuid.uuid4().hex[:12]}"
    
    # ISO 8601 Timestamp (Local/UTC representation)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Calculate SHA-256 hash precisely: id_encuestador + ":" + timestamp + ":" + latitud + ":" + longitud + ":" + voto
    validation_string = f"{POLLSTER_ID}:{timestamp}:{lat}:{lng}:{voto_candidato}"
    hash_signature = hashlib.sha256(validation_string.encode("utf-8")).hexdigest()
    
    return {
        "id_registrosnvoto": id_voto,
        "timestamp": timestamp,
        "latitud": lat,
        "longitud": lng,
        "voto": voto_candidato,
        "id_encuestador": POLLSTER_ID,
        "centro_votacion": centro_votacion,
        "hash_validacion": hash_signature
    }

def simulate_sync():
    print(f"\n[CLIENT] Generating 4 mock voter responses taken in the field...")
    
    # Coordinates close to voting centers in Maneiro, Nueva Esparta
    # Center 1: U.E. Colegio El Ángel (Approx: 10.9922, -63.8051)
    # Center 2: Casa de la Cultura Manuel Plácido Maneiro (Approx: 10.9996, -63.8005)
    
    votes = [
        generate_signed_vote("CANDIDATO_B", "U.E. Colegío El Ángel", 10.99225, -63.80512),
        generate_signed_vote("CANDIDATO_B", "U.E. Colegío El Ángel", 10.99221, -63.80509),
        generate_signed_vote("CANDIDATO_A", "U.E. Colegío El Ángel", 10.99228, -63.80515),
        generate_signed_vote("CANDIDATO_B", "Casa de la Cultura Manuel Plácido Maneiro", 10.99965, -63.80052),
    ]
    
    payload = {
        "records": votes
    }
    
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    
    print(f"[CLIENT] Sending sync payload batch to server: {SERVER_URL}")
    print(f"[CLIENT] Authenticating as: {POLLSTER_ID}")
    
    try:
        response = httpx.post(SERVER_URL, headers=headers, json=payload, timeout=30.0)
        print(f"\n[SERVER RESPONSE - STATUS {response.status_code}]:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"[CLIENT ERROR] Connection failed: {e}")



if __name__ == "__main__":
    simulate_sync()
