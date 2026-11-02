"""Train Isolation Forest model on synthetic transaction data.

This script generates reproducible synthetic transaction data that mimics
normal payment patterns, then trains an Isolation Forest model for anomaly detection.

The synthetic data includes:
- Normal transactions: typical amounts, velocities, merchants
- Anomalous transactions: unusual amounts, high velocity, new merchants, odd hours
- Labeled data for evaluation

Usage:
    python train_model.py
"""

import json
import pickle
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# Configuration (must match anomaly_detection.py)
FEATURE_NAMES = [
    "amount_zscore",
    "amount_log",
    "txn_count_1h",
    "txn_count_24h",
    "txn_count_7d",
    "avg_amount_7d",
    "std_amount_7d",
    "unique_merchants_7d",
    "merchant_novelty",
    "time_since_last_txn_h",
    "hour_of_day",
    "day_of_week",
]

IF_PARAMS = {
    "n_estimators": 100,
    "contamination": 0.1,
    "max_samples": "auto",
    "random_state": 42,
    "n_jobs": 1,
}

MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)
ISOLATION_FOREST_PATH = MODEL_DIR / "isolation_forest.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"


def generate_synthetic_data(n_agents=100, n_transactions_per_agent=50, seed=42):
    """Generate synthetic transaction data for training.

    Creates realistic patterns:
    - Most agents have regular spending patterns
    - Some agents have higher velocity
    - Some agents have variable amounts
    - Anomalous transactions are rare (10% contamination)
    """
    np.random.seed(seed)

    feature_rows = []
    labels = []  # 0 = normal, 1 = anomaly (for evaluation)

    for agent_id in range(n_agents):
        # Agent profile
        agent_type = np.random.choice(
            ["regular", "high_velocity", "variable_amounts", "night_owl"],
            p=[0.6, 0.15, 0.15, 0.1]
        )

        if agent_type == "regular":
            base_amount = np.random.uniform(10, 200)  # $10-$200 typical
            amount_std = base_amount * 0.3
            txn_per_day = np.random.uniform(1, 5)
            preferred_hours = list(range(9, 21))  # Business hours
            merchants = [f"MERCH_{np.random.randint(1, 20):03d}" for _ in range(5)]
        elif agent_type == "high_velocity":
            base_amount = np.random.uniform(5, 50)  # Small frequent purchases
            amount_std = base_amount * 0.2
            txn_per_day = np.random.uniform(20, 50)
            preferred_hours = list(range(8, 22))
            merchants = [f"MERCH_{np.random.randint(1, 10):03d}" for _ in range(3)]
        elif agent_type == "variable_amounts":
            base_amount = np.random.uniform(20, 500)
            amount_std = base_amount * 0.8  # High variance
            txn_per_day = np.random.uniform(2, 8)
            preferred_hours = list(range(9, 21))
            merchants = [f"MERCH_{np.random.randint(1, 30):03d}" for _ in range(8)]
        else:  # night_owl
            base_amount = np.random.uniform(10, 100)
            amount_std = base_amount * 0.4
            txn_per_day = np.random.uniform(1, 5)
            preferred_hours = list(range(0, 8)) + list(range(22, 24))
            merchants = [f"MERCH_{np.random.randint(1, 15):03d}" for _ in range(4)]

        # Generate transaction history
        history = []
        start_time = datetime(2024, 1, 1)

        for t in range(n_transactions_per_agent):
            # Time of transaction
            day_offset = float(np.random.exponential(scale=1/txn_per_day) if txn_per_day > 0 else 1)
            hour = int(np.random.choice(preferred_hours))
            minute = int(np.random.randint(0, 60))
            txn_time = start_time + timedelta(days=day_offset, hours=hour, minutes=minute)

            # Amount
            amount = max(1, np.random.normal(base_amount, amount_std))

            # Merchant (mostly known, occasionally new)
            if np.random.random() < 0.9 and merchants:
                merchant = np.random.choice(merchants)
                merchant_novelty = 0.0
            else:
                merchant = f"MERCH_NEW_{np.random.randint(1000, 9999)}"
                merchant_novelty = 1.0

            # Build features using preceding history
            preceding = history
            amounts_hist = [h["amount_usd"] for h in preceding]
            unique_merchants_hist = set(h["merchant"] for h in preceding)

            mean_amt = np.mean(amounts_hist) if amounts_hist else base_amount
            std_amt = np.std(amounts_hist) if len(amounts_hist) > 1 else amount_std
            zscore = (amount - mean_amt) / std_amt if std_amt > 0 else 0.0

            # Velocity
            cutoff_1h = txn_time - timedelta(hours=1)
            cutoff_24h = txn_time - timedelta(hours=24)
            cutoff_7d = txn_time - timedelta(days=7)

            txn_1h = sum(1 for h in preceding if h["time"] >= cutoff_1h)
            txn_24h = sum(1 for h in preceding if h["time"] >= cutoff_24h)
            txn_7d = sum(1 for h in preceding if h["time"] >= cutoff_7d)

            recent_7d_amt = [h["amount_usd"] for h in preceding if h["time"] >= cutoff_7d]
            avg_7d = np.mean(recent_7d_amt) if recent_7d_amt else amount
            std_7d = np.std(recent_7d_amt) if len(recent_7d_amt) > 1 else std_amt
            unique_7d = len(set(h["merchant"] for h in preceding if h["time"] >= cutoff_7d))

            # Time since last
            last_time = preceding[-1]["time"] if preceding else txn_time
            time_gap = (txn_time - last_time).total_seconds() / 3600

            features = {
                "amount_zscore": np.clip(zscore, -10, 10),
                "amount_log": np.log1p(amount),
                "txn_count_1h": txn_1h,
                "txn_count_24h": txn_24h,
                "txn_count_7d": txn_7d,
                "avg_amount_7d": avg_7d,
                "std_amount_7d": std_7d,
                "unique_merchants_7d": unique_7d,
                "merchant_novelty": merchant_novelty,
                "time_since_last_txn_h": np.clip(time_gap, 0, 168),
                "hour_of_day": float(txn_time.hour),
                "day_of_week": float(txn_time.weekday()),
            }

            # Label: 1 if anomalous (injected anomalies), 0 otherwise
            is_anomaly = 0

            feature_rows.append(features)
            labels.append(is_anomaly)

            # Add to history
            history.append({
                "amount_usd": amount,
                "merchant": merchant,
                "time": txn_time,
            })

        # Inject some anomalous transactions for this agent (after building history)
        if np.random.random() < 0.3:  # 30% of agents get anomalies
            n_anomalies = np.random.randint(1, 4)
            for _ in range(n_anomalies):
                # Anomalous transaction
                anomaly_type = np.random.choice([
                    "large_amount", "high_velocity", "new_merchant", "odd_hour"
                ])

                if anomaly_type == "large_amount":
                    amount = base_amount * np.random.uniform(10, 50)  # 10-50x normal
                    txn_1h = 0
                    hour = np.random.choice(preferred_hours)
                elif anomaly_type == "high_velocity":
                    amount = base_amount * np.random.uniform(0.5, 2)
                    txn_1h = np.random.randint(10, 30)  # Very high velocity
                    hour = np.random.choice(preferred_hours)
                elif anomaly_type == "new_merchant":
                    amount = base_amount * np.random.uniform(0.5, 3)
                    txn_1h = 0
                    hour = np.random.choice(preferred_hours)
                    merchant_novelty = 1.0
                else:  # odd_hour
                    amount = base_amount * np.random.uniform(0.5, 3)
                    txn_1h = 0
                    hour = np.random.choice([h for h in range(24) if h not in preferred_hours])

                # Build features for anomaly
                amounts_hist = [h["amount_usd"] for h in history]
                mean_amt = np.mean(amounts_hist) if amounts_hist else base_amount
                std_amt = np.std(amounts_hist) if len(amounts_hist) > 1 else amount_std
                zscore = (amount - mean_amt) / std_amt if std_amt > 0 else 0.0

                recent_7d_amt = amounts_hist[-20:]  # Last 20
                avg_7d = np.mean(recent_7d_amt) if recent_7d_amt else amount
                std_7d = np.std(recent_7d_amt) if len(recent_7d_amt) > 1 else std_amt
                unique_7d = len(set(h["merchant"] for h in history[-20:]))

                features = {
                    "amount_zscore": np.clip(zscore, -10, 10),
                    "amount_log": np.log1p(amount),
                    "txn_count_1h": txn_1h,
                    "txn_count_24h": len(history),
                    "txn_count_7d": len(history),
                    "avg_amount_7d": avg_7d,
                    "std_amount_7d": std_7d,
                    "unique_merchants_7d": unique_7d,
                    "merchant_novelty": 1.0 if anomaly_type == "new_merchant" else 0.0,
                    "time_since_last_txn_h": 0.5,
                    "hour_of_day": float(hour),
                    "day_of_week": float(np.random.randint(0, 7)),
                }

                feature_rows.append(features)
                labels.append(1)  # Anomaly

    return feature_rows, labels


