import React from 'react';

const legendDataRQ = [
  { color: 'rgba(0, 255, 0, 0.6)', label: '< 0.1' },
  { color: 'rgba(0, 200, 0, 0.7)', label: '0.1 - 1.0' },
  { color: 'rgba(0, 150, 0, 0.8)', label: '1.0 - 2.5' },
  { color: 'rgba(255, 255, 0, 0.8)', label: '2.5 - 5.0' },
  { color: 'rgba(255, 204, 0, 0.8)', label: '5.0 - 10.0' },
  { color: 'rgba(255, 102, 0, 0.9)', label: '10.0 - 25.0' },
  { color: 'rgba(255, 0, 0, 0.9)', label: '25.0 - 50.0' },
  { color: 'rgba(153, 0, 76, 1.0)', label: '>= 50.0' },
];

const legendDataRE = [
  { color: 'rgba(0, 0, 255, 0.6)', label: 'Liquid (Rain)' },
  { color: 'rgba(128, 128, 255, 0.7)', label: 'Mixed / Sleet' },
  { color: 'rgba(255, 255, 255, 0.8)', label: 'Solid (Snow)' },
  { color: 'rgba(255, 0, 255, 0.8)', label: 'Hail (Flag)' },
];

interface LegendProps {
  product: string;
}

const Legend: React.FC<LegendProps> = ({ product }) => {
  const isRE = product === 'RE';
  const data = isRE ? legendDataRE : legendDataRQ;
  const title = isRE ? 'Precipitation Type' : 'Precipitation (mm/h)';

  return (
    <div className="legend-container">
      <h6>{title}</h6>
      {data.map((item, index) => (
        <div key={index} className="d-flex align-items-center mb-1">
          <div style={{ backgroundColor: item.color, width: '20px', height: '20px', marginRight: '5px', border: '1px solid #ccc' }}></div>
          <span style={{ fontSize: '0.9rem' }}>{item.label}</span>
        </div>
      ))}
    </div>
  );
};

export default Legend;
