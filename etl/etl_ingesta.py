import os
import re
import logging
import pandas as pd
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.exc import SQLAlchemyError

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler("etl_ingesta.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ETL_Ingesta")

# Error log for failed records
error_logger = logging.getLogger("ETL_Failed_Records")
error_file_handler = logging.FileHandler("etl_errors.log", encoding="utf-8")
error_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
error_logger.addHandler(error_file_handler)
error_logger.setLevel(logging.ERROR)

def normalize_cedula(cedula_raw):
    """
    Normalizes Venezuelan Cedula:
    - Removes spaces, dots, commas, dashes.
    - Standardizes format to V[digits] or E[digits].
    - Defaults to 'V' if no prefix is specified.
    """
    if pd.isna(cedula_raw):
        return None
    
    # Convert to string and clean
    ced_str = str(cedula_raw).strip().upper()
    
    # Check if foreign (Extranjero)
    is_extranjero = 'E' in ced_str
    
    # Extract only digits
    digits = "".join(re.findall(r'\d+', ced_str))
    
    if not digits:
        return None
    
    # Remove leading zeros to normalize (e.g. V-012345 -> V12345)
    digits = str(int(digits))
    
    prefix = 'E' if is_extranjero else 'V'
    return f"{prefix}{digits}"

def normalize_email(email_raw):
    """Cleans and validates basic email format."""
    if pd.isna(email_raw):
        return None
    email_str = str(email_raw).strip().lower()
    # Simple regex check for basic structure
    if re.match(r'[^@]+@[^@]+\.[^@]+', email_str):
        return email_str
    return None

def normalize_phone(phone_raw):
    """Cleans phone numbers to contain only numbers and optional leading +."""
    if pd.isna(phone_raw):
        return None
    phone_str = str(phone_raw).strip()
    has_plus = phone_str.startswith('+')
    digits = "".join(re.findall(r'\d+', phone_str))
    if not digits:
        return None
    return f"+{digits}" if has_plus else digits

def clean_and_normalize_data(df):
    """
    Cleans and normalizes the dataframe of voters.
    """
    logger.info(f"Starting cleaning on {len(df)} raw records.")
    
    # Copy to avoid modifying original dataframe
    clean_df = df.copy()
    
    # Rename columns to standard lowercase representation and map common synonyms
    mapping = {
        'nombre': 'nombre',
        'apellidos': 'apellidos',
        'telefono': 'telefono',
        'telefono_movil': 'telefono',
        'celular': 'telefono',
        'direccion_de_residencia': 'direccion_residencia',
        'direccion_residencia': 'direccion_residencia',
        'direccion': 'direccion_residencia',
        'residencia': 'direccion_residencia',
        'cedula': 'cedula',
        'cédula': 'cedula',
        'centro_de_votacion': 'centro_votacion',
        'centro_votacion': 'centro_votacion',
        'centro': 'centro_votacion',
        'mesa_donde_vota': 'mesa_vota',
        'mesa_vota': 'mesa_vota',
        'mesa': 'mesa_vota',
        'correo_electronico': 'correo_electronico',
        'correo': 'correo_electronico',
        'email': 'correo_electronico'
    }
    
    new_cols = []
    for col in clean_df.columns:
        c = str(col).strip().lower()
        c = c.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
        c = re.sub(r'[\s\-\.]+', '_', c)
        new_cols.append(mapping.get(c, c))
        
    clean_df.columns = new_cols
    
    # Required columns checklist
    required_cols = ['nombre', 'apellidos', 'cedula', 'centro_votacion', 'mesa_vota']
    for col in required_cols:
        if col not in clean_df.columns:
            raise ValueError(f"Missing mandatory column in Excel sheet: '{col}'. Present columns: {list(clean_df.columns)}")

            
    # Apply normalizations
    clean_df['cedula'] = clean_df['cedula'].apply(normalize_cedula)
    clean_df['correo_electronico'] = clean_df['correo_electronico'].apply(normalize_email)
    clean_df['telefono'] = clean_df['telefono'].apply(normalize_phone)
    
    # Clean text columns
    for str_col in ['nombre', 'apellidos', 'direccion_residencia', 'centro_votacion']:
        if str_col in clean_df.columns:
            clean_df[str_col] = clean_df[str_col].apply(lambda x: str(x).strip() if pd.notna(x) else None)
            
    # Handle mesa_vota: ensure integer or valid number
    def clean_mesa(mesa_val):
        try:
            if pd.isna(mesa_val):
                return None
            return int(float(mesa_val))
        except (ValueError, TypeError):
            return None
    clean_df['mesa_vota'] = clean_df['mesa_vota'].apply(clean_mesa)
    
    # Filter out rows with invalid critical data (missing cedula, nombre, apellidos, centro_votacion, mesa_vota)
    invalid_rows = clean_df[
        clean_df['cedula'].isna() | 
        clean_df['nombre'].isna() | 
        clean_df['apellidos'].isna() | 
        clean_df['centro_votacion'].isna() | 
        clean_df['mesa_vota'].isna()
    ]
    
    if len(invalid_rows) > 0:
        logger.warning(f"Found {len(invalid_rows)} rows with invalid/missing critical fields. Logging to error file.")
        for idx, row in invalid_rows.iterrows():
            error_logger.error(f"Row {idx+2} skipped: Missing critical data. Raw values: {dict(df.loc[idx])}")
            
    # Drop rows with invalid critical data
    clean_df = clean_df.dropna(subset=['cedula', 'nombre', 'apellidos', 'centro_votacion', 'mesa_vota'])
    
    # Deduplicate based on cedula
    total_before_dedup = len(clean_df)
    duplicates = clean_df[clean_df.duplicated(subset=['cedula'], keep='first')]
    
    if len(duplicates) > 0:
        logger.warning(f"Found {len(duplicates)} duplicate Cedulas. Keeping first occurrence.")
        for idx, row in duplicates.iterrows():
            error_logger.error(f"Row {idx+2} skipped: Duplicate Cedula '{row['cedula']}'. Raw values: {dict(df.loc[idx])}")
            
    clean_df = clean_df.drop_duplicates(subset=['cedula'], keep='first')
    logger.info(f"Normalized and cleaned data. Valid records to ingest: {len(clean_df)} (Dropped {len(df) - len(clean_df)} rows).")
    
    return clean_df

