import react from "react";

export default function ForecastPanel ({forecasts = {}}){
  const zones = bject.values(forecasts);
  return(
    <div className = "forecast-panel">
      <h2> Predictive crowd forecast</h2>

      {zones.length ==0 && (
        <p classname = "forecast-empty">
          Collecting ....
          </p>
      )}

      {zones.map((zone) => (
        <div
          className = "forecast-zone"
          key = {zone.zone}
          >
            <div className= "forecast-header">
              <h3>{zone.zone}</h3>

              <span> Current: {zone.current} </span>

              </div>

              {zoe.status ==="collectinng_data" && (
                <p>
                  Collecting data:
                  {" "}
                  {zone.samples} samples
                  </p>
              )}

              {zone.predictions?.length > 0 && (
                <div className = "forecast-grid">
                  {zone.predictions.map(
                    (prediction) => (
                      <div className = "forecast-card"
                      key = {
                        prediction.minuted_ahead
                      }
                      >
                        <strong>
                          +
                          {
                            prediction.minutes_ahead
                          }
                          min 
                        </strong>

                        <div className = "forecast-value">
                          {
                            Math.round(
                              prediction.predicted
                            )
                          }
                          </div>

                          <div>
                            Range:
                            {" "}
                            {
                              Math.round(
                                prediction.lower
                              )
                            }
                            </div>

                            <div>
                              Confidence:
                              {" "}
                              {Math.round(
                                predicted.confidence*100
                              )}%
                              </div>
                            </div>

                    )
                  )}
                  </div>
              )}
              </div>

      ))}
      </div>
  );
}