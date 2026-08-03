import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
pinecone_iea = BASE_DIR / "backend" / "scripts" / "pinecone" / "data" / "IEA_Sections.csv"

df = pd.read_csv(pinecone_iea, dtype=str).fillna("")
print("Pinecone IEA_Sections.csv total rows:", len(df))
print("Columns:", df.columns.tolist())

match_45a = df[df["Section"].str.strip() == "45A"]
print("\nFound 45A in IEA_Sections.csv:")
if not match_45a.empty:
    for idx, r in match_45a.iterrows():
        print(f"Section: {r['Section']} | Title: {r.get('Section _name') or r.get('Title') or r.get('Section_name')}")
        print("Description:", r.get("Description", "")[:200])
else:
    print("Not found in IEA_Sections.csv")
