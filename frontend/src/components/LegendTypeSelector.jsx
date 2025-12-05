import React, { useState } from 'react';

export default function LegendTypeSelector({ imageUrl, onConfirm, onCancel }) {
  const [legendType, setLegendType] = useState(null); // 'continuous' or 'binned'
  const [numBins, setNumBins] = useState('');
  const [minValue, setMinValue] = useState('');
  const [maxValue, setMaxValue] = useState('');

  const handleConfirm = () => {
    if (!legendType) {
      alert('Please select a legend type');
      return;
    }

    if (legendType === 'binned') {
      const bins = parseInt(numBins);
      if (isNaN(bins) || bins < 2 || bins > 20) {
        alert('Please enter a valid number of bins (2-20)');
        return;
      }
      onConfirm({
        type: 'binned',
        numBins: bins
      });
    } else if (legendType === 'continuous') {
      const min = parseFloat(minValue);
      const max = parseFloat(maxValue);
      if (isNaN(min) || isNaN(max) || min >= max) {
        alert('Please enter valid min and max values (min < max)');
        return;
      }
      onConfirm({
        type: 'continuous',
        minValue: min,
        maxValue: max
      });
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      width: '100vw',
      height: '100vh',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      overflow: 'auto'
    }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: '12px',
        padding: '32px',
        maxWidth: '900px',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
        maxHeight: '90vh',
        overflow: 'auto'
      }}>
        <h3 style={{
          margin: 0,
          color: '#333',
          fontSize: '24px',
          fontWeight: '600',
          textAlign: 'center'
        }}>
          Legend Type
        </h3>
        
        <p style={{
          margin: 0,
          color: '#666',
          fontSize: '14px',
          textAlign: 'center'
        }}>
          What type of legend does your map use?
        </p>

        {/* Display uploaded image */}
        {imageUrl && (
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            marginBottom: '8px'
          }}>
            <img
              src={imageUrl}
              alt="Uploaded map"
              style={{
                maxWidth: '100%',
                maxHeight: '400px',
                objectFit: 'contain',
                borderRadius: '8px',
                border: '1px solid #e5e7eb',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
              }}
            />
          </div>
        )}

        {/* Legend Type Selection */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          <label style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '16px',
            border: `2px solid ${legendType === 'binned' ? '#007bff' : '#e5e7eb'}`,
            borderRadius: '8px',
            cursor: 'pointer',
            backgroundColor: legendType === 'binned' ? '#f0f9ff' : 'white',
            transition: 'all 0.2s ease'
          }}>
            <input
              type="radio"
              name="legendType"
              value="binned"
              checked={legendType === 'binned'}
              onChange={(e) => setLegendType('binned')}
              style={{ margin: 0, cursor: 'pointer' }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: '600', marginBottom: '4px', color: '#333' }}>
                Binned Legend
              </div>
              <div style={{ fontSize: '13px', color: '#666' }}>
                Discrete color bins (e.g., 4-6 distinct colors)
              </div>
            </div>
          </label>

          <label style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '16px',
            border: `2px solid ${legendType === 'continuous' ? '#007bff' : '#e5e7eb'}`,
            borderRadius: '8px',
            cursor: 'pointer',
            backgroundColor: legendType === 'continuous' ? '#f0f9ff' : 'white',
            transition: 'all 0.2s ease'
          }}>
            <input
              type="radio"
              name="legendType"
              value="continuous"
              checked={legendType === 'continuous'}
              onChange={(e) => setLegendType('continuous')}
              style={{ margin: 0, cursor: 'pointer' }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: '600', marginBottom: '4px', color: '#333' }}>
                Continuous Legend
              </div>
              <div style={{ fontSize: '13px', color: '#666' }}>
                Gradient/continuous color scale
              </div>
            </div>
          </label>
        </div>

        {/* Binned Input */}
        {legendType === 'binned' && (
          <div style={{
            padding: '16px',
            backgroundColor: '#f8fafc',
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            width: '100%'
          }}>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: '600',
              marginBottom: '8px',
              color: '#333'
            }}>
              Number of Bins
            </label>
            <input
              type="number"
              min="2"
              max="20"
              value={numBins}
              onChange={(e) => setNumBins(e.target.value)}
              placeholder="e.g., 4, 5, 6"
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px',
                boxSizing: 'border-box'
              }}
            />
            <p style={{
              margin: '8px 0 0 0',
              fontSize: '12px',
              color: '#666'
            }}>
              Enter the number of distinct color bins in your legend. Min and max values will be extracted from the legend when you select it.
            </p>
          </div>
        )}

        {/* Continuous Input */}
        {legendType === 'continuous' && (
          <div style={{
            padding: '16px',
            backgroundColor: '#f8fafc',
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px'
          }}>
            <div>
              <label style={{
                display: 'block',
                fontSize: '14px',
                fontWeight: '600',
                marginBottom: '8px',
                color: '#333'
              }}>
                Minimum Value
              </label>
              <input
                type="number"
                step="any"
                value={minValue}
                onChange={(e) => setMinValue(e.target.value)}
                placeholder="e.g., 0, 10.5"
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
              />
            </div>
            <div>
              <label style={{
                display: 'block',
                fontSize: '14px',
                fontWeight: '600',
                marginBottom: '8px',
                color: '#333'
              }}>
                Maximum Value
              </label>
              <input
                type="number"
                step="any"
                value={maxValue}
                onChange={(e) => setMaxValue(e.target.value)}
                placeholder="e.g., 100, 50.2"
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
              />
            </div>
            <p style={{
              margin: 0,
              fontSize: '12px',
              color: '#666'
            }}>
              Enter the lowest and highest values shown in your legend
            </p>
          </div>
        )}

        {/* Buttons */}
        <div style={{
          display: 'flex',
          gap: '12px',
          justifyContent: 'flex-end'
        }}>
          <button
            onClick={onCancel}
            style={{
              backgroundColor: '#6c757d',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!legendType || (legendType === 'binned' && !numBins) || (legendType === 'continuous' && (!minValue || !maxValue))}
            style={{
              backgroundColor: (!legendType || (legendType === 'binned' && !numBins) || (legendType === 'continuous' && (!minValue || !maxValue))) ? '#ccc' : '#28a745',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: (!legendType || (legendType === 'binned' && !numBins) || (legendType === 'continuous' && (!minValue || !maxValue))) ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}

