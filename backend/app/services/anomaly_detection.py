"""Anomaly detection service for AgentGuard.

Provides lightweight, explainable anomaly detection for payment authorization.
Uses Isolation Forest for statistical anomaly detection with deterministic
rule-based fallback for cold-start scenarios.

All models are trained offline and loaded at startup for reproducible results.
"""

import json
import logging
import math
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AuthorizationDecisionRecord,
    SecurityEvent,
    SecurityEventType,
    Transaction,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Model file paths
MODEL_DIR = Path(__file__).parent.parent.parent / "models"
MODEL_DIR.mkdir(exist_ok=True)
ISOLATION_FOREST_PATH = MODEL_DIR / "isolation_forest.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"

# Feature names (in order)
FEATURE_NAMES = [
    "amount_zscore",           # Transaction amount z-score vs agent history
    "amount_log",              # Log of transaction amount
    "txn_count_1h",            # Transactions in last hour
    "txn_count_24h",           # Transactions in last 24 hours
    "txn_count_7d",            # Transactions in last 7 days
    "avg_amount_7d",           # Average amount over 7 days
    "std_amount_7d",           # Std dev of amount over 7 days
    "unique_merchants_7d",     # Unique merchants in 7 days
    "merchant_novelty",        # 1 if new merchant, 0 if known
    "time_since_last_txn_h",   # Hours since last transaction
    "hour_of_day",             # Hour of day (0-23)
    "day_of_week",             # Day of week (0-6)
]

# Isolation Forest parameters
IF_PARAMS = {
    "n_estimators": 100,
    "contamination": 0.1,
    "max_samples": "auto",
    "random_state": 42,
    "n_jobs": 1,
}

# Risk score thresholds (0-100)
RISK_THRESHOLDS = {
    "low": 30,
    "medium": 60,
    "high": 80,
    "critical": 95,
}

# Minimum samples for ML model
MIN_SAMPLES_FOR_ML = 20


def normalize_risk_score(score: Any) -> int:
    """Return the canonical finite integer risk score in the 0-100 range."""
    value = float(score)
    if not math.isfinite(value):
        raise ValueError(f"Risk score must be finite, got {score!r}")
    return max(0, min(100, int(round(value))))


# =============================================================================
# Feature Engineering
# =============================================================================

