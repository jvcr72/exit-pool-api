import pandas as pd
from sqlalchemy import create_engine, text

def calculate_weighted_projection(db_url: str):
    """
    Computes the weighted exit poll results for Maneiro Municipality.
    
    The weighting formula is:
      Let N_c = official voter census of center c (from 'votantes' table)
      Let n_c = sample size in exit poll for center c (from 'resultados' table)
      Let v_c(i) = votes for candidate i in center c
      
      We compute the weight for each sampled center:
        W_c = N_c / Sum_{k in sampled_centers}(N_k)
        
      The projected percentage for candidate i is:
        P_i = Sum_{c in sampled_centers}( W_c * (v_c(i) / n_c) )
    """
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # 1. Get official census count per voting center (N_c)
        census_query = text("""
            SELECT centro_votacion, COUNT(*) as censo_total 
            FROM votantes 
            GROUP BY centro_votacion
        """)
        census_df = pd.read_sql(census_query, conn)
        
        # 2. Get exit poll sample count per voting center (n_c)
        sample_query = text("""
            SELECT centro_votacion, COUNT(*) as muestra_total 
            FROM resultados 
            GROUP BY centro_votacion
        """)
        sample_df = pd.read_sql(sample_query, conn)
        
        # 3. Get exit poll votes per candidate per center (v_c(i))
        votes_query = text("""
            SELECT centro_votacion, voto, COUNT(*) as votos_candidato 
            FROM resultados 
            GROUP BY centro_votacion, voto
        """)
        votes_df = pd.read_sql(votes_query, conn)
        
    if sample_df.empty or votes_df.empty:
        return {
            "status": "no_data",
            "message": "No exit poll results available to calculate projections.",
            "unweighted_results": {},
            "weighted_projection": {}
        }
        
    # Merge census and sample data to identify sampled centers
    centers_summary = pd.merge(census_df, sample_df, on="centro_votacion", how="inner")
    
    if centers_summary.empty:
        return {
            "status": "no_data",
            "message": "Sampled voting centers do not match the loaded census database.",
            "unweighted_results": {},
            "weighted_projection": {}
        }
        
    # N_sampled = sum of census for centers that have at least one sample
    total_sampled_census = centers_summary["censo_total"].sum()
    
    # Calculate Weight for each center: W_c = N_c / N_sampled
    centers_summary["peso_ponderacion"] = centers_summary["censo_total"] / total_sampled_census
    
    # Merge the weights back into the vote records
    votes_with_weights = pd.merge(votes_df, centers_summary, on="centro_votacion", how="inner")
    
    # Calculate proportion of candidate vote within each center: v_c(i) / n_c
    votes_with_weights["proporcion_centro"] = votes_with_weights["votos_candidato"] / votes_with_weights["muestra_total"]
    
    # Calculate weighted vote portion: W_c * (v_c(i) / n_c)
    votes_with_weights["porcion_ponderada"] = votes_with_weights["peso_ponderacion"] * votes_with_weights["proporcion_centro"]
    
    # Sum weighted portions per candidate to get final projection P_i
    weighted_projection = votes_with_weights.groupby("voto")["porcion_ponderada"].sum().to_dict()
    
    # Calculate unweighted results for comparison
    total_votes = votes_df["votos_candidato"].sum()
    unweighted_results = votes_df.groupby("voto")["votos_candidato"].sum().to_dict()
    unweighted_pct = {k: v / total_votes for k, v in unweighted_results.items()}
    
    # Build detailed center-by-center report
    center_details = []
    for _, row in centers_summary.iterrows():
        center_details.append({
            "centro_votacion": row["centro_votacion"],
            "census": int(row["censo_total"]),
            "sample_size": int(row["muestra_total"]),
            "weight_factor": float(row["peso_ponderacion"])
        })
        
    return {
        "status": "success",
        "total_census": int(census_df["censo_total"].sum()),
        "sampled_census": int(total_sampled_census),
        "total_sample_size": int(total_votes),
        "center_details": center_details,
        "unweighted_results": {
            "counts": unweighted_results,
            "percentages": {k: round(v * 100, 2) for k, v in unweighted_pct.items()}
        },
        "weighted_projection": {
            "percentages": {k: round(v * 100, 2) for k, v in weighted_projection.items()}
        }
    }

if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Calculate Weighted Projections for Maneiro Exit Poll")
    parser.add_argument("--db", default="postgresql://postgres:postgres@localhost:5432/exitpoll", help="SQLAlchemy database URL")
    args = parser.parse_args()
    
    try:
        results = calculate_weighted_projection(args.db)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error calculating weighting: {e}")
