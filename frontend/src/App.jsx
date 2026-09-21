import { useState, useEffect, useRef } from 'react';
import VideoStream from './components/VideoStream';
import AlertPanel from './components/AlertPanel';
import HeatmapGrid from './components/HeatmapGrid';
import SystemStatus from './components/SystemStatus';
import ControlPanel from './components/ControlPanel';
import StatsBar from './components/StatsBar';
import InputSelector from './components/InputSelector';
import { fetchStatus, fetchAlerts, createWebSocket } from './services/api';
import ForecastPanel from "./components/ForecastPanel";

function App() {
  const [status, setStatus] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [densities, setDensities] = useState({});
  const [wsConnected, setWsConnected] = useState(false);
  const [clock, setClock] = useState('');
  const [systemLevel, setSystemLevel] = useState('normal');
  const [forecasts, setForecasts] = useState({});
  const wsRef = useRef(null);

  // Clock
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock(now.toLocaleTimeString('en-US', { hour12: false }) + ' ' +
        now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  // Fetch status on mount
  useEffect(() => {
    const poll = async () => {
      try {
        const s = await fetchStatus();
        setStatus(s);
      } catch (e) {
        setStatus(null);
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const fetchForecasts = async () => {
      try{
        const response = await fetch(
          "http://localhost:8000/forecasts"
        );

        const data = await response.json();
        setForecasts(
          data.forecasts || {}
        );
      }
      catch(error){
        console.error("Failed to fetch forecasts:",error);
      }
    };
    fetchForecasts();
    const interval = setInterval(
      fetchForecasts,
      5000
    );
    return () => clearInterval(interval);
  }, []);

  // Fetch initial alerts
  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchAlerts();
        setAlerts(data.alerts || []);
      } catch (e) { /* ignore */ }
    };
    load();
  }, []);

  // WebSocket
  useEffect(() => {
    wsRef.current = createWebSocket(
      (msg) => {
        if (msg.type === 'alerts' && msg.data) {
          setAlerts((prev) => {
            const combined = [...msg.data, ...prev];
            // Deduplicate by id, keep latest 100
            const seen = new Set();
            const deduped = [];
            for (const a of combined) {
              if (!seen.has(a.id)) {
                seen.add(a.id);
                deduped.push(a);
              }
            }
            return deduped.slice(0, 100);
          });
        }
        if (msg.type === 'heatmap' && msg.data) {
          setDensities(msg.data);
        }
      },
      () => setWsConnected(true),
      () => setWsConnected(false),
    );
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Determine system level based on alerts
  useEffect(() => {
    const hasCritical = alerts.some((a) => a.level === 'critical');
    const hasWarning = alerts.some((a) => a.level === 'warning');
    if (hasCritical) setSystemLevel('critical');
    else if (hasWarning) setSystemLevel('warning');
    else setSystemLevel('normal');
  }, [alerts]);

  const handleSimulate = (data) => {
    if (data.zone_densities) setDensities(data.zone_densities);
    if (data.alerts) {
      setAlerts((prev) => [...data.alerts, ...prev].slice(0, 100));
    }
  };

  // Handler for InputSelector results (image detect or video process)
  const handleInputResult = (result) => {
    if (result.zone_densities) setDensities(result.zone_densities);
    if (result.peak_density) setDensities(result.peak_density);
    if (result.alerts && result.alerts.length > 0) {
      setAlerts((prev) => [...result.alerts, ...prev].slice(0, 100));
    }
  };

  return (
    <div className="app-wrapper">
      {/* ── Top Bar ── */}
      <header className="top-bar">
        <div className="top-bar-left">
          <div className="top-bar-logo">E</div>
          <div>
            <div className="top-bar-title">Emergency Intelligence System</div>
            <div className="top-bar-subtitle">Real-time Crowd Monitoring</div>
          </div>
        </div>
        <div className="top-bar-right">
          <SystemStatus status={status} wsConnected={wsConnected} />
          <div className="top-bar-clock">{clock}</div>
        </div>
      </header>

      {/* ── Main Dashboard ── */}
      <main className="main-content">
        {/* Stats Bar (full width) */}
        <StatsBar
          densities={densities}
          alertCount={alerts.filter(a => a.level === 'critical' || a.level === 'warning').length}
          wsConnected={wsConnected}
          videoSource={status?.services?.video_source || 'mock'}
        />


        {/* Left Column: Input Selector + Video + Heatmap */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <InputSelector onResult={handleInputResult} />
          <VideoStream />
          <HeatmapGrid densities={densities} />
        </div>

      <ForecastPanel forecasts={forecasts} />
        {/* Right Column: Alerts + Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <AlertPanel alerts={alerts} />
          <ControlPanel onSimulate={handleSimulate} />
        </div>
      </main>
    </div>
  );
}

export default App;
