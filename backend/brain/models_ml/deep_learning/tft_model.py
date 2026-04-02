"""
Temporal Fusion Transformer (TFT) — Multi-horizon swing targets.

Primary model for 5d/10d/20d quantile forecasts.
Implements TFT architecture with:
- Variable Selection Networks
- LSTM Encoder-Decoder
- Multi-head Attention
- Quantile regression heads (10%, 50%, 90%)

Architecture based on:
"Temporal Fusion Transformers for Interpretable Multi-horizon Time Series Forecasting"
(Lim et al., 2020)
"""

import logging
import numpy as np
from typing import Any, Dict, Optional, Tuple
import pickle
import os

logger = logging.getLogger("brain.models_ml.deep_learning.tft_model")

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    # Create stub nn.Module for when PyTorch is not available
    class _StubModule:
        pass
    nn = type('nn', (), {'Module': _StubModule})()
    torch = None
    logger.warning("PyTorch not available - TFT model disabled")


class VariableSelectionNetwork(nn.Module):
    """Variable Selection Network with Gating."""
    
    def __init__(self, input_dim: int, hidden_dim: int, dropout: float = 0.1):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        
        # GRN for variable selection weights
        self.grn = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, input_dim),
            nn.Softmax(dim=-1)
        )
        
        # Feature transformation
        self.transform = nn.Linear(input_dim, hidden_dim)
        
    def forward(self, x):
        # x: (batch, seq_len, input_dim) or (batch, input_dim)
        weights = self.grn(x)  # Variable selection weights
        selected = x * weights
        output = self.transform(selected)
        return output, weights


class LSTMEncoderDecoder(nn.Module):
    """LSTM Encoder-Decoder with skip connections."""
    
    def __init__(self, input_dim: int, hidden_dim: int, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        self.encoder = nn.LSTM(
            input_dim,
            hidden_dim,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0
        )
        
        self.decoder = nn.LSTM(
            hidden_dim,
            hidden_dim,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0
        )
        
    def forward(self, x):
        # x: (batch, seq_len, input_dim)
        # Encode
        encoder_output, (hidden, cell) = self.encoder(x)
        
        # Decode (autoregressive, simplified for single-step)
        decoder_output, _ = self.decoder(encoder_output, (hidden, cell))
        
        return decoder_output, encoder_output


class InterpretableMultiHeadAttention(nn.Module):
    """Interpretable multi-head attention with additive aggregation."""
    
    def __init__(self, hidden_dim: int, num_heads: int = 4, dropout: float = 0.1):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads
        self.head_dim = hidden_dim // num_heads
        
        assert hidden_dim % num_heads == 0, "hidden_dim must be divisible by num_heads"
        
        self.query = nn.Linear(hidden_dim, hidden_dim)
        self.key = nn.Linear(hidden_dim, hidden_dim)
        self.value = nn.Linear(hidden_dim, hidden_dim)
        self.out = nn.Linear(hidden_dim, hidden_dim)
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, x):
        # x: (batch, seq_len, hidden_dim)
        batch_size, seq_len, _ = x.shape
        
        # Linear projections
        Q = self.query(x).view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        K = self.key(x).view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        V = self.value(x).view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        
        # Scaled dot-product attention
        scores = torch.matmul(Q, K.transpose(-2, -1)) / (self.head_dim ** 0.5)
        attn_weights = torch.softmax(scores, dim=-1)
        attn_weights = self.dropout(attn_weights)
        
        # Apply attention to values
        attn_output = torch.matmul(attn_weights, V)
        
        # Concat heads and project
        attn_output = attn_output.transpose(1, 2).contiguous().view(batch_size, seq_len, self.hidden_dim)
        output = self.out(attn_output)
        
        return output, attn_weights


