import { exportRowsToCsv, downloadText } from './data.js';

/**
 * Framework-neutral accessible data table primitive.
 *
 * It is intentionally small enough to use from a .vel action or ordinary
 * module, while keeping filtering/sorting/pagination deterministic and keyed.
 */
export function createDataTable(container, options = {}) {
  if (!container) throw new TypeError('createDataTable requires a container');
  const columns = (options.columns || []).map(column => typeof column === 'string' ? { key: column, label: column } : column);
  let rows = Array.isArray(options.rows) ? options.rows : [];
  let query = '';
  let sort = null;
  let page = 0;
  const pageSize = Math.max(1, Number(options.pageSize || 25));
  const keyOf = options.key || (row => row?.id ?? row?.key ?? rows.indexOf(row));
  const shell = document.createElement('div'); shell.className = 'teloce-data-table';
  const controls = document.createElement('div'); controls.className = 'teloce-data-table-controls';
  const input = document.createElement('input'); input.type = 'search'; input.placeholder = options.searchPlaceholder || 'Filter rows'; input.setAttribute('aria-label', 'Filter rows');
  const status = document.createElement('output'); status.setAttribute('aria-live', 'polite');
  const table = document.createElement('table'); table.setAttribute('role', 'grid');
  const head = document.createElement('thead'); const body = document.createElement('tbody');
  const footer = document.createElement('div'); footer.className = 'teloce-data-table-footer';
  controls.append(input, status); table.append(head, body); shell.append(controls, table, footer); container.replaceChildren(shell);
  const filtered = () => {
    const needle = query.trim().toLowerCase();
    let result = needle ? rows.filter(row => columns.some(column => String(row?.[column.key] ?? '').toLowerCase().includes(needle))) : [...rows];
    if (sort) result.sort((left, right) => { const a = left?.[sort.key]; const b = right?.[sort.key]; const value = a === b ? 0 : a == null ? -1 : b == null ? 1 : a < b ? -1 : 1; return sort.direction === 'desc' ? -value : value; });
    return result;
  };
  const render = () => {
    const result = filtered(); const pages = Math.max(1, Math.ceil(result.length / pageSize)); page = Math.min(page, pages - 1);
    const visible = options.virtual ? result.slice(page * pageSize, (page + 1) * pageSize) : result.slice(page * pageSize, (page + 1) * pageSize);
    head.replaceChildren(); const headerRow = document.createElement('tr');
    for (const column of columns) {
      const th = document.createElement('th'); th.scope = 'col';
      if (column.sortable !== false && options.sortable !== false) { const button = document.createElement('button'); button.type = 'button'; button.textContent = column.label || column.key; button.setAttribute('aria-label', `Sort by ${column.label || column.key}`); button.onclick = () => { sort = sort?.key === column.key ? { key: column.key, direction: sort.direction === 'asc' ? 'desc' : 'asc' } : { key: column.key, direction: 'asc' }; render(); }; th.append(button); }
      else th.textContent = column.label || column.key;
      headerRow.append(th);
    }
    head.append(headerRow); body.replaceChildren();
    if (!visible.length) { const row = document.createElement('tr'); const cell = document.createElement('td'); cell.colSpan = Math.max(columns.length, 1); cell.textContent = options.emptyText || 'No matching rows'; row.append(cell); body.append(row); }
    for (const item of visible) { const row = document.createElement('tr'); row.dataset.key = String(keyOf(item)); for (const column of columns) { const cell = document.createElement('td'); const value = item?.[column.key]; if (typeof column.render === 'function') { const rendered = column.render(value, item); if (rendered && typeof rendered === 'object' && rendered.nodeType) cell.append(rendered); else cell.textContent = String(rendered ?? ''); } else cell.textContent = String(value ?? ''); row.append(cell); } body.append(row); }
    status.textContent = `${result.length} row${result.length === 1 ? '' : 's'}`; footer.replaceChildren();
    if (pages > 1) { const previous = document.createElement('button'); previous.type = 'button'; previous.textContent = 'Previous'; previous.disabled = page === 0; previous.onclick = () => { page -= 1; render(); }; const next = document.createElement('button'); next.type = 'button'; next.textContent = 'Next'; next.disabled = page >= pages - 1; next.onclick = () => { page += 1; render(); }; footer.append(previous, document.createTextNode(` Page ${page + 1} of ${pages} `), next); }
  };
  input.addEventListener('input', () => { query = input.value; page = 0; render(); }); render();
  return {
    update(next = {}) { if (Object.prototype.hasOwnProperty.call(next, 'rows')) rows = Array.isArray(next.rows) ? next.rows : []; if (Object.prototype.hasOwnProperty.call(next, 'columns')) columns.splice(0, columns.length, ...(next.columns || []).map(column => typeof column === 'string' ? { key: column, label: column } : column)); render(); },
    setRows(next) { rows = Array.isArray(next) ? next : []; page = 0; render(); },
    getVisibleRows() { return filtered().slice(page * pageSize, (page + 1) * pageSize); },
    exportCsv(filename = 'table.csv') { downloadText(exportRowsToCsv(filtered(), { columns: columns.map(column => column.key) }), filename, 'text/csv;charset=utf-8'); },
    unmount() { container.replaceChildren(); },
  };
}
