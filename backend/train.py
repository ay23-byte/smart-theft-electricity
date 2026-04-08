import os

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = [
    "avg_daily_consumption",
    "max_daily_consumption",
    "consumption_variance",
    "usage_intensity",
]
LABEL_COLUMN = "theft_label"
DEFAULT_THRESHOLD = 0.35
EXCLUDED_FEATURE_COLUMNS = {"FLAG", "CONS_NO", "THEFT_LABEL", "LABEL", "ID"}


def get_base_dir(base_dir=None):
    return base_dir or os.path.dirname(os.path.abspath(__file__))


def build_feature_row(avg_daily_consumption, max_daily_consumption, consumption_variance):
    avg_val = float(avg_daily_consumption)
    max_val = float(max_daily_consumption)
    variance_val = float(consumption_variance)
    usage_intensity = max_val / (avg_val + 0.1)
    return {
        "avg_daily_consumption": avg_val,
        "max_daily_consumption": max_val,
        "consumption_variance": variance_val,
        "usage_intensity": usage_intensity,
    }


def build_inference_features(avg_daily_consumption, max_daily_consumption, consumption_variance):
    return pd.DataFrame(
        [build_feature_row(avg_daily_consumption, max_daily_consumption, consumption_variance)],
        columns=FEATURE_COLUMNS,
    )


def engineer_features(df, is_daily_data=True):
    new_df = pd.DataFrame()
    if is_daily_data:
        cols = [c for c in df.columns if c.upper() not in EXCLUDED_FEATURE_COLUMNS]
        new_df["avg_daily_consumption"] = df[cols].mean(axis=1)
        new_df["max_daily_consumption"] = df[cols].max(axis=1)
        new_df["consumption_variance"] = df[cols].var(axis=1)
        label_col = next((c for c in df.columns if c.upper() in ["FLAG", "THEFT_LABEL", "LABEL"]), None)
        new_df[LABEL_COLUMN] = df[label_col] if label_col else 0
    else:
        def find_col(keys):
            return next((c for c in df.columns if any(k in c.lower() for k in keys)), None)

        avg = find_col(["avg", "mean"])
        peak = find_col(["max", "peak"])
        var = find_col(["var", "std"])
        target = find_col(["label", "flag", "theft"])
        new_df["avg_daily_consumption"] = df[avg] if avg else 0
        new_df["max_daily_consumption"] = df[peak] if peak else 0
        new_df["consumption_variance"] = df[var] if var else 0
        new_df[LABEL_COLUMN] = df[target] if target else 0

    new_df["usage_intensity"] = new_df["max_daily_consumption"] / (new_df["avg_daily_consumption"] + 0.1)
    return new_df


def clean_wide_meter_dataset(df):
    cleaned = df.copy()
    cleaned.columns = [str(column).strip() for column in cleaned.columns]

    if "CONS_NO" in cleaned.columns:
        cleaned["CONS_NO"] = cleaned["CONS_NO"].astype(str).str.strip()

    if "FLAG" in cleaned.columns:
        cleaned["FLAG"] = pd.to_numeric(cleaned["FLAG"], errors="coerce").fillna(0).astype(int)

    reading_columns = [c for c in cleaned.columns if c.upper() not in EXCLUDED_FEATURE_COLUMNS]
    for column in reading_columns:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    if "CONS_NO" in cleaned.columns:
        cleaned = cleaned.drop_duplicates(subset=["CONS_NO"], keep="first")

    cleaned = cleaned.dropna(subset=reading_columns, how="all")
    return cleaned


def load_training_dataset(base_dir=None):
    base_dir = get_base_dir(base_dir)
    df1 = pd.read_csv(os.path.join(base_dir, "cleaned_electricity_theft_data.csv"))
    df2 = pd.read_csv(os.path.join(base_dir, "cleaned_datasetsmall.csv"))
    df3 = pd.read_csv(os.path.join(base_dir, "electric_2.csv"))
    data_csv_path = os.path.join(base_dir, "data.csv")
    cleaned_data_csv_path = os.path.join(base_dir, "cleaned_data.csv")
    df4 = None
    if os.path.exists(data_csv_path):
        df4 = clean_wide_meter_dataset(pd.read_csv(data_csv_path))
        df4.to_csv(cleaned_data_csv_path, index=False)
        print("DONE: Saved 'cleaned_data.csv'")
    elif os.path.exists(cleaned_data_csv_path):
        df4 = pd.read_csv(cleaned_data_csv_path)
    return pd.concat(
        [
            engineer_features(df1, is_daily_data=False),
            engineer_features(df2, is_daily_data=True),
            engineer_features(df3, is_daily_data=True),
            engineer_features(df4, is_daily_data=True) if df4 is not None else pd.DataFrame(),
        ],
        ignore_index=True,
    ).fillna(0)


def train_and_save_model(base_dir=None):
    base_dir = get_base_dir(base_dir)
    print("--- Step 1: Loading and Aligning All 3 Datasets ---")

    df_comb = load_training_dataset(base_dir)
    print(f"Total Combined Dataset Size: {len(df_comb)} households.")

    X = df_comb[FEATURE_COLUMNS]
    y = df_comb[LABEL_COLUMN]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print("Balancing classes (SMOTE)...")
    smote = SMOTE(random_state=42)
    X_res, y_res = smote.fit_resample(X_train, y_train)

    scaler = StandardScaler()
    X_res_scaled = scaler.fit_transform(X_res)
    X_test_scaled = scaler.transform(X_test)

    print("Training Intelligent Random Forest...")
    model = RandomForestClassifier(n_estimators=300, max_depth=15, random_state=42)
    model.fit(X_res_scaled, y_res)

    model_path = os.path.join(base_dir, "smart_theft_model.pkl")
    scaler_path = os.path.join(base_dir, "scaler.pkl")
    report_image_path = os.path.join(base_dir, "model_performance.png")
    suspects_path = os.path.join(base_dir, "field_inspection_list.csv")

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    print("DONE: Saved 'smart_theft_model.pkl' and 'scaler.pkl'")

    y_probs = model.predict_proba(X_test_scaled)[:, 1]
    y_pred = (y_probs > DEFAULT_THRESHOLD).astype(int)
    plt.figure(figsize=(8, 6))
    sns.heatmap(confusion_matrix(y_test, y_pred), annot=True, fmt="d", cmap="Blues")
    plt.title("Theft Detection Confusion Matrix (Recall Proof)")
    plt.savefig(report_image_path)
    plt.close()
    print("DONE: Saved 'model_performance.png'")

    all_probs = model.predict_proba(scaler.transform(X))[:, 1]
    df_comb["Theft_Probability"] = all_probs
    suspects = df_comb[df_comb["Theft_Probability"] > 0.5].sort_values(
        by="Theft_Probability", ascending=False
    )
    suspects.to_csv(suspects_path, index=False)
    print("DONE: Saved 'field_inspection_list.csv'")

    print("\n========== FINAL RESULTS ==========")
    print(classification_report(y_test, y_pred))

    return {
        "model": model,
        "scaler": scaler,
        "dataset_size": len(df_comb),
        "model_path": model_path,
        "scaler_path": scaler_path,
        "report_image_path": report_image_path,
        "suspects_path": suspects_path,
    }


def load_trained_artifacts(base_dir=None):
    base_dir = get_base_dir(base_dir)
    model_path = os.path.join(base_dir, "smart_theft_model.pkl")
    scaler_path = os.path.join(base_dir, "scaler.pkl")
    return joblib.load(model_path), joblib.load(scaler_path)


if __name__ == "__main__":
    try:
        train_and_save_model()
    except Exception as e:
        print(f"Error: {e}")