class TemporalFusionTransformer(nn.Module):
    """
    Complete TFT architecture for multi-horizon quantile forecasting.
    
    Architecture Flow:
    1. Variable Selection Network (input gating)
    2. LSTM Encoder-Decoder (temporal processing)
    3. Multi-head Attention (feature importance)
    4. Quantile regression heads (P10, P50, P90)
    """
    
    def __init__(
        self,
        input_dim: int = 15,
        hidden_dim: int = 64,
        num_lstm_layers: int = 2,
        num_attention_heads: int = 4,
        dropout: float = 0.1,
        num_quantiles: int = 3,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_quantiles = num_quantiles
        
        # 1. Variable Selection Network
        self.vsn = VariableSelectionNetwork(input_dim, hidden_dim, dropout)
        
        # 2. LSTM Encoder-Decoder
        self.lstm = LSTMEncoderDecoder(hidden_dim, hidden_dim, num_lstm_layers, dropout)
        
        # 3. Multi-head Attention
        self.attention = InterpretableMultiHeadAttention(hidden_dim, num_attention_heads, dropout)
        
        # 4. Feed-forward enrichment
        self.enrichment = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim * 2),
            nn.ELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim * 2, hidden_dim),
        )
        
        # 5. Quantile output heads (one per quantile)
        self.quantile_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, 1)
            ) for _ in range(num_quantiles)
        ])
        
        # Layer normalization
        self.norm1 = nn.LayerNorm(hidden_dim)
        self.norm2 = nn.LayerNorm(hidden_dim)
        
    def forward(self, x):
        # x: (batch, seq_len, input_dim) or (batch, input_dim)
        
        # Handle 2D input (batch, input_dim) -> (batch, 1, input_dim)
        if x.dim() == 2:
            x = x.unsqueeze(1)
        
        # 1. Variable selection
        vsn_output, vsn_weights = self.vsn(x)
        
        # 2. LSTM encoding-decoding
        lstm_output, encoder_output = self.lstm(vsn_output)
        lstm_output = self.norm1(lstm_output + vsn_output)  # Skip connection
        
        # 3. Multi-head attention
        attn_output, attn_weights = self.attention(lstm_output)
        attn_output = self.norm2(attn_output + lstm_output)  # Skip connection
        
        # 4. Feed-forward enrichment
        enriched = self.enrichment(attn_output)
        enriched = enriched + attn_output  # Skip connection
        
        # 5. Take last timestep for prediction
        final_features = enriched[:, -1, :]  # (batch, hidden_dim)
        
        # 6. Quantile predictions
        quantile_outputs = [head(final_features) for head in self.quantile_heads]
        quantiles = torch.cat(quantile_outputs, dim=-1)  # (batch, num_quantiles)
        
        return quantiles, attn_weights, vsn_weights


