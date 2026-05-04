# File: backend/app/ml/bilstm/model.py
#
# BiLSTM Complexity Classifier for NexusDesk
#
# Architecture:
#   Text → Embedding → BiLSTM(128) → Dropout → BiLSTM(64) → Dropout
#        → GlobalMaxPool → Dense(64, ReLU) → Dropout → Dense(3, Softmax)
#
# Output classes: simple | moderate | complex

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # suppress TF info logs

import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import (
    Input, Embedding, Bidirectional, LSTM,
    Dense, Dropout, GlobalMaxPooling1D,
    SpatialDropout1D, BatchNormalization,
)
from tensorflow.keras.regularizers import l2


# ── Hyperparameters ───────────────────────────────────────────────────────────

class Config:
    # Vocabulary & sequence
    VOCAB_SIZE     = 3000   # top N words to keep
    MAX_LEN       = 50     # max token length per ticket description
    OOV_TOKEN     = "<OOV>" # out-of-vocabulary token

    # Embedding
    EMBED_DIM     = 128     # embedding vector size

    # BiLSTM layers
    LSTM_UNITS_1  = 64      # units per direction in layer 1 → 128 total
    LSTM_UNITS_2  = 32      # units per direction in layer 2 → 64 total

    # Regularization
    SPATIAL_DROP  = 0.3     # spatial dropout after embedding
    LSTM_DROP     = 0.3     # dropout inside LSTM cells
    RECURRENT_DROP= 0.2     # recurrent dropout inside LSTM
    DENSE_DROP    = 0.4     # dropout before final dense layer
    L2_REG        = 1e-4    # L2 weight regularization

    # Output
    NUM_CLASSES   = 3       # simple, moderate, complex
    CLASSES       = ['simple', 'moderate', 'complex']


# ── Model Builder ─────────────────────────────────────────────────────────────

def build_model(config: Config = None) -> Model:
    """
    Build and compile the BiLSTM complexity classifier.

    Architecture rationale:
    - SpatialDropout1D: drops entire embedding dimensions (better than regular
      dropout for sequences — preserves temporal structure)
    - Bidirectional LSTM: reads sequence forward AND backward — captures
      context like "not working AFTER migration" vs just "not working"
    - Two stacked BiLSTM layers: layer 1 captures local patterns (word pairs),
      layer 2 captures global context (full sentence meaning)
    - GlobalMaxPooling1D: takes the most activated feature across all timesteps
      — more robust than taking only the last hidden state
    - BatchNormalization: stabilizes training, allows higher learning rates
    - L2 regularization: prevents weight explosion on small datasets
    """
    if config is None:
        config = Config()

    # ── Input ─────────────────────────────────────────────────────────────────
    inputs = Input(shape=(config.MAX_LEN,), name='token_input')

    # ── Embedding layer ───────────────────────────────────────────────────────
    # Learns word representations specific to IT support language
    x = Embedding(
        input_dim=config.VOCAB_SIZE,
        output_dim=config.EMBED_DIM,
        input_length=config.MAX_LEN,
        name='word_embedding',
        embeddings_regularizer=l2(config.L2_REG),
    )(inputs)

    # SpatialDropout1D: randomly zeroes entire feature maps
    # better than Dropout for sequences
    x = SpatialDropout1D(config.SPATIAL_DROP, name='spatial_dropout')(x)

    # ── BiLSTM Layer 1 ────────────────────────────────────────────────────────
    # return_sequences=True: passes full sequence to next layer
    # Forward + Backward = 2 × LSTM_UNITS_1 total output
    x = Bidirectional(
        LSTM(
            config.LSTM_UNITS_1,
            return_sequences=True,          # pass sequence to layer 2
            dropout=config.LSTM_DROP,       # input/output dropout
            recurrent_dropout=config.RECURRENT_DROP,  # hidden state dropout
            kernel_regularizer=l2(config.L2_REG),
            name='lstm_1',
        ),
        merge_mode='concat',                # concat forward + backward
        name='bilstm_1',
    )(x)

    x = BatchNormalization(name='bn_1')(x)

    # ── BiLSTM Layer 2 ────────────────────────────────────────────────────────
    # return_sequences=True: needed for GlobalMaxPooling
    x = Bidirectional(
        LSTM(
            config.LSTM_UNITS_2,
            return_sequences=True,
            dropout=config.LSTM_DROP,
            recurrent_dropout=config.RECURRENT_DROP,
            kernel_regularizer=l2(config.L2_REG),
            name='lstm_2',
        ),
        merge_mode='concat',
        name='bilstm_2',
    )(x)

    x = BatchNormalization(name='bn_2')(x)

    # ── Global Max Pooling ────────────────────────────────────────────────────
    # Takes max activation across all timesteps
    # More robust than last-timestep — captures strongest signal anywhere
    x = GlobalMaxPooling1D(name='global_max_pool')(x)

    # ── Dense layers ─────────────────────────────────────────────────────────
    x = Dense(
        64,
        activation='relu',
        kernel_regularizer=l2(config.L2_REG),
        name='dense_1',
    )(x)
    x = BatchNormalization(name='bn_3')(x)
    x = Dropout(config.DENSE_DROP, name='dense_dropout')(x)

    # ── Output layer ─────────────────────────────────────────────────────────
    # Softmax: outputs probability distribution over 3 classes
    outputs = Dense(
        config.NUM_CLASSES,
        activation='softmax',
        name='complexity_output',
    )(x)

    # ── Compile ───────────────────────────────────────────────────────────────
    model = Model(inputs=inputs, outputs=outputs, name='NexusDesk_BiLSTM')

    model.compile(
        optimizer=tf.keras.optimizers.Adam(
            learning_rate=1e-3,
            beta_1=0.9,
            beta_2=0.999,
            epsilon=1e-7,
        ),
        loss='sparse_categorical_crossentropy',
        metrics=['accuracy'],
    )

    return model


def print_summary(model: Model) -> None:
    print("\n" + "=" * 60)
    print("  NexusDesk BiLSTM — Model Summary")
    print("=" * 60)
    model.summary()
    total_params = model.count_params()
    print(f"\n  Total parameters: {total_params:,}")
    print(f"  Trainable:        {sum(tf.size(v).numpy() for v in model.trainable_variables):,}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    cfg   = Config()
    model = build_model(cfg)
    print_summary(model)