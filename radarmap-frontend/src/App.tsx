import { useState, useEffect } from 'react';
import { MapContainer, TileLayer } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import 'bootstrap/dist/css/bootstrap.min.css';
import './styles.css';
import Legend from './Legend';

interface Stats {
  files_downloaded: number;
  total_mb_downloaded: number;
  cache_hits: number;
  cache_misses: number;
}

function App() {
  const [product, setProduct] = useState<string>("RQ"); // "RQ" or "RE"
  
  const [allTimestamps, setAllTimestamps] = useState<string[]>([]);
  const [baseTimestamps, setBaseTimestamps] = useState<string[]>([]);
  const [availableLeadTimes, setAvailableLeadTimes] = useState<number[]>([]);
  
  const [selectedTimestampIndex, setSelectedTimestampIndex] = useState<number>(0);
  const [leadTimeIndex, setLeadTimeIndex] = useState<number>(0);
  
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [maxDataValue, setMaxDataValue] = useState<number | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    const fetchTimestamps = async () => {
      setLoading(true);
      try {
        const response = await fetch(`http://localhost:8000/api/radvor/timestamps?product=${product}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data: string[] = await response.json();
        
        const uniqueBaseTimestamps = [...new Set(data.map(ts => ts.split('_')[0]))].sort();
        setAllTimestamps(data);
        setBaseTimestamps(uniqueBaseTimestamps);
        
        if (uniqueBaseTimestamps.length > 0) {
          setSelectedTimestampIndex(uniqueBaseTimestamps.length - 1);
        }
        setLeadTimeIndex(0); // Reset lead time on product change
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchTimestamps();
  }, [product]);

  const baseTimestamp = baseTimestamps[selectedTimestampIndex];

  useEffect(() => {
    if (!baseTimestamp) return;
    const leads = allTimestamps
      .filter(ts => ts.startsWith(baseTimestamp))
      .map(ts => parseInt(ts.split('_')[1], 10))
      .sort((a, b) => a - b);
    setAvailableLeadTimes(leads);
    // Ensure leadTimeIndex is valid for new leads list
    if (leadTimeIndex >= leads.length) {
        setLeadTimeIndex(0);
    }
  }, [baseTimestamp, allTimestamps, leadTimeIndex]); // Added leadTimeIndex dependency check logic inside but simplified dep array
  
  const selectedLeadTime = availableLeadTimes[leadTimeIndex];
  const fullTimestampForApi = baseTimestamp && (selectedLeadTime !== undefined)
    ? `${baseTimestamp}_${String(selectedLeadTime).padStart(3, '0')}`
    : null;

  useEffect(() => {
    if (!fullTimestampForApi) return;
    
    setMaxDataValue(null);
    const fetchMaxValue = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/radvor/max-value?timestamp=${fullTimestampForApi}&product=${product}`);
        if(response.ok) {
          const data = await response.json();
          setMaxDataValue(data.max_value);
        } else {
          setMaxDataValue(NaN);
        }
      } catch (e) {
        console.error("Failed to fetch max value:", e);
        setMaxDataValue(NaN);
      }
    };

    const fetchStats = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/stats');
        if (response.ok) {
          const data = await response.json();
          setStats(data);
        }
      } catch(e) {
        console.error("Failed to fetch stats:", e)
      }
    };

    fetchMaxValue();
    fetchStats();
  }, [fullTimestampForApi, product]);
  
  const formattedTimestamp = baseTimestamp
    ? `20${baseTimestamp.substring(0, 2)}-${baseTimestamp.substring(2, 4)}-${baseTimestamp.substring(4, 6)} ${baseTimestamp.substring(6, 8)}:${baseTimestamp.substring(8, 10)}`
    : 'N/A';

  if (loading && allTimestamps.length === 0) {
    return <div className="loading-container">Loading available timestamps...</div>;
  }
  if (error && allTimestamps.length === 0) {
    return <div className="alert alert-danger">{error}</div>;
  }

  return (
    <div className="App">
      <MapContainer center={[51.0, 10.0]} zoom={6} style={{ height: '100vh', width: '100%' }}>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
        />
        {fullTimestampForApi && (
          <TileLayer
            key={`${product}_${fullTimestampForApi}`}
            url={`http://localhost:8000/api/tiles/{z}/{x}/{y}.png?timestamp=${fullTimestampForApi}&product=${product}`}
            attribution='RADVOR Data &copy; DWD'
            opacity={0.8}
            zIndex={1000}
          />
        )}
      </MapContainer>
      
      <div className="map-overlay legend-container">
        <Legend product={product} />
      </div>

      <div className="map-overlay debug-info">
        <p className="mb-0">Max Value: {maxDataValue === null ? '...' : (isNaN(maxDataValue) ? 'Error' : `${maxDataValue.toFixed(2)} ${product === 'RQ' ? 'mm/h' : '%'}`)}</p>
        {stats && <p className="mb-0">DLs: {stats.files_downloaded} ({stats.total_mb_downloaded.toFixed(2)} MB) | Hits: {stats.cache_hits}</p>}
      </div>

      <div className="map-overlay time-slider-container">
        <div className="mb-3">
            <div className="btn-group w-100" role="group" aria-label="Product Selection">
                <input 
                    type="radio" 
                    className="btn-check" 
                    name="product" 
                    id="product-rq" 
                    autoComplete="off" 
                    checked={product === "RQ"} 
                    onChange={() => setProduct("RQ")}
                />
                <label className="btn btn-outline-primary" htmlFor="product-rq">Intensity (RQ)</label>

                <input 
                    type="radio" 
                    className="btn-check" 
                    name="product" 
                    id="product-re" 
                    autoComplete="off" 
                    checked={product === "RE"} 
                    onChange={() => setProduct("RE")}
                />
                <label className="btn btn-outline-primary" htmlFor="product-re">Type (RE)</label>
            </div>
        </div>

        <div className='w-75'>
          <label htmlFor="time-slider" className="form-label mb-1">
            Forecast Run: <strong>{formattedTimestamp} UTC</strong>
          </label>
          <input
            type="range"
            className="form-range"
            id="time-slider"
            min="0"
            max={baseTimestamps.length > 0 ? baseTimestamps.length - 1 : 0}
            value={selectedTimestampIndex}
            onChange={(e) => setSelectedTimestampIndex(parseInt(e.target.value, 10))}
            disabled={baseTimestamps.length === 0}
          />
        </div>
        <div className='w-75 mt-2'>
          <label htmlFor="lead-time-slider" className="form-label mb-1">
            Lead Time: <strong>+{selectedLeadTime} minutes</strong>
          </label>
          <input
            type="range"
            className="form-range"
            id="lead-time-slider"
            min="0"
            max={availableLeadTimes.length > 0 ? availableLeadTimes.length - 1 : 0}
            value={leadTimeIndex}
            onChange={(e) => setLeadTimeIndex(parseInt(e.target.value, 10))}
            disabled={availableLeadTimes.length === 0}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
