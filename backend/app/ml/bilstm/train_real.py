# File: backend/app/ml/bilstm/train_real.py
# BiLSTM with Attention — Real IT Ticket Complexity Classifier
# Architecture: Embedding → SpatialDropout → BiLSTM × 2 → Attention → Dense → Output
# Run: python -m app.ml.bilstm.train_real

import os, json, pickle, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import (
    Input, Embedding, Bidirectional, LSTM, Dense, Dropout,
    BatchNormalization, SpatialDropout1D, GlobalAveragePooling1D,
    GlobalMaxPooling1D, Concatenate, Layer, Multiply, Softmax
)
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.callbacks import (
    EarlyStopping, ModelCheckpoint, ReduceLROnPlateau, CSVLogger
)
from tensorflow.keras.regularizers import l2
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight
import seaborn as sns

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(__file__)
DATA_DIR       = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATA_PATH      = os.path.join(DATA_DIR, "tickets.csv")
MODEL_PATH     = os.path.join(DATA_DIR, "bilstm_model.h5")
TOKENIZER_PATH = os.path.join(DATA_DIR, "tokenizer.pkl")
HISTORY_PATH   = os.path.join(DATA_DIR, "training_history.json")
PLOT_PATH      = os.path.join(DATA_DIR, "training_curves.png")
CM_PATH        = os.path.join(DATA_DIR, "confusion_matrix.png")
REPORT_PATH    = os.path.join(DATA_DIR, "classification_report.txt")
LOG_PATH       = os.path.join(DATA_DIR, "training_log.csv")

MAX_LEN    = 100
VOCAB_SIZE = 10000
EMBED_DIM  = 128
LSTM_UNITS = 128
DENSE_UNITS = 64
DROPOUT    = 0.3
BATCH_SIZE = 32
EPOCHS     = 60
LABEL_MAP  = {'simple': 0, 'moderate': 1, 'complex': 2}
LABEL_NAMES = ['Simple', 'Moderate', 'Complex']

print("\n" + "="*60)
print("  BiLSTM + Attention — Real Data Training")
print("="*60)

# ── Load data ────────────────────────────────────────────────────────────────
df = pd.read_csv(DATA_PATH).dropna(subset=['text', 'complexity'])
df['complexity'] = df['complexity'].str.strip().str.lower()
df = df[df['complexity'].isin(LABEL_MAP)]
print(f"\n📂 Loaded: {len(df)} samples")
print(df['complexity'].value_counts())

# ── Tokenize ─────────────────────────────────────────────────────────────────
tok = Tokenizer(num_words=VOCAB_SIZE, oov_token='<OOV>', lower=True,
                filters='!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~\t\n')
tok.fit_on_texts(df['text'].tolist())
actual_vocab = min(len(tok.word_index) + 1, VOCAB_SIZE)
print(f"\n🔤 Vocabulary: {len(tok.word_index)} words → using top {actual_vocab}")

with open(TOKENIZER_PATH, 'wb') as f:
    pickle.dump(tok, f)

X     = pad_sequences(tok.texts_to_sequences(df['text'].tolist()),
                      maxlen=MAX_LEN, padding='post', truncating='post')
y_raw = [LABEL_MAP[c] for c in df['complexity']]
y     = tf.keras.utils.to_categorical(y_raw, num_classes=3)

X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"\n📊 Train: {len(X_train)} | Val: {len(X_val)}")

cw = compute_class_weight('balanced', classes=np.array([0,1,2]), y=np.array(y_raw))
class_weights = {i: float(cw[i]) for i in range(3)}
print(f"⚖️  Class weights: { {LABEL_NAMES[k]: round(v,3) for k,v in class_weights.items()} }")

# ── Attention Layer ───────────────────────────────────────────────────────────
class BahdanauAttention(Layer):
    """Additive attention mechanism (Bahdanau et al., 2015)"""
    def __init__(self, units=128, **kwargs):
        super().__init__(**kwargs)
        self.units = units
        self.W = Dense(units, use_bias=False)
        self.V = Dense(1, use_bias=False)

    def call(self, hidden_states):
        # hidden_states: (batch, timesteps, features)
        score = self.V(tf.nn.tanh(self.W(hidden_states)))  # (batch, timesteps, 1)
        weights = tf.nn.softmax(score, axis=1)              # attention weights
        context = weights * hidden_states                   # weighted sum
        context = tf.reduce_sum(context, axis=1)            # (batch, features)
        return context, weights

    def get_config(self):
        config = super().get_config()
        config.update({'units': self.units})
        return config
    @classmethod
    def from_config(cls, config):
        return cls(**config)

# ── Model Architecture ────────────────────────────────────────────────────────
inp = Input(shape=(MAX_LEN,), name='token_input')

# Embedding with spatial dropout (drops entire feature maps)
x = Embedding(actual_vocab, EMBED_DIM, name='embedding',
              embeddings_regularizer=l2(1e-5))(inp)
x = SpatialDropout1D(0.2, name='spatial_dropout')(x)

# BiLSTM Layer 1 — return sequences for attention
x = Bidirectional(
    LSTM(LSTM_UNITS, return_sequences=True, dropout=0.2,
         recurrent_dropout=0.0, kernel_regularizer=l2(1e-5)),
    name='bilstm_1'
)(x)
x = BatchNormalization(name='bn_1')(x)

