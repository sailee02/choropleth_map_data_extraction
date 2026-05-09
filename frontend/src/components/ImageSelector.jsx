import React, { useState, useRef, useEffect } from 'react';
import { previewLegend } from '../api';
import {
  ocrVerticalLegendBinRanges,
  looksLikeNumericRange,
  isPlaceholderBinLabel,
} from '../utils/legendBinOcr';

function toImageSelection(selection, imageRef) {
  const rect = imageRef.current.getBoundingClientRect();
  const imageWidth = imageRef.current.naturalWidth;
  const imageHeight = imageRef.current.naturalHeight;
  return {
    x: (selection.left / rect.width) * imageWidth,
    y: (selection.top / rect.height) * imageHeight,
    width: (selection.width / rect.width) * imageWidth,
    height: (selection.height / rect.height) * imageHeight,
  };
}

export default function ImageSelector({
  imageUrl,
  uploadId,
  legendTypeInfo,
  onSelectionComplete,
  onCancel,
}) {
  const [phase, setPhase] = useState('draw');
  const [isSelecting, setIsSelecting] = useState(false);
  const [startPoint, setStartPoint] = useState(null);
  const [endPoint, setEndPoint] = useState(null);
  const [selection, setSelection] = useState(null);
  const [pendingNatSelection, setPendingNatSelection] = useState(null);
  const [previewError, setPreviewError] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [reviewRows, setReviewRows] = useState([]);
  const [legendCropUrl, setLegendCropUrl] = useState('');
  const [clientOcrLoading, setClientOcrLoading] = useState(false);
  const [activeColorRowIdx, setActiveColorRowIdx] = useState(null);
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const cropImgRef = useRef(null);

  const isBinned = legendTypeInfo && legendTypeInfo.type === 'binned';

  useEffect(() => {
    if (phase !== 'review' || !pendingNatSelection || !imageUrl) {
      if (phase !== 'review') setLegendCropUrl('');
      return;
    }
    const { x, y, width, height } = pendingNatSelection;
    const img = new Image();
    img.onload = () => {
      const cw = Math.max(1, Math.round(width));
      const ch = Math.max(1, Math.round(height));
      const canvas = document.createElement('canvas');
      canvas.width = cw;
      canvas.height = ch;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        setLegendCropUrl('');
        return;
      }
      ctx.drawImage(
        img,
        Math.round(x),
        Math.round(y),
        cw,
        ch,
        0,
        0,
        cw,
        ch
      );
      try {
        setLegendCropUrl(canvas.toDataURL('image/png'));
      } catch {
        setLegendCropUrl('');
      }
    };
    img.onerror = () => setLegendCropUrl('');
    img.src = imageUrl;
  }, [phase, pendingNatSelection, imageUrl]);

  useEffect(() => {
    if (phase !== 'review' || !isBinned || !legendCropUrl || reviewRows.length < 2) {
      return undefined;
    }
    const crop = legendCropUrl;
    const n = reviewRows.length;
    let cancelled = false;
    setClientOcrLoading(true);
    ocrVerticalLegendBinRanges(crop, n)
      .then((ranges) => {
        if (cancelled) return;
        setReviewRows((rows) => {
          if (rows.length !== n) return rows;
          return rows.map((row, i) => {
            const ocrLabel = ranges[i];
            if (!ocrLabel) return row;
            const cur = String(row.binRange ?? '').trim();
            const keepServer =
              looksLikeNumericRange(cur) && !isPlaceholderBinLabel(cur);
            if (keepServer) return row;
            return { ...row, binRange: ocrLabel };
          });
        });
      })
      .catch(() => {
        /* keep server / placeholder labels */
      })
      .finally(() => {
        if (!cancelled) setClientOcrLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [phase, isBinned, legendCropUrl, reviewRows.length]);

  const handleMouseDown = (e) => {
    if (phase !== 'draw' || !imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (x >= 0 && x <= rect.width && y >= 0 && y <= rect.height) {
      setIsSelecting(true);
      setStartPoint({ x, y });
      setEndPoint({ x, y });
    }
  };

  const handleMouseMove = (e) => {
    if (!isSelecting || !imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const constrainedX = Math.max(0, Math.min(x, rect.width));
    const constrainedY = Math.max(0, Math.min(y, rect.height));

    setEndPoint({ x: constrainedX, y: constrainedY });
  };

  const handleMouseUp = () => {
    if (!isSelecting || !startPoint || !endPoint) return;

    setIsSelecting(false);

    const left = Math.min(startPoint.x, endPoint.x);
    const top = Math.min(startPoint.y, endPoint.y);
    const width = Math.abs(endPoint.x - startPoint.x);
    const height = Math.abs(endPoint.y - startPoint.y);

    if (width > 10 && height > 10) {
      setSelection({ left, top, width, height });
    } else {
      setStartPoint(null);
      setEndPoint(null);
    }
  };

  const finishWithoutReview = (nat) => {
    onSelectionComplete(nat);
  };

  const handleConfirmSelection = async () => {
    if (!selection || !imageRef.current) return;

    const imageSelection = toImageSelection(selection, imageRef);

    if (!isBinned || !uploadId) {
      finishWithoutReview(imageSelection);
      return;
    }

    setPreviewError('');
    setPreviewLoading(true);
    setPendingNatSelection(imageSelection);
    try {
      const resp = await previewLegend(uploadId, imageSelection, legendTypeInfo);
      const bins = resp.data?.bins;
      if (!bins || !Array.isArray(bins) || bins.length < 2) {
        setPreviewError('Could not read enough legend bins from this area.');
        setPreviewLoading(false);
        return;
      }
      setReviewRows(
        bins.map((b) => ({
          rgb: b.rgb,
          binRange: String(b.binRange ?? b.label ?? "").trim(),
        }))
      );
      setPhase('review');
    } catch (err) {
      setPreviewError(
        err.response?.data?.error || err.message || 'Preview failed'
      );
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleConfirmReview = () => {
    if (!pendingNatSelection) return;
    const binLabelsOverride = [];
    const binColorsOverride = [];
    for (let i = 0; i < reviewRows.length; i++) {
      const row = reviewRows[i];
      const text = String(row.binRange ?? "").trim();
      binLabelsOverride.push(text || `Bin ${i + 1}`);
      const rgb = Array.isArray(row.rgb) ? row.rgb : null;
      if (rgb && rgb.length >= 3) {
        binColorsOverride.push([
          Math.max(0, Math.min(255, Math.round(Number(rgb[0]) || 0))),
          Math.max(0, Math.min(255, Math.round(Number(rgb[1]) || 0))),
          Math.max(0, Math.min(255, Math.round(Number(rgb[2]) || 0))),
        ]);
      } else {
        binColorsOverride.push(null);
      }
    }
    onSelectionComplete(pendingNatSelection, {
      binLabelsOverride,
      binColorsOverride,
    });
  };

  const handleBackToDraw = () => {
    setPhase('draw');
    setReviewRows([]);
    setPendingNatSelection(null);
    setLegendCropUrl('');
    setClientOcrLoading(false);
    setPreviewError('');
    setActiveColorRowIdx(null);
  };

  const handleClearSelection = () => {
    setSelection(null);
    setStartPoint(null);
    setEndPoint(null);
  };

  const getSelectionStyle = () => {
    if (!startPoint || !endPoint) return null;

    const left = Math.min(startPoint.x, endPoint.x);
    const top = Math.min(startPoint.y, endPoint.y);
    const width = Math.abs(endPoint.x - startPoint.x);
    const height = Math.abs(endPoint.y - startPoint.y);

    return {
      position: 'absolute',
      left: left,
      top: top,
      width: width,
      height: height,
      border: '2px solid #007bff',
      backgroundColor: 'rgba(0, 123, 255, 0.1)',
      pointerEvents: 'none',
      zIndex: 10,
    };
  };

  const getConfirmedSelectionStyle = () => {
    if (!selection) return null;

    return {
      position: 'absolute',
      left: selection.left,
      top: selection.top,
      width: selection.width,
      height: selection.height,
      border: '2px solid #28a745',
      backgroundColor: 'rgba(40, 167, 69, 0.1)',
      pointerEvents: 'none',
      zIndex: 10,
    };
  };

  const rgbCss = (rgb) => {
    if (!rgb || rgb.length < 3) return '#ccc';
    return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
  };

  const handleCropClickPickColor = async (e) => {
    if (phase !== 'review') return;
    if (activeColorRowIdx == null || activeColorRowIdx < 0 || activeColorRowIdx >= reviewRows.length) {
      return;
    }
    const imgEl = cropImgRef.current;
    if (!imgEl) return;

    const rect = imgEl.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    if (x < 0 || y < 0 || x > rect.width || y > rect.height) return;

    const natW = imgEl.naturalWidth || 0;
    const natH = imgEl.naturalHeight || 0;
    if (natW < 2 || natH < 2) return;
    const px = Math.max(0, Math.min(natW - 1, Math.round((x / rect.width) * natW)));
    const py = Math.max(0, Math.min(natH - 1, Math.round((y / rect.height) * natH)));

    try {
      const canvas = document.createElement('canvas');
      canvas.width = natW;
      canvas.height = natH;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(imgEl, 0, 0);
      const d = ctx.getImageData(px, py, 1, 1).data;
      const rgb = [d[0], d[1], d[2]];
      setReviewRows((rows) => {
        const next = [...rows];
        next[activeColorRowIdx] = { ...next[activeColorRowIdx], rgb };
        return next;
      });
    } catch {
      // ignore
    }
  };

  return (
    <div
      style={{
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
      }}
    >
      <div
        style={{
          backgroundColor: 'white',
          borderRadius: '12px',
          padding: '24px',
          maxWidth: phase === 'review' ? '720px' : '90vw',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          overflow: 'auto',
        }}
      >
        {phase === 'draw' && (
          <>
            <h3
              style={{
                margin: '0 0 16px 0',
                color: '#333',
                fontSize: '20px',
                fontWeight: '600',
              }}
            >
              Select Legend Area
            </h3>

            <p
              style={{
                margin: '0 0 20px 0',
                color: '#666',
                fontSize: '14px',
                textAlign: 'center',
                maxWidth: '400px',
              }}
            >
              Click and drag to draw a rectangle around the legend area in your
              image.
            </p>
          </>
        )}

        {phase === 'review' && (
          <>
            <h3
              style={{
                margin: '0 0 8px 0',
                color: '#333',
                fontSize: '20px',
                fontWeight: '600',
              }}
            >
              Review detected legend bins
            </h3>
            {legendCropUrl ? (
              <div
                style={{
                  width: '100%',
                  marginBottom: '16px',
                  textAlign: 'center',
                }}
              >
                <p
                  style={{
                    margin: '0 0 8px 0',
                    color: '#64748b',
                    fontSize: '13px',
                    fontWeight: '500',
                  }}
                >
                  Selected legend area
                </p>
                <div
                  style={{
                    display: 'inline-block',
                    maxWidth: '100%',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    padding: '8px',
                    backgroundColor: '#f8fafc',
                  }}
                >
                  <img
                    ref={cropImgRef}
                    src={legendCropUrl}
                    alt="Cropped legend selection"
                    style={{
                      maxWidth: 'min(100%, 480px)',
                      maxHeight: '200px',
                      width: 'auto',
                      height: 'auto',
                      objectFit: 'contain',
                      display: 'block',
                      cursor: activeColorRowIdx == null ? 'default' : 'crosshair',
                    }}
                    onClick={handleCropClickPickColor}
                  />
                </div>
              </div>
            ) : null}
            
            <p
              style={{
                margin: '-6px 0 16px 0',
                color: '#64748b',
                fontSize: '13px',
                textAlign: 'center',
                maxWidth: '560px',
              }}
            >
              Fix color: click on color box in the table, then click the correct color on the legend image.
              <br />
              Fix range: edit the range in the table.
            </p>
            {clientOcrLoading ? (
              <p
                style={{
                  margin: '-8px 0 16px 0',
                  color: '#2563eb',
                  fontSize: '13px',
                  textAlign: 'center',
                }}
              >
                Reading numeric ranges from the legend image…
              </p>
            ) : null}
          </>
        )}

        {phase === 'draw' && (
          <div
            ref={containerRef}
            style={{
              position: 'relative',
              display: 'inline-block',
              maxWidth: '100%',
              maxHeight: '60vh',
              cursor: isSelecting ? 'crosshair' : 'default',
              opacity: previewLoading ? 0.5 : 1,
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          >
            <img
              ref={imageRef}
              src={imageUrl}
              alt="Select legend area"
              style={{
                maxWidth: '100%',
                maxHeight: '100%',
                objectFit: 'contain',
                display: 'block',
                userSelect: 'none',
              }}
              draggable={false}
            />

            {isSelecting && getSelectionStyle() && (
              <div style={getSelectionStyle()} />
            )}

            {!isSelecting && getConfirmedSelectionStyle() && (
              <div style={getConfirmedSelectionStyle()} />
            )}
          </div>
        )}

        {previewError && phase === 'draw' && (
          <div
            style={{
              marginTop: '12px',
              padding: '10px 14px',
              backgroundColor: '#fef2f2',
              color: '#b91c1c',
              borderRadius: '6px',
              fontSize: '13px',
              maxWidth: '480px',
              textAlign: 'left',
            }}
          >
            {previewError}
          </div>
        )}

        {phase === 'review' && (
          <div
            style={{
              width: '100%',
              maxHeight: '50vh',
              overflow: 'auto',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
            }}
          >
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '13px',
              }}
            >
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', textAlign: 'left' }}>
                  <th style={{ padding: '10px 12px', borderBottom: '1px solid #e5e7eb' }}>
                    Colour
                  </th>
                  <th style={{ padding: '10px 12px', borderBottom: '1px solid #e5e7eb' }}>
                    Bin range (legend)
                  </th>
                </tr>
              </thead>
              <tbody>
                {reviewRows.map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 12px', verticalAlign: 'middle' }}>
                      <div
                        style={{
                          width: '36px',
                          height: '24px',
                          borderRadius: '4px',
                          border: activeColorRowIdx === i ? '2px solid #2563eb' : '1px solid #cbd5e1',
                          backgroundColor: rgbCss(row.rgb),
                          cursor: 'pointer',
                          boxShadow: activeColorRowIdx === i ? '0 0 0 3px rgba(37, 99, 235, 0.15)' : 'none',
                        }}
                        title="Click to select this bin for colour picking"
                        onClick={() => setActiveColorRowIdx(i)}
                      />
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      <input
                        type="text"
                        value={row.binRange}
                        onChange={(e) => {
                          const next = [...reviewRows];
                          next[i] = { ...next[i], binRange: e.target.value };
                          setReviewRows(next);
                        }}
                        style={{
                          width: '100%',
                          maxWidth: '320px',
                          padding: '6px 8px',
                          border: '1px solid #cbd5e1',
                          borderRadius: '4px',
                          fontSize: '13px',
                        }}
                        placeholder="Text from legend (numbers, words, or both)"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {phase === 'draw' && (
          <div
            style={{
              marginTop: '20px',
              display: 'flex',
              gap: '12px',
              alignItems: 'center',
              flexWrap: 'wrap',
              justifyContent: 'center',
            }}
          >
            <button
              onClick={handleConfirmSelection}
              disabled={!selection || previewLoading}
              style={{
                backgroundColor: selection && !previewLoading ? '#28a745' : '#ccc',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: selection && !previewLoading ? 'pointer' : 'not-allowed',
                transition: 'all 0.2s ease',
              }}
            >
              {previewLoading
                ? 'Detecting bins…'
                : isBinned
                ? 'Detect bins & continue'
                : 'Confirm selection'}
            </button>

            <button
              onClick={handleClearSelection}
              disabled={!selection || previewLoading}
              style={{
                backgroundColor: selection && !previewLoading ? '#6c757d' : '#ccc',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: selection && !previewLoading ? 'pointer' : 'not-allowed',
                transition: 'all 0.2s ease',
              }}
            >
              Clear
            </button>

            <button
              onClick={onCancel}
              disabled={previewLoading}
              style={{
                backgroundColor: '#dc3545',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: previewLoading ? 'not-allowed' : 'pointer',
                opacity: previewLoading ? 0.7 : 1,
                transition: 'all 0.2s ease',
              }}
            >
              Cancel
            </button>
          </div>
        )}

        {phase === 'review' && (
          <div
            style={{
              marginTop: '20px',
              display: 'flex',
              gap: '12px',
              alignItems: 'center',
              flexWrap: 'wrap',
              justifyContent: 'center',
            }}
          >
            <button
              onClick={handleConfirmReview}
              style={{
                backgroundColor: '#28a745',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer',
              }}
            >
              Use these bins & continue
            </button>
            <button
              onClick={handleBackToDraw}
              style={{
                backgroundColor: '#6c757d',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer',
              }}
            >
              Back — redraw box
            </button>
            <button
              onClick={onCancel}
              style={{
                backgroundColor: '#dc3545',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
