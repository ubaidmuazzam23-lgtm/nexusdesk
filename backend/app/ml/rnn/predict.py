# File: backend/app/ml/rnn/predict.py
import os, pickle
import numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

BASE_DIR       = os.path.dirname(__file__)
MODEL_PATH     = os.path.join(BASE_DIR, "data", "rnn_model.h5")
TOKENIZER_PATH = os.path.join(os.path.dirname(BASE_DIR), "bilstm", "data", "tokenizer.pkl")
CLASSES        = ['simple', 'moderate', 'complex']
MAX_LEN        = 100

_model     = None
_tokenizer = None

def _load():
    global _model, _tokenizer
    if _model is not None: return
    if not os.path.exists(MODEL_PATH) or not os.path.exists(TOKENIZER_PATH):
        raise FileNotFoundError("rnn model not trained yet")
    import tensorflow as tf
    from tensorflow.keras.layers import Layer, Dense

    class BahdanauAttention(Layer):
        def __init__(self, units=64, **kwargs):
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

    _model = tf.keras.models.load_model(
        MODEL_PATH,
        custom_objects={'BahdanauAttention': BahdanauAttention}
    )
    with open(TOKENIZER_PATH, 'rb') as f:
        _tokenizer = pickle.load(f)

def predict_complexity(text: str) -> dict:
    try:
        _load()
    except FileNotFoundError:
        return {"complexity": "moderate", "confidence": 0.0,
                "scores": {"simple": 0.33, "moderate": 0.34, "complex": 0.33},
                "error": "rnn model not trained yet"}
    from tensorflow.keras.preprocessing.sequence import pad_sequences
    seq    = _tokenizer.texts_to_sequences([text.lower().strip()])
    padded = pad_sequences(seq, maxlen=MAX_LEN, padding='post', truncating='post')
    probs  = _model.predict(padded, verbose=0)[0]
    idx    = int(np.argmax(probs))
    return {
        "complexity": CLASSES[idx],
        "confidence": round(float(probs[idx]), 4),
        "scores": {
            "simple":   round(float(probs[0]), 4),
            "moderate": round(float(probs[1]), 4),
            "complex":  round(float(probs[2]), 4),
        }
    }