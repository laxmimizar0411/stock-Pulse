"""
LSTM with Attention — Intraday pattern detection (Tier 3).

Structure ready for training. Requires PyTorch.
In production, exports to ONNX for fast inference.

Allocation: 10% of ensemble weight.
Purpose: Capture sequential patterns that tree models miss.

Note: Fully functional structure. Training requires:
  pip install torch
"""

import logging
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("brain.models_ml.deep_learning.lstm_attention")

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.info("PyTorch not available — LSTM model disabled")


class LSTMAttentionModel:
    """
    LSTM with self-attention for time-series direction prediction.

    Architecture:
    - Input: (batch, seq_len, n_features)
    - 2-layer LSTM (hidden=128)
    - Multi-head self-attention (4 heads)
    - Dropout (0.3)
    - Linear output -> 3 classes (UP/DOWN/NEUTRAL)
    """

    def __init__(self, input_dim: int = 15, hidden_dim: int = 128,
                 num_layers: int = 2, num_heads: int = 4,
                 dropout: float = 0.3, seq_len: int = 20):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.num_heads = num_heads
        self.dropout = dropout
        self.seq_len = seq_len
        self.model_name = "lstm_attention"
        self.model_version = "0.1.0"
        self._model = None
        self._trained = False

        if TORCH_AVAILABLE:
            self._build_model()

    def _build_model(self):
        """Build the LSTM + Attention architecture."""
        if not TORCH_AVAILABLE:
            return

        class _LSTMAttentionNet(nn.Module):
            def __init__(self_, input_dim, hidden_dim, num_layers, num_heads, dropout):
                super().__init__()
                self_.lstm = nn.LSTM(
                    input_dim, hidden_dim, num_layers,
                    batch_first=True, dropout=dropout,
                )
                self_.attention = nn.MultiheadAttention(
                    hidden_dim, num_heads, dropout=dropout, batch_first=True,
                )
                self_.layer_norm = nn.LayerNorm(hidden_dim)
                self_.fc = nn.Sequential(
                    nn.Linear(hidden_dim, 64),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                    nn.Linear(64, 3),  # 3 classes
                )

            def forward(self_, x):
                lstm_out, _ = self_.lstm(x)
                attn_out, _ = self_.attention(lstm_out, lstm_out, lstm_out)
                normed = self_.layer_norm(attn_out[:, -1, :])  # Last timestep
                return self_.fc(normed)

        self._model = _LSTMAttentionNet(
            self.input_dim, self.hidden_dim, self.num_layers,
            self.num_heads, self.dropout,
        )
        logger.info("LSTM-Attention model built (params: %d)",
                    sum(p.numel() for p in self._model.parameters()))

    @property
    def is_available(self):
        return TORCH_AVAILABLE

    @property
    def is_trained(self):
        return self._trained

    def train(self, X: np.ndarray, y: np.ndarray,
              epochs: int = 50, batch_size: int = 32,
              lr: float = 0.001) -> Dict[str, float]:
        """Train the LSTM model."""
        if not TORCH_AVAILABLE:
            return {"error": "PyTorch not available"}

        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.LongTensor(y)

        dataset = torch.utils.data.TensorDataset(X_tensor, y_tensor)
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

        optimizer = torch.optim.Adam(self._model.parameters(), lr=lr)
        criterion = nn.CrossEntropyLoss()

        self._model.train()
        best_loss = float('inf')

        for epoch in range(epochs):
            total_loss = 0
            correct = 0
            total = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                output = self._model(batch_X)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
                _, predicted = torch.max(output, 1)
                correct += (predicted == batch_y).sum().item()
                total += batch_y.size(0)

            avg_loss = total_loss / len(loader)
            accuracy = correct / total
            if avg_loss < best_loss:
                best_loss = avg_loss

            if (epoch + 1) % 10 == 0:
                logger.info("LSTM Epoch %d/%d: loss=%.4f acc=%.4f",
                            epoch + 1, epochs, avg_loss, accuracy)

        self._trained = True
        return {
            "final_loss": best_loss,
            "final_accuracy": accuracy,
            "epochs": epochs,
        }

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict direction."""
        if not TORCH_AVAILABLE or not self._trained:
            return np.array([])

        self._model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X)
            output = self._model(X_tensor)
            _, predicted = torch.max(output, 1)
        return predicted.numpy()

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        if not TORCH_AVAILABLE or not self._trained:
            return np.array([])

        self._model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X)
            output = self._model(X_tensor)
            proba = torch.softmax(output, dim=1)
        return proba.numpy()

    def get_info(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "available": TORCH_AVAILABLE,
            "trained": self._trained,
            "architecture": {
                "type": "LSTM + MultiheadAttention",
                "input_dim": self.input_dim,
                "hidden_dim": self.hidden_dim,
                "num_layers": self.num_layers,
                "num_heads": self.num_heads,
                "seq_len": self.seq_len,
            },
        }
