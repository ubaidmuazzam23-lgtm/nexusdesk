import os
import glob
import pandas as pd
import numpy as np

CSV_FOLDER = "app/ml/bilstm/data/csvs"
OUTPUT     = "app/ml/bilstm/data/tickets.csv"
LABEL_MAP  = {'simple', 'moderate', 'complex'}

files = glob.glob(f"{CSV_FOLDER}/*.csv")
print(f"Found {len(files)} CSV files:")
for f in files:
    print(f"  {f}")

dfs = []
for f in files:
    try:
        df = pd.read_csv(f, on_bad_lines='skip')
        df.columns = [c.strip().lower() for c in df.columns]
        if 'complexity' in df.columns:
            if 'problem_statement' in df.columns and 'text' not in df.columns:
                df = df.rename(columns={'problem_statement': 'text'})
            df = df[['text', 'complexity']].copy()
            dfs.append(df)
            print(f"  Loaded {len(df)} rows from {os.path.basename(f)}")
        else:
            print(f"  SKIPPED {os.path.basename(f)} — missing columns: {df.columns.tolist()}")
    except Exception as e:
        print(f"  ERROR {os.path.basename(f)}: {e}")

merged = pd.concat(dfs, ignore_index=True)
print(f"\nTotal before cleaning: {len(merged)}")

merged['complexity'] = merged['complexity'].str.strip().str.lower()
merged = merged[merged['complexity'].isin(LABEL_MAP)]
merged = merged.dropna(subset=['text', 'complexity'])
merged = merged[merged['text'].str.len() > 15]
merged = merged.drop_duplicates(subset=['text'])
print(f"After cleaning: {len(merged)}")

dist = merged['complexity'].value_counts()
print(f"\nClass distribution:")
for k, v in dist.items():
    print(f"  {k:10s}: {v:6d} ({v/len(merged)*100:.1f}%)")

min_count = dist.min()
balanced = pd.concat([
    merged[merged['complexity'] == cls].sample(min_count, random_state=42)
    for cls in ['simple', 'moderate', 'complex']
])

for seed in [42, 7, 13, 99, 55]:
    balanced = balanced.sample(frac=1, random_state=seed).reset_index(drop=True)

print(f"\nBalanced dataset: {len(balanced)} rows ({min_count} per class)")

consecutive_same = sum(
    balanced['complexity'].iloc[i] == balanced['complexity'].iloc[i+1]
    for i in range(len(balanced)-1)
)
print(f"Consecutive same-class rows: {consecutive_same} ({consecutive_same/len(balanced)*100:.1f}%) — ideal ~33%")

balanced.to_csv(OUTPUT, index=False)
print(f"\n✅ Saved to {OUTPUT}")
print("\nSample rows:")
print(balanced[['complexity','text']].head(9).to_string())
