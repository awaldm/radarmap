import React from 'react';

interface TimeDisplayProps {
  formattedTimestamp: string;
}

const TimeDisplay: React.FC<TimeDisplayProps> = ({ formattedTimestamp }) => {
  return (
    <div className="time-display-container position-absolute top-0 start-50 translate-middle-x p-2 bg-light bg-opacity-75 rounded m-2">
      <h6>RADVOR Forecast Time: <strong>{formattedTimestamp} UTC</strong></h6>
    </div>
  );
};

export default TimeDisplay;
