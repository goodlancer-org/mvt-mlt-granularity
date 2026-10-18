import { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  useProtocols,
  normalizeFromUpload,
  normalizeFromLocalFile,
  normalizeFromUrl,
  generateFromNormalized,
  previewProfilePlan,
  cancelDatasetJob,
  hasActiveJob,
} from '../hooks/useProtocol';
import './MapsList.css';

const HEARTBEAT_RE = /^\[heartbeat\]\s+(.+?):\s+elapsed=([^\s]+)\s+rss=([^\s]+(?:\s+[A-Z]+)?)\s+temp_db=([^\s]+(?:\s+[A-Z]+)?)\s+mbtiles=([^\s]+(?:\s+[A-Z]+)?)/i;
const OVERALL_PROGRESS_RE = /^\[overall-progress\]\s+variant=([^\s]+)\s+completed_features=(\d+)\s+total_features=(\d+)\s+progress=([\d.]+)%\s+eta=([^\s]+)/i;
const CURRENT_LAYER_PROGRESS_RE = /^\[current-layer-progress\]\s+variant=([^\s]+)\s+layer=(.+)\s+progress=(\d+)%$/i;

function formatSize(bytes) {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function parseHeartbeat(message) {
  if (!message || typeof message !== 'string') return null;
  const match = HEARTBEAT_RE.exec(message.trim());
  if (!match) return null;
  return {
    label: match[1],
    elapsed: match[2],
    rss: match[3],
    tempDb: match[4],
    mbtiles: match[5],
  };
}

function findLatestHeartbeat(progressEntries) {
  if (!Array.isArray(progressEntries) || progressEntries.length === 0) {
    return null;
  }
  for (let i = progressEntries.length - 1; i >= 0; i -= 1) {
    const entry = progressEntries[i] || {};
    const parsed = parseHeartbeat(entry.message || '');
    if (parsed) {
      return {
        ...parsed,
        timestamp: entry.timestamp || '',
      };
    }
  }
  return null;
}

function parseOverallProgress(message) {
  if (!message || typeof message !== 'string') return null;
  const match = OVERALL_PROGRESS_RE.exec(message.trim());
  if (!match) return null;
  const progressPercent = Number.parseFloat(match[4]);
  return {
    variant: match[1],
    completedFeatures: Number.parseInt(match[2], 10) || 0,
    totalFeatures: Number.parseInt(match[3], 10) || 0,
    progressPercent: Number.isFinite(progressPercent) ? progressPercent : 0,
    eta: match[5],
  };
}

function parseCurrentLayerProgress(message) {
  if (!message || typeof message !== 'string') return null;
  const match = CURRENT_LAYER_PROGRESS_RE.exec(message.trim());
  if (!match) return null;
  return {
    variant: match[1],
    layer: match[2],
    progressPercent: Number.parseInt(match[3], 10) || 0,
  };
}

function findLatestParsed(progressEntries, parser) {
  if (!Array.isArray(progressEntries) || progressEntries.length === 0) {
    return null;
  }
  for (let i = progressEntries.length - 1; i >= 0; i -= 1) {
    const entry = progressEntries[i] || {};
    const parsed = parser(entry.message || '');
    if (parsed) {
      return {
        ...parsed,
        timestamp: entry.timestamp || '',
      };
    }
  }
  return null;
}

export default function MapsList() {
  const { protocols, normalized, jobs, loading, error, reload, deleteDataset, reconvertDataset } = useProtocols();
  const [url, setUrl] = useState('');
  const [submitError, setSubmitError] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const fileInputRef = useRef(null);
  const [localPath, setLocalPath] = useState('');
  const [planPreview, setPlanPreview] = useState(null);
  const [planError, setPlanError] = useState(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [cancelingJobs, setCancelingJobs] = useState({});
  const [deletingJobs, setDeletingJobs] = useState({});
  const [reconverting, setReconverting] = useState({});
  const [generating, setGenerating] = useState({});

  async function requestPlanPreview(payload) {
    setPlanLoading(true);
    setPlanError(null);
    try {
      const data = await previewProfilePlan(payload);
      setPlanPreview(data);
    } catch (nextError) {
      setPlanError(nextError.message);
      setPlanPreview(null);
    } finally {
      setPlanLoading(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!url.trim()) {
      return;
    }

    setSubmitError(null);
    try {
      await normalizeFromUrl(url.trim());
      setUrl('');
      setPlanPreview(null);
      await reload();
    } catch (nextError) {
      setSubmitError(nextError);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (!uploadFile) return;

    try {
      await normalizeFromUpload(uploadFile, null);
      setUploadFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setPlanPreview(null);
      await reload();
    } catch (nextError) {
      setSubmitError(nextError);
    }
  }

  async function handleLocalFile(event) {
    event.preventDefault();
    if (!localPath.trim()) {
      return;
    }

    try {
      await normalizeFromLocalFile(localPath.trim());
      setLocalPath('');
      setPlanPreview(null);
      await reload();
    } catch (nextError) {
      setSubmitError(nextError);
    }
  }

  async function handleGenerateFromNormalized(item) {
    const datasetName = item.name;
    setGenerating((prev) => ({ ...prev, [datasetName]: true }));
    try {
      await generateFromNormalized(datasetName, item.gpkg_path);
      await reload();
    } catch (nextError) {
      window.alert(nextError.message);
    } finally {
      setGenerating((prev) => ({ ...prev, [datasetName]: false }));
    }
  }

  async function handleDelete(name) {
    if (!window.confirm(`Delete dataset "${name}"?`)) {
      return;
    }

    try {
      await deleteDataset(name);
      await reload();
    } catch (nextError) {
      window.alert(nextError.message);
    }
  }

  // Rebuild the maps from the saved profile and source. The current maps stay in place the whole time: the API writes the new archives
  // beside the old ones and restores the old protocol and profile if the job fails or is cancelled, so nothing is deleted here.
  async function handleReconvert(name) {
    if (!window.confirm(
      `Rerun the conversion of "${name}"?\n\n`
      + 'GDAL will rebuild Standard, Dense-4 and Dense-16 MVT/MLT archives from the saved profile. The current Standard map stays available while it runs, '
      + 'and is kept if the rerun fails or is cancelled. This can take a while.',
    )) {
      return;
    }
    setReconverting((prev) => ({ ...prev, [name]: true }));
    try {
      await reconvertDataset(name);
      await reload();
    } catch (nextError) {
      window.alert(nextError.message);
    } finally {
      setReconverting((prev) => ({ ...prev, [name]: false }));
    }
  }

  async function handleCancelJob(name) {
    setCancelingJobs((prev) => ({ ...prev, [name]: true }));
    try {
      await cancelDatasetJob(name);
      await reload();
    } catch (nextError) {
      window.alert(nextError.message);
    } finally {
      setCancelingJobs((prev) => ({ ...prev, [name]: false }));
    }
  }

  async function handleDeleteJobData(name) {
    setDeletingJobs((prev) => ({ ...prev, [name]: true }));
    try {
      await deleteDataset(name);
      await reload();
    } catch (nextError) {
      window.alert(nextError.message);
    } finally {
      setDeletingJobs((prev) => ({ ...prev, [name]: false }));
    }
  }

  if (loading) {
    return <div className="maps-list-loading">Loading protocols...</div>;
  }

  if (error) {
    return (
      <div className="maps-list-error">
        <p>Failed to load protocols: {error.message}</p>
        <button onClick={reload}>Retry</button>
      </div>
    );
  }

  return (
    <div className="maps-list">
      <section className="maps-import-panel">
        <div className="maps-import-header"><h2>Stage A: Normalize Source</h2></div>
        <p>Prepare one canonical GPKG per dataset. Stage B generation runs separately.</p>
        <form className="maps-import-form" onSubmit={handleSubmit}>
          <input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://download.geofabrik.de/europe/monaco-latest.osm.pbf" />
          <button type="button" className="btn-secondary" disabled={!url.trim() || planLoading} onClick={() => requestPlanPreview({ url: url.trim() })}>Preview plan</button>
          <button type="submit" className="btn-submit">Normalize</button>
        </form>
        <form className="maps-import-form" onSubmit={handleUpload}>
          <input ref={fileInputRef} type="file" onChange={(e) => setUploadFile(e.target.files[0] || null)} className="maps-file-input" />
          <button type="button" className="btn-secondary" disabled={!uploadFile || planLoading} onClick={() => requestPlanPreview({ filename: uploadFile?.name || '' })}>Preview plan</button>
          <button type="submit" className="btn-submit" disabled={!uploadFile}>Upload + Normalize</button>
        </form>
        <form className="maps-import-form" onSubmit={handleLocalFile}>
          <input type="text" value={localPath} onChange={(event) => setLocalPath(event.target.value)} placeholder="/path/to/source.zip" className="maps-path-input" />
          <button type="button" className="btn-secondary" disabled={!localPath.trim() || planLoading} onClick={() => requestPlanPreview({ file_path: localPath.trim() })}>Preview plan</button>
          <button type="submit" className="btn-submit" disabled={!localPath.trim()}>Normalize</button>
        </form>
        {submitError ? <p className="maps-import-error">{submitError.message}</p> : null}
        {planLoading ? <p className="maps-import-note">Planning profile...</p> : null}
        {planError ? <p className="maps-import-error">{planError}</p> : null}
        {planPreview?.plan ? (
          <div className="plan-preview">
            <div className="plan-preview-header">
              <strong>Profile plan preview</strong>
              <span>{planPreview.dataset_name}</span>
            </div>
            <div className="plan-preview-meta">
              <span>format: {planPreview.source_format}</span>
              <span>kind: {planPreview.plan.source_kind}</span>
              <span>zoom: {planPreview.plan.output?.min_zoom ?? '—'}-{planPreview.plan.output?.max_zoom ?? '—'}</span>
              <span>rule: {planPreview.plan.rule_name || 'auto-default'}</span>
            </div>
            <div className="plan-preview-layers">
              {(planPreview.plan.tile_layers || []).slice(0, 8).map((layer) => (
                <div key={layer.id} className="plan-preview-layer">
                  <div className="plan-preview-layer-top">
                    <strong>{layer.id}</strong>
                    <span>{layer.zoom?.min ?? 0}-{layer.zoom?.max ?? 14}</span>
                  </div>
                  <div className="plan-preview-layer-body">
                    src: {(layer.source_layers || []).join(', ') || '—'}
                  </div>
                </div>
              ))}
              {(planPreview.plan.tile_layers || []).length > 8 ? (
                <div className="plan-preview-more">and {(planPreview.plan.tile_layers || []).length - 8} more layer(s)</div>
              ) : null}
            </div>
          </div>
        ) : null}
      </section>

      <section className="maps-import-panel">
        <div className="maps-import-header"><h2>Stage B: Generate MVT/MLT</h2></div>
        <p>Select a normalized dataset and run Standard / Dense4 / Dense16 generation.</p>
        {normalized.length === 0 ? (
          <p className="maps-import-note">No normalized bundles yet. Run Stage A first.</p>
        ) : (
          <div className="normalized-list">
            {normalized.map((item) => {
              const busy = hasActiveJob(jobs, item.name) || !!generating[item.name];
              return (
                <div key={item.name} className="normalized-card">
                  <div className="normalized-card-top">
                    <strong>{item.name}</strong>
                    <span>{formatSize(item.gpkg_size_bytes)}</span>
                  </div>
                  <div className="normalized-card-path">{item.gpkg_path}</div>
                  <div className="normalized-card-actions">
                    <button
                      type="button"
                      className="btn-submit"
                      disabled={!item.gpkg_exists || busy}
                      onClick={() => handleGenerateFromNormalized(item)}
                    >
                      {busy ? 'Running...' : 'Generate Stage B'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {jobs.length > 0 ? (
        <section className="maps-jobs-panel">
          <div className="maps-jobs-header">
            <h2>Import Jobs</h2>
            <button onClick={reload} className="btn-refresh">Refresh</button>
          </div>
          <div className="jobs-list">
            {jobs.map((job) => {
              const progress = Array.isArray(job.progress) ? job.progress : [];
              const recentProgress = progress.slice(-8);
              const heartbeat = findLatestHeartbeat(progress);
              const overallProgress = findLatestParsed(progress, parseOverallProgress);
              const currentLayerProgress = findLatestParsed(progress, parseCurrentLayerProgress);
              const canCancel = ['queued', 'running', 'canceling'].includes(job.status);
              const isCanceling = !!cancelingJobs[job.name] || job.status === 'canceling';
              const canCleanup = !canCancel;
              const isDeleting = !!deletingJobs[job.name];

              return (
                <div key={`${job.name}-${job.created_at}`} className="job-card">
                  <div className="job-card-top">
                    <strong>{job.name}</strong>
                    <span className={`job-status job-status-${job.status}`}>{job.status}</span>
                  </div>
                  <div className="job-url">{job.url}</div>

                  {canCancel ? (
                    <div className="job-actions">
                      <button
                        type="button"
                        className="btn-cancel-job"
                        onClick={() => handleCancelJob(job.name)}
                        disabled={isCanceling}
                      >
                        {isCanceling ? 'Cancelling...' : 'Cancel job'}
                      </button>
                    </div>
                  ) : canCleanup ? (
                    <div className="job-actions">
                      <button
                        type="button"
                        className="btn-cleanup-job"
                        onClick={() => handleDeleteJobData(job.name)}
                        disabled={isDeleting}
                      >
                        {isDeleting ? 'Deleting...' : 'Delete data'}
                      </button>
                    </div>
                  ) : null}

                  {job.stage ? <div className="job-stage">Stage: {job.stage}</div> : null}

                  {heartbeat ? (
                    <div className="job-live-telemetry">
                      <div className="job-live-header">Live telemetry</div>
                      <div className="job-live-grid">
                        <span>step</span><strong>{heartbeat.label}</strong>
                        <span>elapsed</span><strong>{heartbeat.elapsed}</strong>
                        <span>rss</span><strong>{heartbeat.rss}</strong>
                        <span>temp DB</span><strong>{heartbeat.tempDb}</strong>
                        <span>MBTiles</span><strong>{heartbeat.mbtiles}</strong>
                        {heartbeat.timestamp ? <span>at</span> : null}
                        {heartbeat.timestamp ? <strong>{heartbeat.timestamp}</strong> : null}
                      </div>
                    </div>
                  ) : null}

                  {overallProgress ? (
                    <div className="job-progress-bars">
                      <div className="job-progress-bar-head">
                        <span>Overall Progress ({overallProgress.variant})</span>
                        <strong>{overallProgress.progressPercent.toFixed(2)}%</strong>
                      </div>
                      <div className="job-progress-bar-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={overallProgress.progressPercent}>
                        <div className="job-progress-bar-fill" style={{ width: `${Math.max(0, Math.min(100, overallProgress.progressPercent))}%` }} />
                      </div>
                      <div className="job-progress-bar-meta">
                        <span>features: {overallProgress.completedFeatures} / {overallProgress.totalFeatures}</span>
                        <span>eta: {overallProgress.eta}</span>
                      </div>
                    </div>
                  ) : null}

                  {currentLayerProgress ? (
                    <div className="job-progress-bars layer-progress">
                      <div className="job-progress-bar-head">
                        <span>Current Layer ({currentLayerProgress.variant}): {currentLayerProgress.layer}</span>
                        <strong>{currentLayerProgress.progressPercent}%</strong>
                      </div>
                      <div className="job-progress-bar-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={currentLayerProgress.progressPercent}>
                        <div className="job-progress-bar-fill layer-fill" style={{ width: `${Math.max(0, Math.min(100, currentLayerProgress.progressPercent))}%` }} />
                      </div>
                    </div>
                  ) : null}

                  {recentProgress.length > 0 ? (
                    <div className="job-progress">
                      {recentProgress.map((entry, index) => (
                        <div key={`${job.name}-${entry.timestamp || index}`} className="job-progress-line">
                          <span className="job-progress-stage">{entry.stage || 'step'}</span>
                          <span>{entry.message || ''}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {job.error ? <div className="job-error">{job.error}</div> : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {protocols.length === 0 ? (
        <div className="maps-list-empty">
          <h2>No maps converted yet</h2>
          <p>Run Stage A normalization first, then launch Stage B generation from normalized bundles.</p>
        </div>
      ) : (
        <>
          <div className="maps-list-header">
            <h2>Converted Maps ({protocols.length})</h2>
            <button onClick={reload} className="btn-refresh">Refresh</button>
          </div>
          <table className="maps-table">
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Status</th>
                <th>Profile</th>
                <th>MVT</th>
                <th>MLT</th>
                <th>Topology</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {protocols.map((p) => {
                const ds = p.dataset || {};
                const outputs = p.outputs || {};
                const topology = p.topology || {};
                const busy = !!reconverting[ds.id] || hasActiveJob(jobs, ds.id);

                return (
                  <tr key={ds.id}>
                    <td className="td-name">
                      <Link to={`/map/${encodeURIComponent(ds.id)}`}>
                        {ds.title || ds.id}
                      </Link>
                    </td>
                    <td>
                      <span className={`job-status job-status-${p.validation?.research_ready ? 'completed' : 'partial'}`}>{p.validation?.research_ready ? 'ready' : 'partial'}</span>
                    </td>
                    <td>{p.profile?.origin || '—'}</td>
                    <td>{formatSize(outputs.mvt?.archive_bytes)}</td>
                    <td className="td-highlight">{formatSize(outputs.mlt?.archive_bytes)}</td>
                    <td>{topology.layer_count ?? '—'} layers</td>
                    <td>
                      <Link to={`/map/${encodeURIComponent(ds.id)}`} className="btn-view">
                        View
                      </Link>
                      <button
                        type="button"
                        onClick={() => handleReconvert(ds.id)}
                        className="btn-rerun"
                        disabled={busy}
                        title={busy ? 'A conversion for this dataset is already running' : 'Rebuild the GDAL Standard and Dense experiment archives from the saved profile, keeping the current Standard map'}
                      >
                        {busy ? 'Converting…' : 'Rerun'}
                      </button>
                      <button onClick={() => handleDelete(ds.id)} className="btn-delete">Delete</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

