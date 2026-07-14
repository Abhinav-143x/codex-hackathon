import os
import json
from pathlib import Path

def aggregate_runs():
    base_dir = Path(__file__).parent
    runs_dir = base_dir / "runs"
    out_file = base_dir / "vite_ui" / "src" / "data.json"
    
    if not runs_dir.exists():
        print("Runs directory not found!")
        return

    all_runs = []
    for f in runs_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                all_runs.append(data)
        except Exception as e:
            print(f"Error reading {f}: {e}")

    # Sort by sample name
    all_runs.sort(key=lambda x: x.get("sample_name", ""))
    
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as file:
        json.dump(all_runs, file, indent=2)
        
    print(f"Aggregated {len(all_runs)} runs into {out_file}")

if __name__ == "__main__":
    aggregate_runs()
