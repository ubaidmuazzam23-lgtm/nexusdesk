# File: backend/app/ml/gru/train_real.py
# GRU with Attention — Real IT Ticket Complexity Classifier
# Architecture: Embedding → SpatialDropout → GRU × 2 → Attention → Dense → Output
# Run: python -m app.ml.gru.train_real

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
    Input, Embedding, GRU, Dense, Dropout, BatchNormalization,
    SpatialDropout1D, GlobalMaxPooling1D, GlobalAveragePooling1D,
    Concatenate, Layer
)
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.callbacks import (
    EarlyStopping, ModelCheckpoint, ReduceLROnPlateau, CSVLogger
)
from tensorflow.keras.regularizers import l2
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight
import seaborn as sns

BASE_DIR       = os.path.dirname(__file__)
BILSTM_DIR     = os.path.join(os.path.dirname(BASE_DIR), "bilstm", "data")
DATA_PATH      = os.path.join(BILSTM_DIR, "tickets.csv")
TOKENIZER_PATH = os.path.join(BILSTM_DIR, "tokenizer.pkl")
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
MODEL_PATH   = os.path.join(BASE_DIR, "data", "gru_model.h5")
HISTORY_PATH = os.path.join(BASE_DIR, "data", "training_history.json")
PLOT_PATH    = os.path.join(BASE_DIR, "data", "training_curves.png")
CM_PATH      = os.path.join(BASE_DIR, "data", "confusion_matrix.png")
REPORT_PATH  = os.path.join(BASE_DIR, "data", "classification_report.txt")
LOG_PATH     = os.path.join(BASE_DIR, "data", "training_log.csv")

MAX_LEN    = 100
EMBED_DIM  = 128
GRU_UNITS  = 128
DROPOUT    = 0.3
BATCH_SIZE = 32
EPOCHS     = 60
LABEL_MAP  = {'simple': 0, 'moderate': 1, 'complex': 2}
LABEL_NAMES = ['Simple', 'Moderate', 'Complex']

print("\n" + "="*60)
print("  GRU + Attention — Real Data Training")
print("="*60)

df = pd.read_csv(DATA_PATH).dropna(subset=['text','complexity'])
df['complexity'] = df['complexity'].str.strip().str.lower()
df = df[df['complexity'].isin(LABEL_MAP)]
print(f"\n📂 Loaded: {len(df)} samples")

with open(TOKENIZER_PATH, 'rb') as f:
    tok = pickle.load(f)

VOCAB_SIZE = len(tok.word_index) + 1

X     = pad_sequences(tok.texts_to_sequences(df['text'].tolist()),
                      maxlen=MAX_LEN, padding='post', truncating='post')
y_raw = [LABEL_MAP[c] for c in df['complexity']]
y     = tf.keras.utils.to_categorical(y_raw, num_classes=3)
X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

cw = compute_class_weight('balanced', classes=np.array([0,1,2]), y=np.array(y_raw))
class_weights = {i: float(cw[i]) for i in range(3)}

class BahdanauAttention(Layer):
    def __init__(self, units=128, **kwargs):
        super().__init__(**kwargs)
        self.units = units
        self.W = Dense(units, use_bias=False)
        self.V = Dense(1, use_bias=False)
    def call(self, hidden_states):
        score   = self.V(tf.nn.tanh(self.W(hidden_states)))
        weights = tf.nn.softmax(score, axis=1)
        return tf.reduce_sum(weights * hidden_states, axis=1)
    def get_config(self):
        config = super().get_config()
        config.update({'units': self.units})
        return config
    @classmethod
    def from_config(cls, config):
        return cls(**config)

inp = Input(shape=(MAX_LEN,))
x   = Embedding(VOCAB_SIZE, EMBED_DIM, embeddings_regularizer=l2(1e-5))(inp)
x   = SpatialDropout1D(0.2)(x)
x   = GRU(GRU_UNITS, return_sequences=True, dropout=0.2,
          kernel_regularizer=l2(1e-5))(x)