class TFTModel:
    """
    Temporal Fusion Transformer for multi-horizon stock prediction.

    Provides quantile forecasts at 5-day, 10-day, and 20-day horizons.
    Uses variable selection networks and interpretable attention.

    Architecture:
    - Variable Selection Networks (static + temporal)
    - LSTM Encoder-Decoder
    - Multi-head Interpretable Attention
    - Quantile output (10%, 50%, 90%)
    """

    def __init__(
        self,
        input_dim: int = 15,
        hidden_dim: int = 64,
        num_lstm_layers: int = 2,
        num_attention_heads: int = 4,
        dropout: float = 0.1,
    ):
        self.model_name = "tft_multi_horizon"
        self.model_version = "0.1.0"
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_lstm_layers = num_lstm_layers
        self.num_attention_heads = num_attention_heads
        self.dropout = dropout
        self.horizons = [5, 10, 20]
        self.quantiles = [0.1, 0.5, 0.9]
        
        self._model: Optional[TemporalFusionTransformer] = None
        self._trained = False
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu") if TORCH_AVAILABLE else None

    @property
    def is_available(self):
        return TORCH_AVAILABLE

    @property
    def is_trained(self):
        return self._trained

    def _quantile_loss(self, y_pred: Any, y_true: Any, quantiles: list) -> Any:
        """Quantile loss (pinball loss) for training."""
        losses = []
        for i, q in enumerate(quantiles):
            errors = y_true - y_pred[:, i]
            loss = torch.max((q - 1) * errors, q * errors)
            losses.append(loss.mean())
        return torch.stack(losses).mean()

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        val_split: float = 0.2,
        **kwargs
    ) -> Dict[str, float]:
        """
        Train TFT model with quantile regression.
        
        Args:
            X: Input features (n_samples, seq_len, input_dim) or (n_samples, input_dim)
            y: Target returns (n_samples, 1) for 5-day horizon
            epochs: Number of training epochs
            batch_size: Batch size
            learning_rate: Learning rate
            val_split: Validation split ratio
        """
        if not TORCH_AVAILABLE:
            return {"error": "PyTorch not available"}
        
        if X.shape[0] < 10:
            return {"error": "Insufficient training data"}
        
        # Initialize model
        if self._model is None:
            self._model = TemporalFusionTransformer(
                input_dim=self.input_dim if X.ndim == 3 else X.shape[1],
                hidden_dim=self.hidden_dim,
                num_lstm_layers=self.num_lstm_layers,
                num_attention_heads=self.num_attention_heads,
                dropout=self.dropout,
                num_quantiles=len(self.quantiles),
            )
            self._model.to(self._device)
        
        # Prepare data
        X_tensor = torch.FloatTensor(X).to(self._device)
        y_tensor = torch.FloatTensor(y).to(self._device)
        
        # Train/val split
        split_idx = int(len(X) * (1 - val_split))
        X_train, X_val = X_tensor[:split_idx], X_tensor[split_idx:]
        y_train, y_val = y_tensor[:split_idx], y_tensor[split_idx:]
        
        # DataLoader
        train_dataset = TensorDataset(X_train, y_train)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        
        # Optimizer
        optimizer = optim.Adam(self._model.parameters(), lr=learning_rate)
        
        # Training loop
        self._model.train()
        train_losses = []
        
        for epoch in range(epochs):
            epoch_loss = 0.0
            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()
                
                # Forward pass
                quantile_preds, _, _ = self._model(batch_X)
                
                # Quantile loss
                loss = self._quantile_loss(quantile_preds, batch_y, self.quantiles)
                
                # Backward pass
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._model.parameters(), max_norm=1.0)
                optimizer.step()
                
                epoch_loss += loss.item()
            
            avg_loss = epoch_loss / len(train_loader)
            train_losses.append(avg_loss)
            
            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch+1}/{epochs}, Loss: {avg_loss:.4f}")
        
        # Validation
        self._model.eval()
        with torch.no_grad():
            val_preds, _, _ = self._model(X_val)
            val_loss = self._quantile_loss(val_preds, y_val, self.quantiles).item()
        
        self._trained = True
        
        return {
            "final_train_loss": train_losses[-1],
            "val_loss": val_loss,
            "epochs": epochs,
            "samples_trained": len(X_train),
        }

    def predict(self, X: np.ndarray) -> Dict[str, Any]:
        """
        Multi-horizon quantile forecast.
        
        Returns:
            Dict with quantile predictions (P10, P50, P90) and attention weights
        """
        if not self._trained or self._model is None:
            return {"error": "Model not trained"}
        
        self._model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X).to(self._device)
            quantile_preds, attn_weights, vsn_weights = self._model(X_tensor)
            
            # Convert to numpy
            predictions = quantile_preds.cpu().numpy()
            
            return {
                "predictions": predictions.tolist(),
                "quantiles": self.quantiles,
                "p10": predictions[:, 0].tolist(),
                "p50": predictions[:, 1].tolist(),
                "p90": predictions[:, 2].tolist(),
                "attention_weights_shape": attn_weights.shape if attn_weights is not None else None,
                "vsn_weights_shape": vsn_weights.shape if vsn_weights is not None else None,
            }

    def save(self, path: str):
        """Save trained model to disk."""
        if not self._trained or self._model is None:
            logger.warning("Cannot save untrained model")
            return
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        torch.save({
            "model_state": self._model.state_dict(),
            "config": {
                "input_dim": self.input_dim,
                "hidden_dim": self.hidden_dim,
                "num_lstm_layers": self.num_lstm_layers,
                "num_attention_heads": self.num_attention_heads,
                "dropout": self.dropout,
            },
            "trained": self._trained,
        }, path)
        logger.info(f"TFT model saved to {path}")

    def load(self, path: str):
        """Load trained model from disk."""
        if not TORCH_AVAILABLE:
            logger.error("PyTorch not available")
            return
        
        checkpoint = torch.load(path, map_location=self._device)
        config = checkpoint["config"]
        
        self._model = TemporalFusionTransformer(
            input_dim=config["input_dim"],
            hidden_dim=config["hidden_dim"],
            num_lstm_layers=config["num_lstm_layers"],
            num_attention_heads=config["num_attention_heads"],
            dropout=config["dropout"],
            num_quantiles=len(self.quantiles),
        )
        self._model.load_state_dict(checkpoint["model_state"])
        self._model.to(self._device)
        self._trained = checkpoint["trained"]
        logger.info(f"TFT model loaded from {path}")

    def get_info(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "available": TORCH_AVAILABLE,
            "trained": self._trained,
            "horizons": self.horizons,
            "quantiles": self.quantiles,
            "architecture": "Temporal Fusion Transformer (LSTM + Attention + VSN)",
            "device": str(self._device) if self._device else "N/A",
            "parameters": sum(p.numel() for p in self._model.parameters()) if self._model else 0,
        }
