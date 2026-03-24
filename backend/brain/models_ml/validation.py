"""
Walk-Forward and Purged K-Fold Validation

Financial-time-series-aware validation utilities that prevent look-ahead
bias and information leakage between train/test splits.

No external dependencies beyond numpy.
"""

import logging
from typing import Callable, Dict, Generator, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class WalkForwardSplitter:
    """
    Walk-forward (expanding or rolling window) splitter for time series.

    For each fold the model is trained on *train_window* observations and
    tested on the next *test_window* observations.  The window then slides
    forward by *step* observations (defaults to *test_window*).

    Example with train_window=100, test_window=20, step=20:
        Fold 0: train [0:100],   test [100:120]
        Fold 1: train [20:120],  test [120:140]
        ...
    """

    def __init__(
        self,
        train_window: int,
        test_window: int,
        step: Optional[int] = None,
    ):
        if train_window < 1:
            raise ValueError("train_window must be >= 1")
        if test_window < 1:
            raise ValueError("test_window must be >= 1")

        self.train_window = train_window
        self.test_window = test_window
        self.step = step if step is not None else test_window

    def split(
        self,
        X: np.ndarray,
        y: Optional[np.ndarray] = None,
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """
        Yield (train_indices, test_indices) for each fold.

        Args:
            X: Array-like of shape (n_samples, ...).
            y: Ignored. Present for API compatibility.

        Yields:
            Tuple of (train_indices, test_indices) as 1-D int arrays.
        """
        n = len(X)
        start = 0

        while start + self.train_window + self.test_window <= n:
            train_end = start + self.train_window
            test_end = train_end + self.test_window

            train_idx = np.arange(start, train_end)
            test_idx = np.arange(train_end, test_end)

            yield train_idx, test_idx
            start += self.step

    def get_n_splits(self, X: np.ndarray) -> int:
        """Return the number of folds for the given dataset size."""
        n = len(X)
        if n < self.train_window + self.test_window:
            return 0
        return 1 + max(
            0,
            (n - self.train_window - self.test_window) // self.step,
        )


class PurgedKFold:
    """
    Purged K-Fold cross-validation for financial time series.

    Removes *purge_gap* observations between each training and test set
    boundary to prevent information leakage from overlapping labels.
    Additionally, an *embargo* period (as a fraction of total observations)
    is removed after the test set before the next training window.

    Reference:
        De Prado, M.L. (2018). *Advances in Financial Machine Learning*.
    """

    def __init__(
        self,
        n_splits: int = 5,
        purge_gap: int = 5,
        embargo_pct: float = 0.01,
    ):
        if n_splits < 2:
            raise ValueError("n_splits must be >= 2")
        if purge_gap < 0:
            raise ValueError("purge_gap must be >= 0")
        if not 0.0 <= embargo_pct < 1.0:
            raise ValueError("embargo_pct must be in [0, 1)")

        self.n_splits = n_splits
        self.purge_gap = purge_gap
        self.embargo_pct = embargo_pct

    def split(
        self,
        X: np.ndarray,
        y: Optional[np.ndarray] = None,
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """
        Yield (train_indices, test_indices) for each fold.

        Args:
            X: Array-like of shape (n_samples, ...).
            y: Ignored.

        Yields:
            Tuple of (train_indices, test_indices) as 1-D int arrays.
        """
        n = len(X)
        indices = np.arange(n)
        embargo_size = int(n * self.embargo_pct)

        fold_sizes = np.full(self.n_splits, n // self.n_splits, dtype=int)
        fold_sizes[: n % self.n_splits] += 1

        current = 0
        for fold_size in fold_sizes:
            test_start = current
            test_end = current + fold_size

            test_idx = indices[test_start:test_end]

            # Build train indices: everything outside test + purge + embargo
            purge_start = max(0, test_start - self.purge_gap)
            purge_end = min(n, test_end + self.purge_gap + embargo_size)

            train_mask = np.ones(n, dtype=bool)
            train_mask[purge_start:purge_end] = False

            train_idx = indices[train_mask]

            if len(train_idx) > 0 and len(test_idx) > 0:
                yield train_idx, test_idx

            current += fold_size

    def get_n_splits(self, X: Optional[np.ndarray] = None) -> int:
        """Return the number of folds."""
        return self.n_splits


def walk_forward_evaluate(
    model,
    X: np.ndarray,
    y: np.ndarray,
    train_window: int,
    test_window: int,
    metrics_fn: Callable[[np.ndarray, np.ndarray], Dict[str, float]],
    step: Optional[int] = None,
) -> Dict[str, List[float]]:
    """
    Convenience function: run walk-forward validation and collect metrics.

    Args:
        model: Any object with ``train(X, y)`` and ``predict(X)`` methods.
        X: Feature matrix (n_samples, n_features).
        y: Target array (n_samples,).
        train_window: Number of training observations per fold.
        test_window: Number of test observations per fold.
        metrics_fn: Callable(y_true, y_pred) -> dict of metric_name: value.
        step: How far to advance the window each fold. Defaults to test_window.

    Returns:
        Dictionary mapping metric names to lists of per-fold values.
    """
    splitter = WalkForwardSplitter(
        train_window=train_window,
        test_window=test_window,
        step=step,
    )

    all_metrics: Dict[str, List[float]] = {}
    fold = 0

    for train_idx, test_idx in splitter.split(X, y):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        model.train(X_train, y_train)
        y_pred = model.predict(X_test)

        fold_metrics = metrics_fn(y_test, y_pred)

        for name, value in fold_metrics.items():
            all_metrics.setdefault(name, []).append(value)

        logger.info(
            "Walk-forward fold %d: %s",
            fold,
            {k: f"{v:.4f}" for k, v in fold_metrics.items()},
        )
        fold += 1

    if fold == 0:
        logger.warning(
            "No folds generated. Dataset length=%d, train_window=%d, test_window=%d",
            len(X),
            train_window,
            test_window,
        )

    return all_metrics
