# Sistema de Exit Poll Municipal - Maneiro, Estado Nueva Esparta

Este repositorio contiene la arquitectura y el backend completo para un sistema de exit poll electoral a nivel municipal para el municipio Maneiro del estado Nueva Esparta. El sistema garantiza la integridad de los datos mediante firmas criptográficas SHA-256, aplica políticas de seguridad a nivel de base de datos (Row-Level Security - RLS) para aislar los datos entre encuestadores, provee un motor de ingesta ETL para limpiar el censo oficial de votantes, y calcula proyecciones estadísticas ponderadas.

## Estructura del Proyecto

```
exitpool/
├── db/
│   └── schema.sql          # Esquema de base de datos (PostgreSQL DDL + RLS)
├── etl/
│   ├── etl_ingesta.py      # Script de ingesta ETL (Pandas + SQLAlchemy)
│   └── generate_mock_excel.py # Generador de datos simulados de votantes (.xlsx)
├── api/
│   ├── main.py             # Servidor API FastAPI con endpoints de sincronización
│   └── database.py         # Configuración de base de datos y transacciones RLS
├── analysis/
│   └── weighting.py        # Algoritmo de ponderación electoral estadístico
├── requirements.txt        # Dependencias de Python requeridas
├── test_system.py          # Script de prueba e integración del sistema completo
└── README.md               # Documentación y guía de uso
```

---

## 1. Esquema de Base de Datos (PostgreSQL)

El esquema implementado en `db/schema.sql` consta de tres tablas principales con sus índices y políticas RLS:

- **`encuestadores`**: Registra los encuestadores de campo autorizados, sus tokens de auditoría y estado de conexión actual.
- **`votantes`**: Contiene el censo o padrón de votantes registrados del Municipio Maneiro.
- **`resultados`**: Registra las respuestas recolectadas del exit poll con sus marcas geográficas, timestamp, el voto y firmas SHA-256.

### Aislamiento de Datos por Row-Level Security (RLS)
Para asegurar que un encuestador no acceda ni manipule registros de otro, se activa RLS en la tabla `resultados`:
```sql
ALTER TABLE resultados ENABLE ROW LEVEL SECURITY;
ALTER TABLE resultados FORCE ROW LEVEL SECURITY;
```
Y se crea una política vinculada al parámetro de sesión de PostgreSQL `app.current_pollster_id`:
```sql
CREATE POLICY pollster_isolation_policy ON resultados
    FOR ALL
    TO public
    USING (id_encuestador = current_setting('app.current_pollster_id', true))
    WITH CHECK (id_encuestador = current_setting('app.current_pollster_id', true));
```
Al ejecutar inserts o consultas en la API, la conexión establece esta variable local dentro de la transacción:
```sql
SET LOCAL app.current_pollster_id = 'id_del_encuestador';
```

---

## 2. Ingesta ETL de Votantes

El script `etl/etl_ingesta.py` procesa los registros de votantes desde un archivo Excel (`.xlsx`).

### Procesamientos y Limpieza:
1. **Normalización de Cédulas**: Remueve espacios, puntos y guiones. Reconoce nacionalidad (V = Venezolano, E = Extranjero). Formatea las cédulas al estándar `V[número]` o `E[número]` de forma consistente (ej. `"V- 12.345.678 "` -> `"V12345678"`).
2. **Normalización de Correos y Teléfonos**: Convierte correos a minúsculas y valida su formato; los números telefónicos se limpian para contener únicamente caracteres numéricos y el prefijo `+` si aplica.
3. **Eliminación de Duplicados**: Identifica duplicados por número de cédula en el archivo Excel, conservando el primero y descartando los subsiguientes.
4. **Inserción Transaccional con Gestión de Errores**: Inserta los registros procesados en la base de datos de manera transaccional. En caso de que algún registro falle por restricciones de base de datos (por ejemplo, clave primaria duplicada o datos nulos), se captura de forma individual, se cancela la transacción parcial (`SAVEPOINT`) de ese registro y se escribe un reporte en el log de fallas `etl_errors.log` para permitir que el resto de los votantes se ingesten sin problemas.

---

## 3. Seguridad y API de Sincronización

El servidor FastAPI (`api/main.py`) expone el endpoint `POST /api/v1/sync`.