def ingest_to_database(db_url, clean_df):
    """
    Ingests cleaned dataframe into PostgreSQL database using a transactional connection.
    Attempts batch insert first; falls back to row-by-row transactional insert on failure
    to isolate and log specific invalid rows.
    """
    engine = create_engine(db_url)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    
    # Get table object
    if 'votantes' not in metadata.tables:
        raise ValueError("The 'votantes' table does not exist in the database. Run schema.sql first.")
    
    votantes_table = Table('votantes', metadata, autoload_with=engine)
    
    # Prepare records for insertion
    records = clean_df.to_dict(orient='records')
    
    # Columns matching DB schema
    db_cols = ['cedula', 'nombre', 'apellidos', 'telefono', 'direccion_residencia', 'centro_votacion', 'mesa_vota', 'correo_electronico']
    
    insert_records = []
    for r in records:
        filtered_record = {col: r.get(col) for col in db_cols if col in r}
        insert_records.append(filtered_record)
        
    logger.info("Initiating database insertion transaction...")
    
    success_count = 0
    fail_count = 0
    
    # Connection context manager
    with engine.begin() as connection:
        # We perform a transactional savepoint operation or row-by-row fallback.
        # To avoid rolling back the entire migration if a duplicate key constraint fails in production,
        # we can use INSERT ... ON CONFLICT DO UPDATE or handle failures row-by-row.
        # Since requirements state "insercion transaccional con manejo de errores (log de registros fallidos)",
        # inserting row-by-row under a transaction (or nested transactions/savepoints) lets us log failures.
        # In SQL Alchemy, we can use SAVEPOINTs to roll back single failures.
        
        for record in insert_records:
            trans = connection.begin_nested() # Create savepoint
            try:
                connection.execute(votantes_table.insert().values(record))
                trans.commit()
                success_count += 1
            except SQLAlchemyError as e:
                trans.rollback()
                fail_count += 1
                error_msg = str(e.orig).replace('\n', ' ') if hasattr(e, 'orig') else str(e)
                error_logger.error(f"DB Insertion Failed for Cedula '{record['cedula']}': {error_msg}")
                logger.debug(f"Record failed: {record}")
                
    logger.info(f"Ingestion complete: {success_count} inserted successfully. {fail_count} failed in DB.")
    return success_count, fail_count

def run_etl(excel_path, db_url):
    """Runs the complete ETL pipeline."""
    logger.info(f"Starting ETL pipeline for file: {excel_path}")
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
        
    try:
        # Load excel file
        logger.info("Reading Excel file...")
        df = pd.read_excel(excel_path)
        
        # Clean and normalize
        clean_df = clean_and_normalize_data(df)
        
        # Ingest to database
        success, fails = ingest_to_database(db_url, clean_df)
        
        logger.info(f"ETL Execution Finished. Success: {success}, Failures: {fails}.")
        print(f"\nETL Ingestion Summary:\n- Successfully Ingested: {success} voters\n- Failed/Skipped: {fails} records (See etl_errors.log for details)\n")
        return success, fails
        
    except Exception as e:
        logger.exception("Fatal error during ETL execution:")
        raise e

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ETL Voter Ingestion Pipeline for Maneiro Exit Poll")
    parser.add_argument("--file", default="mock_votantes.xlsx", help="Path to voter Excel (.xlsx) file")
    parser.add_argument("--db", default="postgresql://postgres:postgres@localhost:5432/exitpoll", help="SQLAlchemy database URL")
    
    args = parser.parse_args()
    
    # Run the ETL script
    try:
        run_etl(args.file, args.db)
    except Exception as err:
        print(f"ETL execution failed: {err}")
