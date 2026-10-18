import { useState, useEffect } from 'react';

/**
 * Hook to load datasets and background jobs from the API.
 */
export function useProtocols() {
  const [protocols, setProtocols] = useState([]);
  const [normalized, setNormalized] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const { datasets, normalized: nextNormalized, jobs: nextJobs } = await loadProtocols();
        if (cancelled) return;
        setProtocols(datasets);
        setNormalized(nextNormalized || []);
        setJobs(nextJobs);
        setError(null);
      } catch (nextError) {
        if (cancelled) return;
        setError(nextError);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    load();
    const intervalId = setInterval(load, 5000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  const reload = async () => {
    setLoading(true);
    try {
      const { datasets, normalized: nextNormalized, jobs: nextJobs } = await loadProtocols();
      setProtocols(datasets);
      setNormalized(nextNormalized || []);
      setJobs(nextJobs);
      setError(null);
    } catch (nextError) {
      setError(nextError);
    } finally {
      setLoading(false);
    }
  };

  return {
    protocols,
    normalized,
    jobs,
    loading,
    error,
    reload,
    importDataset,
    normalizeFromUrl,
    normalizeFromLocalFile,
    normalizeFromUpload,
    generateFromNormalized,
    deleteDataset,
    reconvertDataset,
    cancelDatasetJob,
  };
}

/**
 * Hook to load a single protocol by dataset name.
 */
export function useProtocol(name) {
  const [protocol, setProtocol] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!name) return;
    fetch(`/api/datasets/${encodeURIComponent(name)}`)
      .then(r => {
        if (!r.ok) throw new Error(`Dataset not found: ${name}`);
        return r.json();
      })
      .then(setProtocol)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [name]);

  return { protocol, loading, error };
}

async function loadProtocols() {
  const resp = await fetch('/api/datasets');
  if (!resp.ok) {
    throw new Error('Failed to load datasets');
  }
  const data = await resp.json();
  return {
    datasets: data.datasets || [],
    normalized: data.normalized || [],
    jobs: data.jobs || [],
  };
}

export async function normalizeFromUrl(url) {
  const resp = await fetch('/api/stage-a/import', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ url }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || 'Failed to start Stage A normalization');
  return data.job;
}

export async function normalizeFromLocalFile(filePath) {
  const resp = await fetch('/api/stage-a/local-file', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ file_path: filePath }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || 'Failed to start Stage A normalization');
  return data.job;
}

export function normalizeFromUpload(file, onProgress) {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded / e.total);
      }
    };

    xhr.onload = () => {
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { data = {}; }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data.job);
      } else {
        reject(new Error(data.error || 'Upload failed'));
      }
    };

    xhr.onerror = () => reject(new Error('Upload failed — network error'));
    xhr.open('POST', '/api/stage-a/upload');
    xhr.send(formData);
  });
}

export async function generateFromNormalized(name, gpkgPath) {
  const resp = await fetch('/api/stage-b/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name, gpkg_path: gpkgPath }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || 'Failed to start Stage B generation');
  return data.job;
}

export async function importDataset(url) {
  const resp = await fetch('/api/datasets/import', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ url }),
  });

  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || 'Failed to start dataset import');
  }
  return data.job;
}

export function uploadDataset(file, onProgress) {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded / e.total);
      }
    };

    xhr.onload = () => {
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { data = {}; }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data.job);
      } else {
        reject(new Error(data.error || 'Upload failed'));
      }
    };

    xhr.onerror = () => reject(new Error('Upload failed — network error'));
    xhr.open('POST', '/api/datasets/upload');
    xhr.send(formData);
  });
}

export async function processLocalFile(filePath) {
  const resp = await fetch('/api/datasets/local-file', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ file_path: filePath }),
  });

  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || 'Failed to process local file');
  }
  return data.job;
}

export async function previewProfilePlan(payload) {
  const resp = await fetch('/api/profile-plan/preview', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload || {}),
  });

  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || 'Failed to preview profile plan');
  }
  return data;
}

export async function saveMetrics(name, renderMetrics) {
  return { saved: false, name, ignored: true };
}

export async function deleteDataset(name) {
  const resp = await fetch(`/api/datasets/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || 'Failed to delete dataset');
  }
  return data;
}

const ACTIVE_JOB_STATUSES = ['queued', 'running', 'canceling'];

/** True while a conversion job for this dataset has not finished (so a rerun would be refused). */
export function hasActiveJob(jobs, name) {
  return (jobs || []).some((job) => job.name === name && ACTIVE_JOB_STATUSES.includes(job.status));
}

/**
 * Rebuild a dataset's GDAL Standard/Dense MVT and MLT archives from its saved profile and source.
 *
 * Nothing is deleted first: the API snapshots the current protocol and profile, writes the new archives beside the old ones, and
 * puts the old protocol and profile back if the job fails or is cancelled, so the current map stays usable.
 */
export async function reconvertDataset(name) {
  const resp = await fetch(`/api/datasets/${encodeURIComponent(name)}/reconvert`, { method: 'POST' });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || 'Failed to rerun conversion');
  }
  return data.job;
}

export async function cancelDatasetJob(name) {
  const resp = await fetch(`/api/jobs/${encodeURIComponent(name)}/cancel`, {
    method: 'POST',
  });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || 'Failed to cancel job');
  }
  return data.job;
}