class AnomalyFeatures:
    """Extracts and computes anomaly detection features for a transaction."""

    def __init__(self, db: Session, agent_id: int):
        self.db = db
        self.agent_id = agent_id
        self._history: Optional[List[AuthorizationDecisionRecord]] = None
        self._cached_stats: Optional[Dict[str, float]] = None

    def _get_history(self, hours: int = 24 * 7) -> List[AuthorizationDecisionRecord]:
        """Get agent's authorization history for the last N hours."""
        if self._history is not None:
            return self._history

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        history = self.db.execute(
            select(AuthorizationDecisionRecord)
            .where(
                AuthorizationDecisionRecord.agent_id == self.agent_id,
                AuthorizationDecisionRecord.decided_at >= cutoff,
                AuthorizationDecisionRecord.decision == "allow",  # Only ALLOW decisions for spending history
            )
            .order_by(AuthorizationDecisionRecord.decided_at.desc())
        ).scalars().all()

        self._history = list(history)
        return self._history

    def _compute_stats(self) -> Dict[str, float]:
        """Compute statistical features from history."""
        if self._cached_stats is not None:
            return self._cached_stats

        history = self._get_history()
        amounts = [h.amount_cents / 100.0 for h in history]  # Convert to dollars

        if len(amounts) < 2:
            self._cached_stats = {
                "mean": 0.0,
                "std": 0.0,
                "count": len(amounts),
                "unique_merchants": 0,
                "last_txn_time": None,
            }
            return self._cached_stats

        unique_merchants = len(set(h.merchant_id for h in history))
        last_txn = history[0].decided_at if history else None

        self._cached_stats = {
            "mean": float(np.mean(amounts)),
            "std": float(np.std(amounts)) if len(amounts) > 1 else 0.0,
            "count": len(amounts),
            "unique_merchants": unique_merchants,
            "last_txn_time": last_txn,
        }
        return self._cached_stats

    def extract(
        self,
        amount_cents: int,
        merchant_id: str,
        currency: str = "USD",
    ) -> Dict[str, float]:
        """Extract feature vector for a transaction."""
        stats = self._compute_stats()
        history = self._get_history()

        amount_usd = amount_cents / 100.0
        now = datetime.utcnow()

        # Amount z-score
        if stats["std"] > 0:
            amount_zscore = (amount_usd - stats["mean"]) / stats["std"]
        else:
            amount_zscore = 0.0

        # Transaction velocity
        cutoff_1h = now - timedelta(hours=1)
        cutoff_24h = now - timedelta(hours=24)
        cutoff_7d = now - timedelta(days=7)

        txn_count_1h = sum(1 for h in history if h.decided_at >= cutoff_1h)
        txn_count_24h = sum(1 for h in history if h.decided_at >= cutoff_24h)
        txn_count_7d = sum(1 for h in history if h.decided_at >= cutoff_7d)

        # Average amount in 7 days
        recent_7d = [h.amount_cents / 100.0 for h in history if h.decided_at >= cutoff_7d]
        avg_amount_7d = float(np.mean(recent_7d)) if recent_7d else 0.0
        std_amount_7d = float(np.std(recent_7d)) if len(recent_7d) > 1 else 0.0

        # Unique merchants in 7 days
        unique_merchants_7d = len(set(
            h.merchant_id for h in history if h.decided_at >= cutoff_7d
        ))

        # Merchant novelty
        known_merchants = set(h.merchant_id for h in history)
        merchant_novelty = 1.0 if merchant_id not in known_merchants else 0.0

        # Time since last transaction
        if stats["last_txn_time"]:
            time_since_last_txn_h = (now - stats["last_txn_time"]).total_seconds() / 3600
        else:
            time_since_last_txn_h = 168.0  # 1 week default for cold start

        # Time features
        hour_of_day = float(now.hour)
        day_of_week = float(now.weekday())

        return {
            "amount_zscore": float(np.clip(amount_zscore, -10, 10)),
            "amount_log": float(np.log1p(amount_usd)),
            "txn_count_1h": float(txn_count_1h),
            "txn_count_24h": float(txn_count_24h),
            "txn_count_7d": float(txn_count_7d),
            "avg_amount_7d": avg_amount_7d,
            "std_amount_7d": std_amount_7d,
            "unique_merchants_7d": float(unique_merchants_7d),
            "merchant_novelty": merchant_novelty,
            "time_since_last_txn_h": float(np.clip(time_since_last_txn_h, 0, 168)),
            "hour_of_day": hour_of_day,
            "day_of_week": day_of_week,
        }


# =============================================================================
# Rule-Based Anomaly Detection (Cold Start / Deterministic)
# =============================================================================