def train_model(feature_rows, labels=None):
    """Train Isolation Forest model and scaler."""
    print(f"Training on {len(feature_rows)} samples...")

    # Convert to numpy array
    X = np.array([[row[name] for name in FEATURE_NAMES] for row in feature_rows])

    # Train scaler
    print("Training scaler...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train Isolation Forest
    print("Training Isolation Forest...")
    model = IsolationForest(**IF_PARAMS)
    model.fit(X_scaled)

    # Evaluate on training data
    scores = model.decision_function(X_scaled)
    predictions = model.predict(X_scaled)  # -1 = anomaly, 1 = normal

    print(f"\nTraining evaluation:")
    print(f"  Decision function range: [{scores.min():.4f}, {scores.max():.4f}]")
    print(f"  Mean score: {scores.mean():.4f}")
    print(f"  Predicted anomalies: {(predictions == -1).sum()} / {len(predictions)} ({(predictions == -1).mean()*100:.1f}%)")

    if labels is not None:
        labels = np.array(labels)
        true_anomalies = (labels == 1).sum()
        print(f"  True anomalies in data: {true_anomalies} / {len(labels)} ({true_anomalies/len(labels)*100:.1f}%)")

        # Precision/recall on injected anomalies
        pred_anomalies = (predictions == -1)
        tp = ((pred_anomalies) & (labels == 1)).sum()
        fp = ((pred_anomalies) & (labels == 0)).sum()
        fn = ((~pred_anomalies) & (labels == 1)).sum()
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        print(f"  Precision on injected anomalies: {precision:.2f}")
        print(f"  Recall on injected anomalies: {recall:.2f}")

    return model, scaler


def save_model(model, scaler):
    """Save trained model and scaler."""
    with open(ISOLATION_FOREST_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
    print(f"\nSaved model to {ISOLATION_FOREST_PATH}")
    print(f"Saved scaler to {SCALER_PATH}")


def test_model_loading():
    """Test that model loads correctly."""
    print("\nTesting model loading...")
    with open(ISOLATION_FOREST_PATH, "rb") as f:
        model = pickle.load(f)
    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)

    # Test prediction
    test_features = {
        "amount_zscore": 0.0,
        "amount_log": np.log1p(100),
        "txn_count_1h": 2,
        "txn_count_24h": 10,
        "txn_count_7d": 50,
        "avg_amount_7d": 100,
        "std_amount_7d": 30,
        "unique_merchants_7d": 3,
        "merchant_novelty": 0.0,
        "time_since_last_txn_h": 5.0,
        "hour_of_day": 14.0,
        "day_of_week": 2.0,
    }

    X = np.array([[test_features[name] for name in FEATURE_NAMES]])
    X_scaled = scaler.transform(X)
    score = model.decision_function(X_scaled)[0]
    pred = model.predict(X_scaled)[0]

    # Convert to risk score (same as anomaly_detection.py)
    risk_score = float(np.clip(50 - score * 100, 0, 100))

    print(f"  Test prediction:")
    print(f"    Decision function: {score:.4f}")
    print(f"    Prediction: {'anomaly' if pred == -1 else 'normal'}")
    print(f"    Risk score: {risk_score:.1f}")

    return True


def main():
    print("=" * 60)
    print("Training Isolation Forest Model for AgentGuard")
    print("=" * 60)

    # Generate synthetic data
    print("\nGenerating synthetic transaction data...")
    feature_rows, labels = generate_synthetic_data(
        n_agents=200,
        n_transactions_per_agent=50,
        seed=42
    )

    # Train model
    model, scaler = train_model(feature_rows, labels)

    # Save model
    save_model(model, scaler)

    # Test loading
    test_model_loading()

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()