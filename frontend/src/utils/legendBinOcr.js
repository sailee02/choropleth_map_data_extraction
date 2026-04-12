/**
 * Parse choropleth-style bin ranges from OCR text (e.g. 6.90-33.10).
 */
export function parseBinRangeFromText(text) {
  if (!text || typeof text !== "string") return null;
  const t = text
    .replace(/\r/g, " ")
    .replace(/\n/g, " ")
    .replace(/\s+/g, " ")
    .replace(/[–—‐−]/g, "-")
    .trim();
  const patterns = [
    /\b(\d+[.,]\d+)\s*-\s*(\d+[.,]\d+)\b/,
    /\b(\d+[.,]\d+)\s+(\d+[.,]\d+)\b/,
    /\b(\d+)\s*-\s*(\d+)\b/,
  ];
  for (const re of patterns) {
    const m = t.match(re);
    if (m) {
      const lo = parseFloat(m[1].replace(",", "."));
      const hi = parseFloat(m[2].replace(",", "."));
      if (Number.isFinite(lo) && Number.isFinite(hi) && hi > lo) {
        return `${lo}-${hi}`;
      }
    }
  }
  return null;
}

/** True if the string already looks like a numeric min–max range (not a placeholder). */
export function looksLikeNumericRange(s) {
  return /\d[\d.,]*\s*[-–—]\s*\d[\d.,]*/.test(String(s ?? ""));
}

export function isPlaceholderBinLabel(s) {
  const t = String(s ?? "").trim();
  if (!t) return true;
  return /^bin\s*\d+$/i.test(t);
}

/**
 * OCR each horizontal band of a vertical legend crop; reads the number column (right side).
 * @param {string} legendCropDataUrl - data URL of the exact legend rectangle
 * @param {number} numBins
 * @returns {Promise<(string|null)[]>} one string per bin (or null if unreadable)
 */
export async function ocrVerticalLegendBinRanges(legendCropDataUrl, numBins) {
  if (!legendCropDataUrl || numBins < 2) return [];

  const img = await new Promise((resolve, reject) => {
    const im = new Image();
    im.onload = () => resolve(im);
    im.onerror = () => reject(new Error("Legend image load failed"));
    im.src = legendCropDataUrl;
  });

  const w = img.naturalWidth || img.width;
  const h = img.naturalHeight || img.height;
  if (w < 4 || h < 4) return Array(numBins).fill(null);

  const stripH = h / numBins;
  const { createWorker } = await import("tesseract.js");
  const worker = await createWorker("eng", 1, { logger: () => {} });

  try {
    try {
      await worker.setParameters({
        tessedit_pageseg_mode: "7",
        tessedit_char_whitelist: "0123456789.-",
      });
    } catch {
      try {
        await worker.setParameters({ tessedit_pageseg_mode: "7" });
      } catch {
        /* use defaults */
      }
    }

    const results = [];
    for (let i = 0; i < numBins; i++) {
      const y0 = Math.floor(i * stripH);
      const y1 = Math.max(y0 + 1, Math.floor((i + 1) * stripH));
      const sh = y1 - y0;
      const textLeft = Math.floor(w * 0.28);
      const cw = Math.max(8, w - textLeft);

      const c = document.createElement("canvas");
      const scale = Math.max(2, Math.min(4, 140 / Math.max(sh, 8)));
      c.width = Math.min(900, Math.ceil(cw * scale));
      c.height = Math.min(220, Math.ceil(sh * scale));
      const ctx = c.getContext("2d");
      if (!ctx) {
        results.push(null);
        continue;
      }
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, textLeft, y0, cw, sh, 0, 0, c.width, c.height);

      const { data } = await worker.recognize(c);
      let label = parseBinRangeFromText(data.text);

      if (!label) {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, y0, w, sh, 0, 0, c.width, c.height);
        const r2 = await worker.recognize(c);
        label = parseBinRangeFromText(r2.data.text);
      }

      results.push(label);
    }

    return results;
  } finally {
    await worker.terminate();
  }
}