# BiLSTM Layer 2 — return sequences for attention
x = Bidirectional(
    LSTM(LSTM_UNITS // 2, return_sequences=True, dropout=0.2,
         recurrent_dropout=0.0, kernel_regularizer=l2(1e-5)),
    name='bilstm_2'
)(x)
x = BatchNormalization(name='bn_2')(x)

# Attention mechanism
attn_out, attn_weights = BahdanauAttention(LSTM_UNITS, name='attention')(x)

# Also use global max pool for richer representation
global_max  = GlobalMaxPooling1D(name='global_max')(x)
global_avg  = GlobalAveragePooling1D(name='global_avg')(x)

# Concatenate attention + pooled representations
combined = Concatenate(name='concat')([attn_out, global_max, global_avg])

# Fully connected head
x = Dense(DENSE_UNITS * 2, activation='relu',
          kernel_regularizer=l2(1e-4), name='fc_1')(combined)
x = BatchNormalization(name='bn_3')(x)
x = Dropout(DROPOUT, name='dropout_1')(x)

x = Dense(DENSE_UNITS, activation='relu',
          kernel_regularizer=l2(1e-4), name='fc_2')(x)
x = Dropout(DROPOUT * 0.5, name='dropout_2')(x)

out = Dense(3, activation='softmax', name='output')(x)

model = Model(inputs=inp, outputs=out, name='BiLSTM_Attention')
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=0.001, clipnorm=1.0),
    loss='categorical_crossentropy',
    metrics=['accuracy']
)
model.summary()

total_params = model.count_params()
print(f"\n  Total parameters: {total_params:,}")

# ── Callbacks ────────────────────────────────────────────────────────────────
callbacks = [
    EarlyStopping(
        monitor='val_accuracy', patience=12,
        restore_best_weights=True, min_delta=0.002, verbose=1
    ),
    ModelCheckpoint(
        MODEL_PATH, monitor='val_accuracy',
        save_best_only=True, verbose=1
    ),
    ReduceLROnPlateau(
        monitor='val_loss', factor=0.5,
        patience=5, min_lr=1e-6, verbose=1
    ),
    CSVLogger(LOG_PATH),
]

# ── Train ─────────────────────────────────────────────────────────────────────
print("\n🚀 Training...")
history = model.fit(
    X_train, y_train,
    validation_data=(X_val, y_val),
    epochs=EPOCHS,
    batch_size=BATCH_SIZE,
    callbacks=callbacks,
    class_weight=class_weights,
    verbose=1
)

# ── Evaluate ──────────────────────────────────────────────────────────────────
print("\n📈 Evaluation:")
val_loss, val_acc = model.evaluate(X_val, y_val, verbose=0)
print(f"   Val Loss:     {val_loss:.4f}")
print(f"   Val Accuracy: {val_acc:.4f} ({val_acc*100:.1f}%)")

preds = np.argmax(model.predict(X_val, verbose=0), axis=1)
true  = np.argmax(y_val, axis=1)
report = classification_report(true, preds, target_names=LABEL_NAMES, digits=4)
print("\n" + report)

with open(REPORT_PATH, 'w') as f:
    f.write(f"BiLSTM + Attention\nVal Accuracy: {val_acc*100:.2f}%\n\n{report}")

# ── Save history ──────────────────────────────────────────────────────────────
with open(HISTORY_PATH, 'w') as f:
    json.dump({k: [float(v) for v in vals] for k, vals in history.history.items()}, f)

# ── Plots ─────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('BiLSTM + Attention — Training Curves', fontsize=14, fontweight='bold')

axes[0].plot(history.history['accuracy'],     label='Train Acc', color='#174D38', linewidth=2)
axes[0].plot(history.history['val_accuracy'], label='Val Acc',   color='#4d9e78', linewidth=2, linestyle='--')
axes[0].set_title('Accuracy'); axes[0].legend(); axes[0].set_xlabel('Epoch'); axes[0].grid(alpha=0.3)

axes[1].plot(history.history['loss'],     label='Train Loss', color='#4D1717', linewidth=2)
axes[1].plot(history.history['val_loss'], label='Val Loss',   color='#a04040', linewidth=2, linestyle='--')
axes[1].set_title('Loss'); axes[1].legend(); axes[1].set_xlabel('Epoch'); axes[1].grid(alpha=0.3)

plt.tight_layout(); plt.savefig(PLOT_PATH, dpi=150); plt.close()

# Confusion matrix
cm = confusion_matrix(true, preds)
plt.figure(figsize=(8, 6))
sns.heatmap(cm, annot=True, fmt='d', cmap='Greens',
            xticklabels=LABEL_NAMES, yticklabels=LABEL_NAMES,
            linewidths=0.5, cbar_kws={'label': 'Count'})
plt.title('BiLSTM + Attention — Confusion Matrix', fontweight='bold')
plt.ylabel('True Label'); plt.xlabel('Predicted Label')
plt.tight_layout(); plt.savefig(CM_PATH, dpi=150); plt.close()

print(f"\n💾 Saved:")
print(f"   Model     : {MODEL_PATH}")
print(f"   Tokenizer : {TOKENIZER_PATH}")
print(f"   Plots     : {PLOT_PATH}")
print(f"   CM        : {CM_PATH}")
print(f"\n{'='*60}")
print(f"  ✅ BiLSTM + Attention complete! Accuracy: {val_acc*100:.1f}%")
print(f"{'='*60}\n")