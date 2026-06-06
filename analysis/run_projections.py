import os
import sys

# Ensure tabulate is installed or use fallback formatting
try:
    from tabulate import tabulate
except ImportError:
    # Simple text formatting if tabulate is not installed
    def tabulate(rows, headers, tablefmt=""):
        col_widths = [max(len(str(x)) for x in col) for col in zip(*(rows + [headers]))]
        fmt = " | ".join(f"{{:<{w}}}" for w in col_widths)
        lines = [fmt.format(*headers)]
        lines.append("-" * (sum(col_widths) + 3 * (len(col_widths) - 1)))
        for r in rows:
            lines.append(fmt.format(*r))
        return "\n".join(lines)

# Add root folder to sys.path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.weighting import calculate_weighted_projection


def read_db_url():
    possible_paths = [
        "db/db_url.txt",
        "db_url.txt",
        "../db/db_url.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    return os.getenv("DATABASE_URL")

def render_dashboard():
    db_url = read_db_url()
    if not db_url:
        print("[ERROR] Database URL file not found.")
        sys.exit(1)
        
    results = calculate_weighted_projection(db_url)
    
    if results.get("status") == "no_data":
        print("\n" + "="*60)
        print(" DASHBOARD ELECTORAL - MUNICIPIO MANEIRO ")
        print("="*60)
        print(f"Estado del Sistema: {results['message']}")
        print("="*60 + "\n")
        return
        
    print("\n" + "="*70)
    print(" === DASHBOARD ELECTORAL DE EXIT POLL - MUNICIPIO MANEIRO, NUEVA ESPARTA ===")
    print("="*70)
    print(f" Censo Total del Municipio: {results['total_census']} electores")
    print(f" Censo en Centros Muestreados: {results['sampled_census']} electores")
    print(f" Muestra Total Recolectada (Exit Poll): {results['total_sample_size']} votos")
    print("="*70)
    
    # 1. Centers Table
    print("\n [CENTROS] DETALLE DE MUESTRA Y FACTORES DE PONDERACION POR CENTRO:")
    headers_centers = ["Centro de Votacion", "Censo Oficial", "Muestra (n)", "Peso Ponderado (W_c)"]
    rows_centers = []
    for c in results["center_details"]:
        rows_centers.append([
            c["centro_votacion"],
            f"{c['census']} electores",
            f"{c['sample_size']} votos",
            f"{round(c['weight_factor'] * 100, 2)}%"
        ])
    print(tabulate(rows_centers, headers=headers_centers, tablefmt="grid"))
    
    # 2. Candidate Projection Table
    print("\n [PROYECCION] PROYECCION FINAL DE RESULTADOS ELECTORALES:")
    headers_proj = ["Candidato/Opcion", "Votos Brutos", "Porcentaje Bruto (Sin Ponderar)", "Proyeccion Ponderada (Sin Sesgo)"]
    rows_proj = []
    
    unweighted_counts = results["unweighted_results"]["counts"]
    unweighted_pcts = results["unweighted_results"]["percentages"]
    weighted_pcts = results["weighted_projection"]["percentages"]
    
    for candidate in weighted_pcts.keys():
        votos_brutos = unweighted_counts.get(candidate, 0)
        pct_bruto = unweighted_pcts.get(candidate, 0.0)
        pct_ponderado = weighted_pcts.get(candidate, 0.0)
        
        # Highlight winner in projection
        candidate_label = f"[*] {candidate}" if pct_ponderado == max(weighted_pcts.values()) else f"    {candidate}"
        
        rows_proj.append([
            candidate_label,
            f"{votos_brutos} votos",
            f"{pct_bruto}%",
            f"{pct_ponderado}%"
        ])
        
    print(tabulate(rows_proj, headers=headers_proj, tablefmt="fancy_grid"))

    print("\n[NOTA] La proyección ponderada corrige desviaciones si se recolectaron más muestras")
    print("       en centros pequeños que en centros grandes. Es el resultado estadístico más confiable.")
    print("="*70 + "\n")

if __name__ == "__main__":
    render_dashboard()

