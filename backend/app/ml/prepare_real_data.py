# File: backend/app/ml/prepare_real_data.py
# Converts real_tickets.csv → tickets.csv
# Filters English only, maps priority + type + tags → complexity label
# Run: python -m app.ml.prepare_real_data

import os, re
import pandas as pd
from collections import Counter

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "bilstm", "data")
INPUT    = os.path.join(DATA_DIR, "real_tickets.csv")
OUTPUT   = os.path.join(DATA_DIR, "tickets.csv")

COMPLEX_TAGS = {
    'outage','disruption','data breach','breach','emergency','ransomware',
    'attack','compromise','crash','critical','security','unauthorized',
    'intrusion','malware','bug','performance','corruption','failure',
}
SIMPLE_TAGS = {
    'documentation','feedback','inquiry','billing','payment','refund',
    'return','feature','product','sales','marketing','subscription',
    'invoice','notification','information',
}

def clean_text(text: str) -> str:
    if not isinstance(text, str): return ''
    text = text.replace('\\n', ' ').replace('\n', ' ')
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\b(dear|regards|sincerely|hello|hi|thank you|thanks|best regards|customer support team)\b', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:300]

def get_tags(row) -> set:
    tags = set()
    for i in range(1, 9):
        val = row.get(f'tag_{i}', '')
        if isinstance(val, str) and val.strip():
            tags.add(val.strip().lower())
    return tags

def assign_complexity(row) -> str:
    priority = str(row.get('priority', '')).strip().lower()
    typ      = str(row.get('type', '')).strip().lower()
    tags     = get_tags(row)
    body_len = len(str(row.get('body', '')))
    tag_count = len(tags)

    complex_hits = len(tags & COMPLEX_TAGS)
    simple_hits  = len(tags & SIMPLE_TAGS)

    # ── Complex ──────────────────────────────────────────────
    if priority == 'high' and typ == 'incident' and complex_hits >= 2:
        return 'complex'
    if priority == 'high' and typ == 'incident' and body_len > 500:
        return 'complex'
    if any(t in tags for t in ['emergency','data breach','ransomware','unauthorized','outage']) and priority == 'high':
        return 'complex'
    if typ == 'incident' and tag_count >= 4 and complex_hits >= 2:
        return 'complex'

    # ── Simple ───────────────────────────────────────────────
    if priority == 'low' and typ in ('request', 'change'):
        return 'simple'
    if priority == 'medium' and typ == 'request' and simple_hits >= 2 and not complex_hits:
        return 'simple'
    if priority == 'low':
        return 'simple'

    # ── Moderate ─────────────────────────────────────────────
    return 'moderate'

def main():
    print(f"\n📂 Loading {INPUT}")
    df = pd.read_csv(INPUT, on_bad_lines='skip')
    print(f"   Total: {len(df)} rows")

    # English only
    df = df[df['language'].str.lower() == 'en']
    print(f"   English: {len(df)} rows")

    # Build text
    df['subject'] = df['subject'].fillna('').apply(clean_text)
    df['body']    = df['body'].fillna('').apply(clean_text)
    df['text']    = (df['subject'] + '. ' + df['body']).str.strip('. ')
    df = df[df['text'].str.len() > 40]

    # Assign labels
    df['complexity'] = df.apply(assign_complexity, axis=1)
    out = df[['text', 'complexity']].dropna()

    dist = Counter(out['complexity'])
    print(f"\n   Raw distribution:")
    for k, v in sorted(dist.items()):
        print(f"   {k:10s}: {v:4d} ({v/len(out)*100:.1f}%)")

    # Balance
    min_count = min(dist.values())
    balanced  = pd.concat([
        out[out['complexity'] == cls].sample(min_count, random_state=42)
        for cls in ['simple', 'moderate', 'complex']
    ]).sample(frac=1, random_state=42).reset_index(drop=True)

    print(f"\n   Balanced: {len(balanced)} rows ({min_count} per class)")
    balanced.to_csv(OUTPUT, index=False)
    print(f"   Saved → {OUTPUT}")

    print("\n── Samples ──────────────────────────────────────────")
    for cls in ['simple', 'moderate', 'complex']:
        sample = balanced[balanced['complexity'] == cls]['text'].iloc[0]
        print(f"\n[{cls.upper()}]\n{sample[:200]}")

if __name__ == '__main__':
    main()