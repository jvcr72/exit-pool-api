import pandas as pd
import random

def generate_mock_excel(filename="mock_votantes.xlsx"):
    # Real voting centers in Maneiro Municipality, Nueva Esparta
    centers = [
        "U.E. Nacional Bernardo Acosta",
        "U.E. Colegío El Ángel",
        "C.E.I. Luisa Cáceres de Arismendi",
        "U.E. Estado Zulia",
        "Liceo U.E. Angel Noriega Baloa",
        "Casa de la Cultura Manuel Plácido Maneiro"
    ]
    
    names = ["José", "María", "Juan", "Ana", "Carlos", "Luis", "Carmen", "Francisco", "Luisa", "Pedro", "Rosa", "Miguel"]
    surnames = ["Rodríguez", "González", "Hernández", "García", "Martínez", "Pérez", "López", "Gómez", "Díaz", "Sánchez", "Álvarez"]
    
    data = []
    
    # Add 50 clean, valid records
    for i in range(1, 51):
        cedula_num = 12000000 + i * 137
        cedula_raw = f"V-{cedula_num:,}".replace(",", ".") # e.g. V-12.000.137
        
        # Introduce some variety in format for normalization testing
        if i % 5 == 0:
            cedula_raw = f"V {cedula_num}"
        elif i % 5 == 1:
            cedula_raw = str(cedula_num)
        elif i % 5 == 2:
            cedula_raw = f"v-{cedula_num}"
        elif i % 5 == 3:
            # Foreigner
            cedula_raw = f"E-{cedula_num + 5000000}"
            
        phone = f"0414-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
        email = f"{random.choice(names).lower()}.{random.choice(surnames).lower()}@gmail.com"
        
        data.append({
            "Nombre": random.choice(names),
            "Apellidos": random.choice(surnames),
            "Telefono": phone,
            "Direccion de Residencia": f"Calle {random.randint(1,15)}, Urbanización Pampatar, Maneiro",
            "Cedula": cedula_raw,
            "Centro de Votacion": random.choice(centers),
            "Mesa donde vota": random.randint(1, 4),
            "Correo Electronico": email
        })
        
    # Add 5 Duplicate Cedulas (to test deduplication and duplicate error logging)
    for i in range(5):
        dup_base = data[i]
        data.append({
            "Nombre": dup_base["Nombre"],
            "Apellidos": dup_base["Apellidos"] + " (Duplicate)",
            "Telefono": dup_base["Telefono"],
            "Direccion de Residencia": dup_base["Direccion de Residencia"],
            "Cedula": dup_base["Cedula"],  # Duplicate ID
            "Centro de Votacion": dup_base["Centro de Votacion"],
            "Mesa donde vota": dup_base["Mesa donde vota"],
            "Correo Electronico": "dup_" + dup_base["Correo Electronico"]
        })
        
    # Add 3 rows with missing critical data (to test validations and logging)
    data.append({
        "Nombre": "MissingCedulaVoter",
        "Apellidos": "NoCedula",
        "Telefono": "0424-999-9999",
        "Direccion de Residencia": "Calle Principal, Pampatar",
        "Cedula": None,  # Missing Cedula
        "Centro de Votacion": "U.E. Colegío El Ángel",
        "Mesa donde vota": 1,
        "Correo Electronico": "nocedula@example.com"
    })
    
    data.append({
        "Nombre": None,  # Missing Name
        "Apellidos": "NoNombre",
        "Telefono": "0424-999-9998",
        "Direccion de Residencia": "Calle Principal, Pampatar",
        "Cedula": "V-99999999",
        "Centro de Votacion": "U.E. Colegío El Ángel",
        "Mesa donde vota": 1,
        "Correo Electronico": "noname@example.com"
    })
    
    data.append({
        "Nombre": "MissingMesaVoter",
        "Apellidos": "NoMesa",
        "Telefono": "0424-999-9997",
        "Direccion de Residencia": "Calle Principal, Pampatar",
        "Cedula": "V-99999998",
        "Centro de Votacion": "U.E. Colegío El Ángel",
        "Mesa donde vota": None,  # Missing Mesa
        "Correo Electronico": "nomesa@example.com"
    })

    # Convert to DataFrame and write to Excel
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Generated mock Excel file: '{filename}' with {len(df)} total rows.")

if __name__ == "__main__":
    generate_mock_excel()
