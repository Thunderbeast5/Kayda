import pandas as pd

df = pd.read_parquet(r"C:\Users\Ajinkya\Desktop\MootCourt\data\metadata_2024\metadata.parquet")

print(df.columns.tolist())
print(df.iloc[0].to_dict())

print("\nColumns:")
for c in df.columns:
    print(c)

print("\nFirst record:\n")
print(df.iloc[0].to_dict())