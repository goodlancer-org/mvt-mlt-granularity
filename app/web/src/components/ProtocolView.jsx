import './ProtocolView.css';

function formatBytes(bytes) {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function yesNo(value) {
  return value ? 'yes' : 'no';
}

export default function ProtocolView({ protocol }) {
  if (!protocol) return null;

  const dataset = protocol.dataset || {};
  const profile = protocol.profile || {};
  const topology = protocol.topology || {};
  const outputs = protocol.outputs || {};
  const validation = protocol.validation || {};
  const zoomSummary = protocol.zoom_summary || [];
  const layerSummary = protocol.layer_summary || [];
  const workloadSummary = protocol.workload_summary || [];
  const outputKeys = [
    'standard_mvt', 'standard_mlt',
    'dense4_mvt', 'dense4_mlt',
    'dense16_mvt', 'dense16_mlt',
  ].filter((key) => outputs[key]?.path || outputs[key]?.archive_bytes);
  const displayedOutputKeys = outputKeys.length > 0 ? outputKeys : ['mvt', 'mlt'];

  return (
    <div className="protocol-view">
      <section className="protocol-section protocol-summary">
        <div className="summary-grid">
          <div className="summary-card"><div className="summary-value">{dataset.id || '—'}</div><div className="summary-label">Dataset</div></div>
          <div className="summary-card"><div className="summary-value">{profile.origin || '—'}</div><div className="summary-label">Profile</div></div>
          <div className="summary-card"><div className="summary-value">{topology.layer_count ?? '—'}</div><div className="summary-label">Layers</div></div>
          <div className="summary-card"><div className="summary-value">{topology.logical_feature_count ?? '—'}</div><div className="summary-label">Logical Features</div></div>
          <div className="summary-card"><div className="summary-value">{yesNo(validation.research_ready)}</div><div className="summary-label">Research Ready</div></div>
          <div className="summary-card"><div className="summary-value">{formatBytes(outputs.mlt?.archive_bytes)}</div><div className="summary-label">MLT Size</div></div>
        </div>
      </section>

      <section className="protocol-section">
        <h3>Dataset</h3>
        <dl className="protocol-dl">
          <dt>Title</dt><dd>{dataset.title || '—'}</dd>
          <dt>Source format</dt><dd>{dataset.source_format || '—'}</dd>
          <dt>Source SHA-256</dt><dd>{dataset.source_sha256 || '—'}</dd>
          <dt>CRS</dt><dd>{dataset.crs || '—'}</dd>
        </dl>
      </section>

      <section className="protocol-section">
        <h3>Profile</h3>
        <dl className="protocol-dl">
          <dt>Version</dt><dd>{profile.version ?? '—'}</dd>
          <dt>Origin</dt><dd>{profile.origin || '—'}</dd>
          <dt>Path</dt><dd>{profile.path || '—'}</dd>
          <dt>SHA-256</dt><dd>{profile.sha256 || '—'}</dd>
        </dl>
      </section>

      <section className="protocol-section">
        <h3>Topology</h3>
        <dl className="protocol-dl">
          <dt>Min zoom</dt><dd>{topology.min_zoom ?? '—'}</dd>
          <dt>Max zoom</dt><dd>{topology.max_zoom ?? '—'}</dd>
          <dt>Layer count</dt><dd>{topology.layer_count ?? '—'}</dd>
          <dt>Feature instance count</dt><dd>{topology.feature_instance_count ?? '—'}</dd>
          <dt>Vertex count</dt><dd>{topology.vertex_count ?? '—'}</dd>
        </dl>
      </section>

      <section className="protocol-section">
        <h3>Outputs</h3>
        <table className="protocol-table">
          <thead><tr><th>Encoding</th><th>Path</th><th>Archive bytes</th><th>Tiles</th><th>Method</th></tr></thead>
          <tbody>
            {displayedOutputKeys.map((key) => (
              <tr key={key}>
                <td><strong>{key.replace(/_/g, ' ').toUpperCase()}</strong></td>
                <td>{outputs[key]?.path || '—'}</td>
                <td>{formatBytes(outputs[key]?.archive_bytes)}</td>
                <td>{outputs[key]?.tile_count ?? '—'}</td>
                <td>{outputs[key]?.generation_method || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="protocol-section">
        <h3>Validation</h3>
        <table className="protocol-table">
          <thead><tr><th>Check</th><th>Value</th></tr></thead>
          <tbody>
            {Object.entries(validation).map(([key, value]) => (
              <tr key={key}><td>{key.replace(/_/g, ' ')}</td><td>{yesNo(value)}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="protocol-section">
        <h3>Zoom Summary</h3>
        <table className="protocol-table">
          <thead><tr><th>Zoom</th><th>Tiles</th><th>Features</th><th>Instances</th><th>MVT</th><th>MLT</th><th>Savings</th></tr></thead>
          <tbody>
            {zoomSummary.length > 0 ? zoomSummary.map((row) => (
              <tr key={row.zoom}>
                <td>{row.zoom}</td>
                <td>{row.tile_count ?? '—'}</td>
                <td>{row.unique_logical_features ?? '—'}</td>
                <td>{row.feature_instances ?? '—'}</td>
                <td>{formatBytes(row.mvt_stored_bytes)}</td>
                <td>{formatBytes(row.mlt_stored_bytes)}</td>
                <td>{row.mlt_stored_savings_pct == null ? '—' : `${row.mlt_stored_savings_pct}%`}</td>
              </tr>
            )) : <tr><td colSpan="7">No zoom summary available.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="protocol-section">
        <h3>Layer Summary</h3>
        <table className="protocol-table">
          <thead><tr><th>Layer</th><th>Semantic kind</th><th>Semantic type</th><th>Features</th><th>Instances</th><th>Vertices</th><th>Tiles</th><th>Savings</th></tr></thead>
          <tbody>
            {layerSummary.length > 0 ? layerSummary.map((row) => (
              <tr key={row.layer}>
                <td><strong>{row.layer}</strong></td>
                <td>{row.semantic_kind || '—'}</td>
                <td>{row.semantic_type || '—'}</td>
                <td>{row.unique_logical_features ?? '—'}</td>
                <td>{row.feature_instances ?? '—'}</td>
                <td>{row.vertex_count ?? '—'}</td>
                <td>{row.tile_appearances ?? '—'}</td>
                <td>{row.mlt_encoded_savings_pct == null ? '—' : `${row.mlt_encoded_savings_pct}%`}</td>
              </tr>
            )) : <tr><td colSpan="8">No layer summary available.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="protocol-section">
        <h3>Workloads</h3>
        <table className="protocol-table">
          <thead><tr><th>Scenario</th><th>Step</th><th>Operation</th><th>New tiles</th><th>New MVT</th><th>New MLT</th></tr></thead>
          <tbody>
            {workloadSummary.length > 0 ? workloadSummary.map((row) => (
              <tr key={`${row.scenario_name}-${row.step_index}`}>
                <td>{row.scenario_name}</td>
                <td>{row.step_index}</td>
                <td>{row.operation}</td>
                <td>{row.new_tile_count ?? '—'}</td>
                <td>{formatBytes(row.new_mvt_stored_bytes)}</td>
                <td>{formatBytes(row.new_mlt_stored_bytes)}</td>
              </tr>
            )) : <tr><td colSpan="6">No workload summary available.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
