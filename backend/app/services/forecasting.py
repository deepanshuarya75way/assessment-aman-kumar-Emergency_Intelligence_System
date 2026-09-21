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

  def get_latest(self):
    return self.latest_forecasts
  
forecasting_service = ForecastingService()

