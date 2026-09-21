"""
Storage service — MongoDB Atlas for persistence, Upstash Redis for real-time cache.

Falls back to in-memory stores when cloud credentials are not configured,
so the prototype works out-of-the-box without any external services.
"""
import json
import time
from typing import Dict, Any, List, Optional
from app.core.config import settings


class StorageService:
    def __init__(self):
        self.mongo_client = None
        self.db = None
        self.redis_client = None

        # In-memory fallbacks
        self._mem_alerts: List[Dict[str, Any]] = []
        self._mem_heatmap: Optional[Dict[str, Any]] = None
        self._mem_events: List[Dict[str, Any]] = []

        self._mem_density_history = []
        self._mem_forecasts = []

        self._init_mongo()
        self._init_redis()

    # ── MongoDB ──
    def _init_mongo(self):
        if settings.MONGODB_URI:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                self.mongo_client = AsyncIOMotorClient(settings.MONGODB_URI)
                self.db = self.mongo_client[settings.MONGODB_DB_NAME]
                print("[Storage] MongoDB Atlas connected")
            except Exception as e:
                print(f"[Storage] MongoDB connection failed, using in-memory: {e}")

    # ── Redis ──
    def _init_redis(self):
        if settings.UPSTASH_REDIS_REST_URL:
            try:
                import redis.asyncio as aioredis
                self.redis_client = aioredis.Redis.from_url(
                    settings.UPSTASH_REDIS_REST_URL, decode_responses=True
                )
                print("[Storage] Upstash Redis connected")
            except Exception as e:
                print(f"[Storage] Redis connection failed, using in-memory: {e}")

    # ── Alerts ──
    async def save_alert(self, alert: Dict[str, Any]):
        if self.db is not None:
            await self.db["alerts"].insert_one({**alert, "_persisted": time.time()})
        else:
            self._mem_alerts.append(alert)
            # Keep only last 200
            if len(self._mem_alerts) > 200:
                self._mem_alerts = self._mem_alerts[-200:]

    async def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.db is not None:
            cursor = self.db["alerts"].find(
                {}, {"_id": 0}
            ).sort("timestamp", -1).limit(limit)
            return await cursor.to_list(length=limit)
        return list(reversed(self._mem_alerts))[:limit]

    # ── Heatmap cache ──
    async def cache_heatmap(self, heatmap: Dict[str, Any]):
        if self.redis_client is not None:
            try:
                await self.redis_client.set("eis:latest_heatmap", json.dumps(heatmap), ex=60)
                return
            except Exception:
                pass
        self._mem_heatmap = heatmap

    async def get_cached_heatmap(self) -> Optional[Dict[str, Any]]:
        if self.redis_client is not None:
            try:
                data = await self.redis_client.get("eis:latest_heatmap")
                if data:
                    return json.loads(data)
            except Exception:
                pass
        return self._mem_heatmap

    # ── System events ──
    async def log_event(self, event_type: str, details: str = ""):
        event = {"type": event_type, "details": details, "timestamp": time.time()}
        if self.db is not None:
            await self.db["events"].insert_one(event)
        else:
            self._mem_events.append(event)
            if len(self._mem_events) > 500:
                self._mem_events = self._mem_events[-500:]

    async def save_density(self,zone_densities: Dict[str,int]):

        timestamp = time.time()

        records = []

        for zone, density in zone_densities.items():
            records.append({
                "timestamp":timestamp,
                "zone":zone,
                "density":density
            })

        if self.db is not None:
            try:
                if records:
                    await self.db["density_history"].insert_many(
                        records
                    )

                return 

            except Exception as e:
                print(
                    f"[Storage] Density history save failed: {e}"
                )

        self._mem_density_history.extend(record)

        if len(self._mem_density_history) > 5000:
            self._mem_density_history= (
                self._mem_density_history[-5000:]
            )

    async def save_forecast(self, forecasts:Dict[str,Any]):

        record = {
            "timestamp": time.time(),
            "forecasts": forecasts
        }

        if self.db is not None:

            try:
                await self.db["forecast_history"].insert_one(record)
                return

            except Exception as e:
                print(f"[Storage] Forecast save failed: {e}")

        self._mem_forecasts.append(record)

        if len(self._mem_forecasts)>1000:
            self._mem_forecasts = (
                self._mem_forecasts[-1000:]
            )

    
    async def get_recent_forecasts(self, limit: int = 50):
        if self.db is None:
            try:
                cursor = (
                    self.db["forecast_history"]
                    .find({}, {"_id":0})
                    .sort("timestamp",-1)
                    .limit(limit)
                )

                return await cursor.to_list(length = limit)

            except Exception as e :
                print(f"[Storage] forecast failed: {e}")

        return list(reversed(self._mem_forecasts[-limit:]))

    # ── Health ──
    def health(self) -> Dict[str, str]:
        return {
            "mongodb": "connected" if self.db is not None else "in-memory",
            "redis": "connected" if self.redis_client is not None else "in-memory",
        }


storage_service = StorageService()