x   = BatchNormalization()(x)
x   = GRU(GRU_UNITS // 2, return_sequences=True, dropout=0.2,
          kernel_regularizer=l2(1e-5))(x)
x   = BatchNormalization()(x)

attn     = BahdanauAttention(GRU_UNITS // 2)(x)
gmax     = GlobalMaxPooling1D()(x)
gavg     = GlobalAveragePooling1D()(x)
combined = Concatenate()([attn, gmax, gavg])

x   = Dense(128, activation='relu', kernel_regularizer=l2(1e-4))(combined)
x   = BatchNormalization()(x)
x   = Dropout(DROPOUT)(x)
x   = Dense(64, activation='relu', kernel_regularizer=l2(1e-4))(x)
x   = Dropout(DROPOUT * 0.5)(x)
out = Dense(3, activation='softmax')(x)

model = Model(inputs=inp, outputs=out, name='GRU_Attention')
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=0.001, clipnorm=1.0),
    loss='categorical_crossentropy', metrics=['accuracy']
)
model.summary()
print(f"  Parameters: {model.count_params():,}")

callbacks = [
    EarlyStopping(monitor='val_accuracy', patience=12, restore_best_weights=True, min_delta=0.002),
    ModelCheckpoint(MODEL_PATH, monitor='val_accuracy', save_best_only=True, verbose=1),
    ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5, min_lr=1e-6, verbose=1),
    CSVLogger(LOG_PATH),
]

print("\n🚀 Training...")
history = model.fit(X_train, y_train, validation_data=(X_val, y_val),
                    epochs=EPOCHS, batch_size=BATCH_SIZE,
                    callbacks=callbacks, class_weight=class_weights, verbose=1)

val_loss, val_acc = model.evaluate(X_val, y_val, verbose=0)
preds = np.argmax(model.predict(X_val, verbose=0), axis=1)
true  = np.argmax(y_val, axis=1)
report = classification_report(true, preds, target_names=LABEL_NAMES, digits=4)
print(f"\n📈 Val Accuracy: {val_acc*100:.2f}%")
print(report)

with open(HISTORY_PATH, 'w') as f:
    json.dump({k: [float(v) for v in vals] for k, vals in history.history.items()}, f)
with open(REPORT_PATH, 'w') as f:
    f.write(f"GRU + Attention\nVal Accuracy: {val_acc*100:.2f}%\n\n{report}")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('GRU + Attention — Training Curves', fontsize=14, fontweight='bold')
axes[0].plot(history.history['accuracy'], label='Train', color='#7c3aed', linewidth=2)
axes[0].plot(history.history['val_accuracy'], label='Val', color='#a78bfa', linewidth=2, linestyle='--')
axes[0].set_title('Accuracy'); axes[0].legend(); axes[0].grid(alpha=0.3)
axes[1].plot(history.history['loss'], label='Train', color='#dc2626', linewidth=2)
axes[1].plot(history.history['val_loss'], label='Val', color='#f87171', linewidth=2, linestyle='--')
axes[1].set_title('Loss'); axes[1].legend(); axes[1].grid(alpha=0.3)
plt.tight_layout(); plt.savefig(PLOT_PATH, dpi=150); plt.close()

cm = confusion_matrix(true, preds)
plt.figure(figsize=(8, 6))
sns.heatmap(cm, annot=True, fmt='d', cmap='Purples',
            xticklabels=LABEL_NAMES, yticklabels=LABEL_NAMES)
plt.title('GRU + Attention — Confusion Matrix', fontweight='bold')
plt.ylabel('True'); plt.xlabel('Predicted')
plt.tight_layout(); plt.savefig(CM_PATH, dpi=150); plt.close()

print(f"\n✅ GRU + Attention complete! Accuracy: {val_acc*100:.1f}%")
print(f"   Model: {MODEL_PATH}\n")