import {
  COLUMN_OPTIONS,
  DEFAULT_TABLE_COLUMNS,
  DOI_OPTIONS,
  saveTableColumns,
  useTableColumns,
  WIDTH_OPTIONS,
  WIDTHS,
  type ColumnWidth,
} from './tableColumns'

/** Settings → Appearance card: paper table columns, widths and DOI lines (stored in this browser). */
export default function PaperTableSettings() {
  const cols = useTableColumns()
  return (
    <div className="card settings-section">
      <h3>Paper tables</h3>
      <p className="muted small">
        Columns of the Library, project and reading-list tables. Title always shows and takes the remaining width.
        Stored in this browser.
      </p>
      <h4>Columns</h4>
      <div className="sidebar-toggles">
        {COLUMN_OPTIONS.map((o) => (
          <label key={o.key} className="check">
            <input
              type="checkbox"
              checked={cols.show[o.key]}
              onChange={(e) => saveTableColumns({ ...cols, show: { ...cols.show, [o.key]: e.target.checked } })}
            />
            {o.label}
          </label>
        ))}
      </div>
      <h4>Column width</h4>
      <div className="column-widths">
        {WIDTH_OPTIONS.map((o) => (
          <label key={o.key}>
            {o.label}{' '}
            <select
              value={cols.width[o.key]}
              onChange={(e) =>
                saveTableColumns({ ...cols, width: { ...cols.width, [o.key]: e.target.value as ColumnWidth } })
              }
            >
              {WIDTHS.map((w) => (
                <option key={w} value={w}>
                  {w[0].toUpperCase() + w.slice(1)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <h4>Show DOI under title</h4>
      <div className="sidebar-toggles">
        {DOI_OPTIONS.map((o) => (
          <label key={o.key} className="check">
            <input
              type="checkbox"
              checked={cols.doi[o.key]}
              onChange={(e) => saveTableColumns({ ...cols, doi: { ...cols.doi, [o.key]: e.target.checked } })}
            />
            {o.label}
          </label>
        ))}
      </div>
      <div className="actions">
        <button type="button" onClick={() => saveTableColumns(structuredClone(DEFAULT_TABLE_COLUMNS))}>
          Reset to defaults
        </button>
      </div>
    </div>
  )
}
