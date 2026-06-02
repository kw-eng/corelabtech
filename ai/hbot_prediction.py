#Jak organizm zareaguje na HBOT
#SpO2 after session 
#HRV change
#adaptation curve
from sklearn.linear_model import LinearRegression

def train_model(rows):

    X=[]
    y=[]

    for r in rows:

     X.append([r[1],r[2],r[4],r[5]])

     y.append(r[3])

    model=LinearRegression()

    model.fit(X,y)

    return model
# hbot_prediction.py
# Funkcja predykcji hipoksji dla HBOT (Hyperbaric Oxygen Therapy)

def predict_hypoxia(input_data=None):

   """ Simulated hypoxia prediction.
 input_data: optional dictionary with patient telemetry
 Returns dictionary with prediction and risk score """
# przykład statyczny / symulacja
   result = {
"prediction": "normal",
"risk_score": 0.05
}
   return result

def predict_hbot_response(spo2, pulse, hrv, temperature):

   score = 0

   if spo2 > 95:
    score += 1

   if pulse < 80:
    score += 1

   if hrv > 40:
    score += 1

   if temperature < 37.5:
    score += 1

   if score >= 3:
    prediction = "Good HBOT adaptation expected"
   else:
    prediction = "Moderate physiological stress possible"

   return {
         "score": score,
         "prediction": prediction
   }