class RuleBasedDetector:
    """Deterministic rule-based anomaly detection for cold-start scenarios.

    This provides explainable, reproducible anomaly signals without requiring
    trained ML models. Rules are based on domain knowledge and security best practices.
    """

    def __init__(self):
        # Rule thresholds (configurable)
        self.rules = {
            "velocity_1h": 5,        # >5 txns/hour
            "velocity_24h": 20,      # >20 txns/day
            "amount_zscore": 3.0,    # >3 std deviations
            "amount_ratio": 5.0,     # >5x average amount
            "merchant_novelty": True,  # First time with merchant
            "time_gap_anomaly": 168, # >1 week since last txn (for regular agents)
        }

    def evaluate(
        self,
        features: Dict[str, float],
        agent_history_count: int,
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Evaluate rules and return risk contribution and signal details."""
        signals = []
        risk_contribution = 0.0

        # Velocity anomaly - burst transactions
        if features["txn_count_1h"] > self.rules["velocity_1h"]:
            severity = min(30, 5 + (features["txn_count_1h"] - self.rules["velocity_1h"]) * 3)
            signals.append({
                "type": "velocity_anomaly",
                "signal": "velocity_anomaly",
                "severity": "warning" if severity < 20 else "critical",
                "description": f"High transaction velocity: {features['txn_count_1h']:.0f} transactions in last hour",
                "details": {
                    "txn_count_1h": features["txn_count_1h"],
                    "threshold": self.rules["velocity_1h"],
                },
                "source": "rule_based",
            })
            risk_contribution += severity

        # Daily velocity anomaly
        if features["txn_count_24h"] > self.rules["velocity_24h"]:
            severity = min(20, 3 + (features["txn_count_24h"] - self.rules["velocity_24h"]) * 0.5)
            signals.append({
                "type": "velocity_anomaly",
                "signal": "velocity_anomaly",
                "severity": "warning" if severity < 15 else "critical",
                "description": f"High daily transaction count: {features['txn_count_24h']:.0f} transactions in 24 hours",
                "details": {
                    "txn_count_24h": features["txn_count_24h"],
                    "threshold": self.rules["velocity_24h"],
                },
                "source": "rule_based",
            })
            risk_contribution += severity

        # Amount anomaly - statistical outlier
        if abs(features["amount_zscore"]) > self.rules["amount_zscore"]:
            severity = min(25, 5 + (abs(features["amount_zscore"]) - self.rules["amount_zscore"]) * 5)
            direction = "unusually large" if features["amount_zscore"] > 0 else "unusually small"
            signals.append({
                "type": "amount_outlier",
                "signal": "amount_outlier",
                "severity": "warning" if severity < 15 else "critical",
                "description": f"Transaction amount is {direction} (z-score: {features['amount_zscore']:.2f})",
                "details": {
                    "amount_zscore": features["amount_zscore"],
                    "threshold": self.rules["amount_zscore"],
                },
                "source": "rule_based",
            })
            risk_contribution += severity

        # Amount ratio - compared to average
        if features["avg_amount_7d"] > 0:
            ratio = features["amount_log"] / np.log1p(features["avg_amount_7d"]) if features["avg_amount_7d"] > 0 else 1
            if ratio > self.rules["amount_ratio"]:
                severity = min(20, 5 + (ratio - self.rules["amount_ratio"]) * 3)
                signals.append({
                    "type": "amount_outlier",
                    "signal": "amount_outlier",
                    "severity": "warning",
                    "description": f"Transaction amount {ratio:.1f}x higher than 7-day average",
                    "details": {
                        "ratio": ratio,
                        "threshold": self.rules["amount_ratio"],
                    },
                    "source": "rule_based",
                })
                risk_contribution += severity

        # Merchant novelty
        if features["merchant_novelty"] > 0.5 and agent_history_count >= 3:
            signals.append({
                "type": "new_merchant",
                "signal": "new_merchant",
                "severity": "info",
                "description": "First transaction with this merchant",
                "details": {
                    "merchant_id": "unknown",  # Would be passed separately
                    "known_merchants_count": int(features["unique_merchants_7d"]),
                },
                "source": "rule_based",
            })
            risk_contribution += 8

        # Time gap anomaly - dormant agent suddenly active
        if features["time_since_last_txn_h"] > self.rules["time_gap_anomaly"] and agent_history_count >= 5:
            signals.append({
                "type": "pattern_deviation",
                "signal": "pattern_deviation",
                "severity": "warning",
                "description": f"Agent inactive for {features['time_since_last_txn_h']:.1f} hours, now transacting",
                "details": {
                    "hours_since_last_txn": features["time_since_last_txn_h"],
                    "threshold": self.rules["time_gap_anomaly"],
                },
                "source": "rule_based",
            })
            risk_contribution += 12

        # Off-hours transaction (optional - based on agent's typical pattern)
        # This would require more history, so we skip for now

        return min(risk_contribution, 100), signals


# =============================================================================
# ML-Based Anomaly Detection (Isolation Forest)
# =============================================================================

class MLAnomalyDetector:
    """Isolation Forest based anomaly detection for trained agents.

    Models are trained offline and loaded at startup for reproducibility.
    """

    def __init__(self):
        self.model: Optional[Any] = None
        self.scaler: Optional[Any] = None
        self._load_models()

    def _load_models(self):
        """Load pre-trained models from disk."""
        try:
            if ISOLATION_FOREST_PATH.exists() and SCALER_PATH.exists():
                with open(ISOLATION_FOREST_PATH, "rb") as f:
                    self.model = pickle.load(f)
                with open(SCALER_PATH, "rb") as f:
                    self.scaler = pickle.load(f)
                logger.info("Loaded pre-trained Isolation Forest model")
            else:
                logger.info("No pre-trained model found, will use rule-based detection")
        except Exception as e:
            logger.warning(f"Failed to load ML models: {e}. Falling back to rule-based detection.")
            self.model = None
            self.scaler = None

    def is_available(self) -> bool:
        """Check if ML model is loaded and ready."""
        return self.model is not None and self.scaler is not None

    def predict(
        self,
        features: Dict[str, float],
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Predict anomaly score using Isolation Forest.

        Returns:
            - anomaly_score: 0-100 (higher = more anomalous)
            - signals: List of contributing anomaly signals
        """
        if not self.is_available():
            return 0.0, []

        try:
            # Prepare feature vector in correct order
            X = np.array([[features[name] for name in FEATURE_NAMES]])

            # Scale features
            X_scaled = self.scaler.transform(X)

            # Get anomaly score (negative = more anomalous in Isolation Forest)
            # decision_function returns anomaly score (lower = more anomalous)
            raw_score = self.model.decision_function(X_scaled)[0]

            # Convert to 0-100 risk score
            # Isolation Forest scores are typically in range [-0.5, 0.5]
            # We invert and scale: more negative = higher risk
            anomaly_score = float(np.clip(50 - raw_score * 100, 0, 100))

            # Identify which features contribute most (simplified)
            signals = []
            if anomaly_score > 30:
                # Find top contributing features by comparing to training distribution
                feature_contributions = self._get_feature_contributions(X_scaled[0])
                for feat_name, contrib in feature_contributions[:3]:  # Top 3
                    signals.append({
                        "type": self._map_feature_to_signal(feat_name),
                        "signal": self._map_feature_to_signal(feat_name),
                        "severity": "warning" if contrib > 0.5 else "info",
                        "description": f"Anomalous {feat_name.replace('_', ' ')} (ML-detected)",
                        "details": {
                            "feature": feat_name,
                            "value": features.get(feat_name, 0),
                            "contribution": contrib,
                        },
                        "source": "ml_based",
                    })

            return anomaly_score, signals

        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            return 0.0, []

    def _get_feature_contributions(self, X: np.ndarray) -> List[Tuple[str, float]]:
        """Estimate feature contributions to anomaly score.

        Simplified: uses feature magnitude relative to training data.
        """
        # In a real implementation, this would use SHAP or similar
        # For now, return dummy contributions based on feature values
        contributions = []
        for i, name in enumerate(FEATURE_NAMES):
            val = abs(X[i])
            # Normalize by expected range
            contrib = min(1.0, val / 5.0)  # Rough normalization
            contributions.append((name, contrib))

        # Sort by contribution
        contributions.sort(key=lambda x: x[1], reverse=True)
        return contributions

    def _map_feature_to_signal(self, feature: str) -> str:
        """Map feature name to SecurityEventType signal."""
        mapping = {
            "amount_zscore": "amount_outlier",
            "amount_log": "amount_outlier",
            "txn_count_1h": "velocity_anomaly",
            "txn_count_24h": "velocity_anomaly",
            "txn_count_7d": "velocity_anomaly",
            "merchant_novelty": "new_merchant",
            "time_since_last_txn_h": "pattern_deviation",
            "hour_of_day": "pattern_deviation",
            "day_of_week": "pattern_deviation",
            "avg_amount_7d": "amount_outlier",
            "std_amount_7d": "amount_outlier",
            "unique_merchants_7d": "new_merchant",
        }
        return mapping.get(feature, "pattern_deviation")


# =============================================================================
# Main Anomaly Detection Service
# =============================================================================

class AnomalyDetectionService:
    """Main service for anomaly detection in payment authorization.

    Combines rule-based (deterministic, cold-start) and ML-based
    (Isolation Forest, trained agents) detection with clear attribution.
    """

    def __init__(self, db: Session):
        self.db = db
        self.rule_detector = RuleBasedDetector()
        self.ml_detector = MLAnomalyDetector()

    def assess_transaction(
        self,
        agent_id: int,
        amount_cents: int,
        merchant_id: str,
        currency: str = "USD",
    ) -> Dict[str, Any]:
        """Assess a transaction for anomalies.

        Returns a comprehensive risk assessment including:
        - Overall risk score (0-100)
        - Risk severity level
        - Contributing anomaly signals with explanations
        - Whether ML or rule-based detection was used
        """
        # Extract features
        feature_extractor = AnomalyFeatures(self.db, agent_id)
        features = feature_extractor.extract(amount_cents, merchant_id, currency)
        history_count = feature_extractor._compute_stats()["count"]

        # Rule-based detection (always runs, provides baseline)
        rule_score, rule_signals = self.rule_detector.evaluate(features, history_count)

        # ML-based detection (runs if model available and enough history)
        ml_score, ml_signals = 0.0, []
        detection_method = "rule_based"

        if self.ml_detector.is_available() and history_count >= MIN_SAMPLES_FOR_ML:
            ml_score, ml_signals = self.ml_detector.predict(features)
            # Keep the stronger independent signal. Averaging can dilute a
            # genuine ML anomaly with a low rule score and cross a decision
            # threshold in the wrong direction.
            if ml_score > 20:  # ML detected something notable
                combined_score = max(ml_score, rule_score)
                # Extreme velocity is an independent security signal. When
                # both detectors agree, preserve that compounded severity.
                if features["txn_count_1h"] > 20:
                    combined_score = min(100, ml_score + rule_score)
                detection_method = "ml_based"
            else:
                combined_score = rule_score
                detection_method = "rule_based"
        else:
            combined_score = rule_score
            detection_method = "rule_based"

        # Combine signals
        all_signals = rule_signals + ml_signals

        # Deduplicate signals by type
        seen_types = set()
        deduplicated_signals = []
        for signal in all_signals:
            if signal["type"] not in seen_types:
                seen_types.add(signal["type"])
                deduplicated_signals.append(signal)

        # Determine risk severity
        normalized_score = normalize_risk_score(combined_score)
        severity = self._score_to_severity(normalized_score)

        return {
            "risk_score": normalized_score,
            "risk_severity": severity,
            "detection_method": detection_method,
            "anomaly_signals": deduplicated_signals,
            "feature_vector": {k: round(v, 4) for k, v in features.items()},
            "history_count": history_count,
            "ml_available": self.ml_detector.is_available(),
        }

    def _score_to_severity(self, score: float) -> str:
        """Convert risk score to severity level."""
        if score >= RISK_THRESHOLDS["critical"]:
            return "critical"
        elif score >= RISK_THRESHOLDS["high"]:
            return "high"
        elif score >= RISK_THRESHOLDS["medium"]:
            return "medium"
        elif score >= RISK_THRESHOLDS["low"]:
            return "low"
        return "minimal"

    def should_trigger_review(self, risk_score: float, policy_threshold: float = 60) -> bool:
        """Determine if risk score should trigger REVIEW decision."""
        return risk_score >= policy_threshold

    def should_block(self, risk_score: float, block_threshold: float = 90) -> bool:
        """Determine if risk score should trigger BLOCK decision.

        Note: This is only for anomaly-based blocks. Hard policy violations
        (budget, limits, etc.) are handled separately and take precedence.
        """
        return risk_score >= block_threshold


# =============================================================================
# Model Training Utilities (Offline)
# =============================================================================

def train_isolation_forest(db: Session, output_dir: Optional[Path] = None) -> bool:
    """Train Isolation Forest model on historical transaction data.

    This should be run OFFLINE (not in production request path).
    Retrain periodically as new data accumulates.

    Args:
        db: Database session
        output_dir: Directory to save model (defaults to MODEL_DIR)

    Returns:
        True if training succeeded, False otherwise
    """
    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        logger.error("scikit-learn not available. Install with: pip install scikit-learn")
        return False

    if output_dir is None:
        output_dir = MODEL_DIR
    output_dir.mkdir(exist_ok=True)

    # Get training data from ALLOW decisions with sufficient history
    # We use AuthorizationDecisionRecord for features
    history = db.execute(
        select(AuthorizationDecisionRecord)
        .where(AuthorizationDecisionRecord.decision == "allow")
        .order_by(AuthorizationDecisionRecord.decided_at.desc())
        .limit(10000)
    ).scalars().all()

    if len(history) < MIN_SAMPLES_FOR_ML * 10:
        logger.warning(f"Insufficient training data: {len(history)} samples, need {MIN_SAMPLES_FOR_ML * 10}")
        return False

    # Group by agent to build features
    agent_histories = {}
    for record in history:
        if record.agent_id not in agent_histories:
            agent_histories[record.agent_id] = []
        agent_histories[record.agent_id].append(record)

    # Build feature matrix
    feature_rows = []
    for agent_id, records in agent_histories.items():
        if len(records) < 5:  # Skip agents with too little history
            continue

        # Sort by time
        records.sort(key=lambda r: r.decided_at)

        # Use each record as a training example with preceding history
        for i, record in enumerate(records):
            if i < 3:  # Need some history before
                continue

            # Build features using preceding records
            preceding = records[:i]
            amounts = [r.amount_cents / 100.0 for r in preceding]
            unique_merchants = set(r.merchant_id for r in preceding)

            amount_usd = record.amount_cents / 100.0
            merchant_novelty = 1.0 if record.merchant_id not in unique_merchants else 0.0

            mean_amt = np.mean(amounts) if amounts else 0.0
            std_amt = np.std(amounts) if len(amounts) > 1 else 0.0
            zscore = (amount_usd - mean_amt) / std_amt if std_amt > 0 else 0.0

            # Time features
            dt = record.decided_at
            hour = dt.hour
            dow = dt.weekday()

            # Velocity
            cutoff_1h = dt - timedelta(hours=1)
            cutoff_24h = dt - timedelta(hours=24)
            cutoff_7d = dt - timedelta(days=7)

            txn_1h = sum(1 for r in preceding if r.decided_at >= cutoff_1h)
            txn_24h = sum(1 for r in preceding if r.decided_at >= cutoff_24h)
            txn_7d = sum(1 for r in preceding if r.decided_at >= cutoff_7d)

            recent_7d_amt = [r.amount_cents / 100.0 for r in preceding if r.decided_at >= cutoff_7d]
            avg_7d = np.mean(recent_7d_amt) if recent_7d_amt else 0.0
            std_7d = np.std(recent_7d_amt) if len(recent_7d_amt) > 1 else 0.0
            unique_7d = len(set(r.merchant_id for r in preceding if r.decided_at >= cutoff_7d))

            # Time since last
            last_time = preceding[-1].decided_at if preceding else dt
            time_gap = (dt - last_time).total_seconds() / 3600

            feature_rows.append({
                "amount_zscore": np.clip(zscore, -10, 10),
                "amount_log": np.log1p(amount_usd),
                "txn_count_1h": txn_1h,
                "txn_count_24h": txn_24h,
                "txn_count_7d": txn_7d,
                "avg_amount_7d": avg_7d,
                "std_amount_7d": std_7d,
                "unique_merchants_7d": unique_7d,
                "merchant_novelty": merchant_novelty,
                "time_since_last_txn_h": np.clip(time_gap, 0, 168),
                "hour_of_day": hour,
                "day_of_week": dow,
            })

    if len(feature_rows) < MIN_SAMPLES_FOR_ML * 5:
        logger.warning(f"Insufficient feature rows: {len(feature_rows)}")
        return False

    # Convert to numpy array
    X = np.array([[row[name] for name in FEATURE_NAMES] for row in feature_rows])

    # Train scaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train Isolation Forest
    model = IsolationForest(**IF_PARAMS)
    model.fit(X_scaled)

    # Save models
    with open(output_dir / "isolation_forest.pkl", "wb") as f:
        pickle.dump(model, f)
    with open(output_dir / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    logger.info(f"Trained Isolation Forest on {len(feature_rows)} samples, saved to {output_dir}")
    return True


def evaluate_model(db: Session) -> Dict[str, Any]:
    """Evaluate trained model on held-out data."""
    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return {"error": "scikit-learn not available"}

    if not ISOLATION_FOREST_PATH.exists():
        return {"error": "No trained model found"}

    with open(ISOLATION_FOREST_PATH, "rb") as f:
        model = pickle.load(f)
    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)

    # Get test data (recent, not used in training)
    # For simplicity, use a time-based split
    cutoff = datetime.utcnow() - timedelta(days=7)
    history = db.execute(
        select(AuthorizationDecisionRecord)
        .where(
            AuthorizationDecisionRecord.decision == "allow",
            AuthorizationDecisionRecord.decided_at >= cutoff,
        )
        .order_by(AuthorizationDecisionRecord.decided_at.desc())
        .limit(1000)
    ).scalars().all()

    # Similar feature extraction as training...
    # This is a placeholder for actual evaluation
    return {
        "model_type": "IsolationForest",
        "n_estimators": IF_PARAMS["n_estimators"],
        "contamination": IF_PARAMS["contamination"],
        "test_samples": len(history),
        "note": "Full evaluation requires proper train/test split",
    }
