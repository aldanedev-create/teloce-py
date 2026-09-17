/* Browser data and sharing helpers for Teloce applications. */

const toDate = value => value instanceof Date ? value : new Date(value);

/** Parse RFC-4180-style CSV/TSV without depending on a third-party package. */
export function parseDelimited(source, options = {}) {
  const delimiter = options.delimiter || (options.tsv ? "\t" : ",");
  const text = String(source ?? "").replace(/^\uFEFF/, "");
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const next = text[index + 1];
    if (quoted) {
      if (character === '"' && next === '"') { field += '"'; index += 1; }
      else if (character === '"') quoted = false;
      else field += character;
    } else if (character === '"' && field.length === 0) quoted = true;
    else if (character === delimiter) { row.push(field); field = ""; }
    else if (character === "\n" || character === "\r") {
      if (character === "\r" && next === "\n") index += 1;
      row.push(field); field = "";
      if (row.some(value => value !== "")) rows.push(row);
      row = [];
    } else field += character;
  }
  if (quoted) throw new SyntaxError("Unclosed quoted field in delimited data");
  if (field.length || row.length) { row.push(field); if (row.some(value => value !== "")) rows.push(row); }
  if (!rows.length) return [];
  const headers = options.headers === false ? null : (options.headers || rows.shift());
  if (!headers) return rows;
  return rows.map((values, rowIndex) => {
    if (values.length > headers.length && options.strict) throw new SyntaxError(`Row ${rowIndex + 1} has more fields than the header`);
    const result = {};
    headers.forEach((header, index) => { result[String(header).trim()] = coerce(values[index] ?? "", options.types?.[header]); });
    if (values.length !== headers.length && options.onRowError) options.onRowError({ row: rowIndex + 1, expected: headers.length, received: values.length });
    return result;
  });
}

export function coerce(value, type) {
  if (value === "" || value == null) return type === "string" ? "" : null;
  if (!type || type === "string") return String(value);
  if (type === "number") { const result = Number(String(value).replace(/,/g, "")); return Number.isFinite(result) ? result : null; }
  if (type === "boolean") return /^(true|1|yes)$/i.test(String(value));
  if (type === "date") { const result = toDate(value); return Number.isNaN(result.getTime()) ? null : result; }
  if (typeof type === "function") return type(value);
  return value;
}

export async function loadCsv(url, options = {}) {
  const controller = options.signal ? null : (typeof AbortController === "function" ? new AbortController() : null);
  const signal = options.signal || controller?.signal;
  const response = await fetch(url, { signal, headers: { Accept: "text/csv,text/tab-separated-values,text/plain" } });
  if (!response.ok) throw new Error(`CSV request failed: ${response.status} ${response.statusText}`);
  const source = await response.text();
  return parseDelimited(source, options);
}

const safeCsvCell = value => {
  const text = value == null ? "" : value instanceof Date ? value.toISOString() : String(value);
  // Prevent spreadsheet formula injection when the export is opened in Excel.
  const safe = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
};

export function exportRowsToCsv(rows, options = {}) {
  const values = Array.isArray(rows) ? rows : [];
  const columns = options.columns || [...new Set(values.flatMap(row => Object.keys(row || {})))];
  const lines = [columns.map(safeCsvCell).join(",")];
  for (const row of values) lines.push(columns.map(column => safeCsvCell(row?.[column])).join(","));
  return lines.join("\r\n") + "\r\n";
}

export function downloadText(text, filename = "export.txt", type = "text/plain;charset=utf-8") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadRowsAsCsv(rows, filename = "data.csv", options = {}) {
  downloadText(exportRowsToCsv(rows, options), filename, "text/csv;charset=utf-8");
}

export function exportChartToPng(element, filename = "chart.png", scale = 2) {
  if (!element) throw new TypeError("A chart element is required");
  const canvas = element instanceof HTMLCanvasElement ? element : element.querySelector?.("canvas");
  if (!canvas) throw new Error("PNG export requires a canvas chart");
  const output = document.createElement("canvas"); output.width = canvas.width * scale; output.height = canvas.height * scale;
  const context = output.getContext("2d"); context.scale(scale, scale); context.drawImage(canvas, 0, 0);
  const anchor = document.createElement("a");
  anchor.href = output.toDataURL("image/png"); anchor.download = filename; anchor.click();
}

export function exportChartToSvg(element, filename = "chart.svg") {
  const svg = element?.matches?.("svg") ? element : element?.querySelector?.("svg");
  if (!svg) throw new Error("SVG export requires an SVG chart");
  downloadText(new XMLSerializer().serializeToString(svg), filename, "image/svg+xml");
}
