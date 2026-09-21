"""
ML Pipeline — YOLOv8 person detection + grid-based density estimation.

The model is loaded lazily on the first call to avoid blocking FastAPI startup.
"""
import cv2
import numpy as np
from typing import Tuple, Dict, List, Any, Optional
from app.core.config import settings
from app.services.forecasting import forecasting_service
from app.services.storage import storage_service


class MLPipeline:
    def __init__(self):
        self._model = None
        self.grid_rows = settings.GRID_ROWS
        self.grid_cols = settings.GRID_COLS

    # ── lazy model load ──
    def _load_model(self):
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(settings.YOLO_MODEL_PATH)

    # ── public API ──
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, int], List[Dict[str, Any]]]:
        """
        Returns (annotated_frame, zone_densities, alerts)
        """
        self._load_model()

        h, w = frame.shape[:2]
        cell_h = h / self.grid_rows
        cell_w = w / self.grid_cols

        # Run YOLO — class 0 = person
        results = self._model(frame, classes=[0], conf=settings.YOLO_CONFIDENCE, verbose=False)

        # Init zone map
        zone_densities: Dict[str, int] = {}
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                zone_densities[f"Zone_{r}_{c}"] = 0

        annotated = frame.copy()
        total_people = 0

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                conf = float(box.conf[0])

                row = min(int(cy / cell_h), self.grid_rows - 1)
                col = min(int(cx / cell_w), self.grid_cols - 1)
                zone_densities[f"Zone_{row}_{col}"] += 1
                total_people += 1

                # Draw bounding box
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.circle(annotated, (cx, cy), 4, (0, 0, 255), -1)
                cv2.putText(annotated, f"{conf:.0%}", (x1, y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        # Draw grid overlay
        for r in range(1, self.grid_rows):
            y = int(r * cell_h)
            cv2.line(annotated, (0, y), (w, y), (255, 255, 255), 1)
        for c in range(1, self.grid_cols):
            x = int(c * cell_w)
            cv2.line(annotated, (x, 0), (x, h), (255, 255, 255), 1)

        # Zone labels
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                zone = f"Zone_{r}_{c}"
                count = zone_densities[zone]
                tx = int(c * cell_w) + 8
                ty = int(r * cell_h) + 24

                # Color by density
                if count >= settings.DENSITY_CRITICAL:
                    color = (0, 0, 255)
                elif count >= settings.DENSITY_WARNING:
                    color = (0, 165, 255)
                else:
                    color = (0, 255, 0)

                cv2.putText(annotated, f"{zone}: {count}", (tx, ty),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)

        # Total people counter
        cv2.putText(annotated, f"Total: {total_people}", (w - 150, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Decision engine
        from app.services.decision_engine import decision_engine
        alerts = decision_engine.analyze(zone_densities)

        forecasts = forecasting_service.update(zone_densities)

        predictive_alerts = decision_engine.analyze_forecasts(
            forecasts
        )

        alerts.extend(predictive_alerts)

        return annotated, zone_densities, alerts

    def detect_single(self, frame: np.ndarray) -> Dict[str, Any]:
        """Run detection on a single frame and return JSON-friendly results."""
        annotated, densities, alerts = self.process_frame(frame)
        forecasts = forecasting_service.get_latest()
        # await storage_service.save_density(densities)
        # await storage_service.save_forecast(forecasts)
        _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        import base64
        b64 = base64.b64encode(buf).decode('utf-8')
        return {
            "total_people": sum(densities.values()),
            "zone_densities": densities,
            "alerts": alerts,
            "forecasts": forecasts,
            "annotated_frame_b64": b64,
        }


ml_pipeline = MLPipeline()