### Flujo de Sincronización y Validación:
1. **Autenticación**: El cliente móvil del encuestador envía un encabezado HTTP `Authorization: Bearer <token_aud>`. La API valida el token contra la tabla `encuestadores` y obtiene el ID del encuestador (`id_encuestador`).
2. **Validación de Integridad SHA-256**: Para cada registro del exit poll recibido, la API calcula el hash SHA-256 localmente concatenando las variables:
   $$\text{Hash} = \text{SHA256}(\text{id\_encuestador} + ":" + \text{timestamp} + ":" + \text{latitud} + ":" + \text{longitud} + ":" + \text{voto})$$
   Si el hash calculado no coincide exactamente con el `hash_validacion` provisto por el dispositivo, el registro es marcado como fallido por alteración de datos.
3. **Aplicación de RLS**: Las inserciones se ejecutan dentro de la transacción con la identidad del encuestador configurada en el contexto de sesión de la base de datos. Cualquier intento de insertar un registro con un `id_encuestador` diferente es bloqueado tanto a nivel de API como por la política RLS de la base de datos.

---

## 4. Lógica de Ponderación Electoral

Dado que la recolección de muestras de un exit poll en campo tiende a no ser homogénea, se aplica una **ponderación post-estratificación** basada en el censo electoral oficial cargado por centro de votación.

### Formulación Matemática:
Sea:
- $C_{muestreados}$ el conjunto de centros de votación que poseen al menos un voto registrado en el exit poll.
- $N_c$ el total de votantes oficiales en el censo para el centro $c$.
- $N_{sampled} = \sum_{c \in C_{muestreados}} N_c$ la sumatoria de votantes de todos los centros con muestras.
- $W_c = \frac{N_c}{N_{sampled}}$ el factor de peso asignado al centro $c$ (proporción del centro sobre el total de la muestra).
- $n_c$ la cantidad de votos de muestra recolectados en el centro $c$.
- $v_c(i)$ los votos en muestra para el candidato $i$ en el centro $c$.

La proyección ponderada final para el candidato $i$ ($P_i$) se calcula como:
$$P_i = \sum_{c \in C_{muestreados}} \left( W_c \cdot \frac{v_c(i)}{n_c} \right)$$

Este algoritmo, implementado en `analysis/weighting.py`, compensa el submuestreo o sobremuestreo de centros de votación específicos en Maneiro, proporcionando un resultado proyectado no sesgado.

---

## Instrucciones para Iniciar y Probar el Sistema

### 1. Clonar e Instalar Dependencias
Instala los paquetes de Python requeridos:
```bash
pip install -r requirements.txt
```
*(Nota: Para ejecutar las pruebas automatizadas, también se requiere `httpx` para el TestClient de FastAPI: `pip install httpx`)*

### 2. Ejecutar la Verificación Automática (Simulación Completa)
Para verificar el correcto funcionamiento del ETL, la API con firmas de seguridad, y las matemáticas de la ponderación de manera local y rápida sin requerir una base de datos PostgreSQL activa:
```bash
python test_system.py
```
Este script inicializará una base de datos SQLite de prueba (`exitpoll_test.db`), generará un archivo Excel con cédulas desordenadas y duplicadas, ejecutará la limpieza ETL, probará los endpoints de la API (validando tokens, firmas correctas e incorrectas e intentos de usurpación de encuestador) y finalmente calculará la proyección ponderada de votación.

### 3. Configuración en Producción (PostgreSQL)
Para iniciar el sistema en producción con una base de datos PostgreSQL:

1. **Crear base de datos y esquema**:
   Ejecuta el script SQL en tu servidor PostgreSQL para crear la estructura de tablas y políticas RLS:
   ```bash
   psql -U postgres -d tu_base_de_datos -f db/schema.sql
   ```
2. **Definir Variables de Entorno**:
   Configura la URL de conexión en tu sistema operativo o archivo `.env`:
   ```bash
   # Windows PowerShell
   $env:DATABASE_URL="postgresql://usuario:contraseña@localhost:5432/nombre_db"
   ```
3. **Ejecutar ETL**:
   Coloca tu archivo `.xlsx` de votantes y ejecuta la ingesta:
   ```bash
   python etl/etl_ingesta.py --file tu_archivo_votantes.xlsx --db postgresql://usuario:contraseña@localhost:5432/nombre_db
   ```
4. **Iniciar API del Servidor**:
   Inicia el servidor web Uvicorn:
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
   ```
5. **Calcular Ponderaciones**:
   Obtén las estadísticas y proyección ponderada en tiempo real:
   ```bash
   python analysis/weighting.py --db postgresql://usuario:contraseña@localhost:5432/nombre_db
   ```
