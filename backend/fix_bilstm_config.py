# File: backend/fix_bilstm_config.py
# Run once: python fix_bilstm_config.py
# Patches BiLSTM model.py to use better config for small dataset

import re, os

MODEL_PATH = "app/ml/bilstm/model.py"

with open(MODEL_PATH, 'r') as f:
    content = f.read()

# Fix MAX_LEN — tickets are ~20 words, 128 is overkill
content = re.sub(r'MAX_LEN\s*=\s*\d+', 'MAX_LEN       = 50', content)

# Fix VOCAB_SIZE to match actual vocab
content = re.sub(r'VOCAB_SIZE\s*=\s*\d+', 'VOCAB_SIZE     = 3000', content)

# Fix batch size — smaller batch for small dataset
content = re.sub(r'BATCH_SIZE\s*=\s*\d+', 'BATCH_SIZE     = 16', content)

# Fix learning rate
content = re.sub(r'LEARNING_RATE\s*=\s*[\d.e-]+', 'LEARNING_RATE  = 0.0005', content)

with open(MODEL_PATH, 'w') as f:
    f.write(content)

# Fix train.py patience
TRAIN_PATH = "app/ml/bilstm/train.py"
with open(TRAIN_PATH, 'r') as f:
    train = f.read()

# EarlyStopping patience 5 → 12
train = train.replace("patience=5,", "patience=12,")
train = train.replace("patience=3,", "patience=5,")

# Add min_delta
train = train.replace(
    "patience=12,",
    "patience=12, min_delta=0.003, monitor='val_accuracy',"
)

with open(TRAIN_PATH, 'w') as f:
    f.write(train)

print("✅ BiLSTM config patched")
print("Now run: python -m app.ml.bilstm.train")