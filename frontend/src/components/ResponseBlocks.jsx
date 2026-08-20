function formatValue(value) {
  return typeof value === "number"
    ? new Intl.NumberFormat("zh-TW").format(value)
    : (value ?? "—");
}

function Table({ table }) {
  if (!table?.columns?.length) return null;
  const rows = (table.rows || []).slice(0, 20);
  return (
    <details className="attachment" open>
      <summary>
        {table.title || "資料結果"}（{table.row_count ?? rows.length} 筆）
      </summary>
      <div className="attachment-content">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {table.columns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {table.columns.map((column) => (
                    <td key={column.key}>{formatValue(row[column.key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(table.rows || []).length > rows.length && (
          <p className="more-rows">
            僅顯示前 {rows.length} 筆，完整結果共 {table.row_count} 筆。
          </p>
        )}
      </div>
    </details>
  );
}

function Chart({ chart, table }) {
  if (!chart?.encoding?.x || !chart.encoding?.y) return null;
  const rows = chart.data?.length ? chart.data : table?.rows || [];
  if (!rows.length) return null;
  const values = rows.map((row) => Number(row[chart.encoding.y]) || 0);
  const max = Math.max(...values, 1);
  return (
    <details className="attachment" open>
      <summary>圖表：{chart.title}</summary>
      <div className="attachment-content">
        <div className="chart">
          {rows.slice(0, 20).map((row, index) => {
            const value = Number(row[chart.encoding.y]) || 0;
            const display =
              chart.encoding.y_format === "0.00%"
                ? `${value.toFixed(2)}%`
                : formatValue(value);
            return (
              <div className="bar-row" key={index}>
                <span>{row[chart.encoding.x]}</span>
                <span className="bar-track">
                  <span
                    className="bar-fill"
                    style={{ width: `${Math.max(2, (value / max) * 100)}%` }}
                  />
                </span>
                <strong>{display}</strong>
              </div>
            );
          })}
        </div>
      </div>
    </details>
  );
}

function Images({ items }) {
  if (!items?.length) return null;
  return (
    <details className="attachment" open>
      <summary>拍品圖片（{items.length} 張）</summary>
      <div className="attachment-content">
        <div className="images">
          {items.map((image, index) => (
            <figure key={`${image.url}-${index}`}>
              <img src={image.url} alt={image.caption} loading="lazy" />
              <figcaption>{image.caption}</figcaption>
            </figure>
          ))}
        </div>
      </div>
    </details>
  );
}

export function DebugPanel({ debug }) {
  if (!debug) return null;
  return (
    <details className="attachment debug-panel" open>
      <summary>分析流程（可審計）</summary>
      <div className="attachment-content">
        <h4>Skills</h4>
        <ul className="trace-list">
          {debug.skills?.length ? (
            debug.skills.map((skill) => (
              <li key={skill.id || skill.name}>
                <strong>{skill.name || skill.id}</strong>
                <span>{skill.purpose || ""}</span>
              </li>
            ))
          ) : (
            <li>未使用額外 Skill</li>
          )}
        </ul>
        <h4>執行步驟</h4>
        <ol className="trace-list">
          {debug.trace?.length ? (
            debug.trace.map((step, index) => (
              <li className={`trace-${step.status || "done"}`} key={index}>
                <strong>{step.label}</strong>
                <span>{step.detail || ""}</span>
              </li>
            ))
          ) : (
            <li>沒有可顯示的步驟</li>
          )}
        </ol>
        {debug.sql?.length > 0 && (
          <>
            <h4>唯讀 SQL</h4>
            <div className="technical">
              {debug.sql.map((query, index) => (
                <pre key={index}>{query}</pre>
              ))}
            </div>
          </>
        )}
      </div>
    </details>
  );
}

export default function ResponseBlocks({ response }) {
  const tables = new Map(
    (response.blocks || [])
      .filter((block) => block.type === "table")
      .map((block) => [block.id, block.data]),
  );
  return (
    <>
      {(response.blocks || []).map((block, index) => {
        if (block.type === "table")
          return <Table key={block.id || index} table={block.data} />;
        if (block.type === "chart")
          return (
            <Chart
              key={block.id || index}
              chart={block.data}
              table={tables.get(block.data?.data_table_id)}
            />
          );
        if (block.type === "image")
          return <Images key={block.id || index} items={block.data?.items} />;
        if (block.type === "kpi")
          return (
            <div className="kpi" key={block.id || index}>
              <strong>{block.title}</strong>
              <span>{block.data?.value ?? "—"}</span>
            </div>
          );
        return null;
      })}
      <DebugPanel debug={response.debug} />
      {(response.warnings || []).map((warning, index) => (
        <div className="notice" key={index}>
          {warning}
        </div>
      ))}
    </>
  );
}
