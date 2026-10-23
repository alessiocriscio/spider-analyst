import random, math
from datetime import date, timedelta
def series(days=3000, start=date(2018,3,15), p=10000.0, vol=0.035, seed=1, weekends=True):
    random.seed(seed); out=[]; d=start
    for i in range(days):
        if weekends or d.weekday()<5:
            p*=math.exp(random.gauss(0.0007,vol)); out.append((d.isoformat(),p))
        d+=timedelta(1)
    return {"symbol":"TEST-USD","name":"Moneta di prova","currency":"USD","type":"CRYPTOCURRENCY","exchange":"Test","points":out}
