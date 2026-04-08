
import joblib
import numpy as np
model = joblib.load('smart_theft_model.pkl')
scaler = joblib.load('scaler.pkl')
def check_new_user(avg, max_val, var):
    intensity = max_val / (avg + 0.1)
    features = np.array([[avg, max_val, var, intensity]])
    scaled = scaler.transform(features)
    prob = model.predict_proba(scaled)[0][1]
    return f"Theft Risk Score: {prob*100:.2f}%"

# Example: Checking a household with 1 unit avg but 20 unit spike
print(check_new_user(1.0, 20.0, 5.0))
