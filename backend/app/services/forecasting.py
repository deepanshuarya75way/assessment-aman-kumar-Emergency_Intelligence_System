import time 
import math 
from collections import defaultdict, deque
from typing import Dict, Any, List

from app.core.config import settings


class ForecastingService:

  def __init__(self):

    # Zone
    self.history = defaultdict(
      lambda: deque(
        maxlen=settings.FORECAST_HISTORY_SIZE
      )
    )

    self.last_sample_time = {}

    # Latest forecast
    self.latest_forecasts = {}

  def update(self,zone_densities: Dict[str,int]) -> Dict[str,Any]:
    """
    Add latest zone densities and generate forecasts
    """

    now = time.time()

    for zone, density in zone_densities.items():

      last_time = self.last_sample_time.get(zone, 0)

      if now - last_time >= settings.FORECAST_SAMPLE_INTERVAL:
        self.history[zone].append(
          (now, float(density))
        )

        self.last_sample_time[zone] = now
    
    forecasts = {}

    for zone in zone_densities:
      history = list(self.history[zone])

      if len(history) < settings.FORECAST_MIN_SAMPLES:
        forecasts[zone] = {
          "zone" : zone,
          "current" : zone_densities[zone],
          "status" : "collecting" ,
          "samples" : len(history),
          "predictions":[]
        }

        continue
      
      forecast = self._forecast_zone(
        zone,
        history,
        zone_densities[zone]
      )

      forecasts[zone] = forecast

    self.latest_forecasts = forecasts

    return forecasts 

  def _forecast_zone(
    self,
    zone:str,
    history:list[float],
    current: int
  ) -> dict[str, Any]:

    # values = history[-20:]

    if not history:
      return{
        "zone":zone,
        "current":current,
        "status":"insufficient_data",
        "samples" : 0,
        "predictions": []
      }

    values = [
      float(item[1])
      for item in history[-20:]
    ]

    if not values:
      return {
        "zone":zone,
        "current":current,
        "status":"insufficient_data",
        "samples" : 0,
        "predictions": []
      }

    if len(values)>= 2:
      first = values[0]
      last = values[-1]
      trend = (last-first)/(len(values)-1)
    else:
      trend = 0.0

    predictions = []

    horizons = getattr(
      settings,
      "FORECAST_HORIZONS",
      [5,10, 15]
    )

    if len(values) >= 2:
        mean = sum(values) / len(values)
        variance = sum(
          (x-mean)**2 
          for x in values
        )/len(values)
        std = variance ** 0.5
      
    else:
      std = 0.0

    margin = max(std, 1.0)

    for horizon in horizons:
      predicted = max(
        0,
        float(values[-1]) + trend * horizon
      )

      
      lower = max(
        0.0,
        predicted - margin
      )

      upper = predicted + margin

      confidence = max(
        0.5,
        min(
          0.99,
          1.0 - (margin / max(predicted, 1.0))
        )
      )

      predictions.append({
        "horizon":horizon,
        "prediction": round(predicted,2),
        "lower": round(lower,2),
        "upper" : round(upper, 2),
        "confidence": round(confidence, 2)
      })

      return {
        "zone" : zone,
        "current": current,
        "status" : "forecasting",
        "samples" : len(history),
        "predictions" : predictions
      }

  def get_latest(self):
    return self.latest_forecasts
  
forecasting_service = ForecastingService()

