#symuluje live telemetry (Mission Control)

import random

def get_live_data():

    data = {

        "pressure": round(random.uniform(1.3, 1.5), 2),

        "oxygen": round(random.uniform(30, 40), 1),

        "spo2": random.randint(96, 100),

        "pulse": random.randint(60, 90),

         "hrv": random.randint(40, 90),

         "temperature": round(random.uniform(36.3, 36.8), 1)

    }

    return data