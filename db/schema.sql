-- Schema for Municipal Exit Poll System (Maneiro, Nueva Esparta)

-- 1. Table: encuestadores (Pollsters)
CREATE TABLE IF NOT EXISTS encuestadores (
    id VARCHAR(50) PRIMARY KEY,
    token_aud VARCHAR(255) NOT NULL UNIQUE,
    estado_conexion VARCHAR(50) DEFAULT 'desconectado',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Table: votantes (Voters - Census)
CREATE TABLE IF NOT EXISTS votantes (
    cedula VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellidos VARCHAR(100) NOT NULL,
    telefono VARCHAR(50),
    direccion_residencia TEXT,
    centro_votacion VARCHAR(255) NOT NULL,
    mesa_vota INTEGER NOT NULL,
    correo_electronico VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexing for voter search and calculations
CREATE INDEX IF NOT EXISTS idx_votantes_centro ON votantes(centro_votacion);

-- 3. Table: resultados (Exit Poll Results)
CREATE TABLE IF NOT EXISTS resultados (
    id_registrosnvoto VARCHAR(50) PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    latitud NUMERIC(10, 8) NOT NULL,
    longitud NUMERIC(11, 8) NOT NULL,
    voto VARCHAR(100) NOT NULL,
    hash_validacion VARCHAR(64) NOT NULL,
    id_encuestador VARCHAR(50) NOT NULL REFERENCES encuestadores(id) ON DELETE RESTRICT,
    centro_votacion VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- Row-Level Security (RLS) Setup
-- Enable RLS on the results table
ALTER TABLE resultados ENABLE ROW LEVEL SECURITY;

-- Force RLS even for the table owner/superuser when connecting through standard application pool
ALTER TABLE resultados FORCE ROW LEVEL SECURITY;

-- Create policy to restrict access based on session variable 'app.current_pollster_id'
-- Note: 'current_setting' retrieves the value of app.current_pollster_id. 
-- The second parameter 'true' prevents throwing an exception if the parameter is not set (returns NULL instead).
DROP POLICY IF EXISTS pollster_isolation_policy ON resultados;
CREATE POLICY pollster_isolation_policy ON resultados
    FOR ALL
    TO public
    USING (id_encuestador = current_setting('app.current_pollster_id', true))
    WITH CHECK (id_encuestador = current_setting('app.current_pollster_id', true));
