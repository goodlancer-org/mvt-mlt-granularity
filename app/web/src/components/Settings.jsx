import { useEffect, useState } from 'react';
import './Settings.css';

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then(setSettings)
      .catch(() => setMessage({ type: 'error', text: 'Failed to load settings.' }));
  }, []);

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      if (!res.ok) {
        const err = await res.json();
        setMessage({ type: 'error', text: err.error || 'Save failed.' });
      } else {
        setMessage({ type: 'success', text: 'Settings saved.' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error.' });
    } finally {
      setSaving(false);
    }
  }

  function set(key, value) {
    setSettings((prev) => ({ ...prev, [key]: value || null }));
  }

  if (!settings) return <div className="settings-loading">Loading settings…</div>;

  return (
    <div className="settings-page">
      <h2>Settings</h2>
      <form className="settings-form" onSubmit={handleSave}>

        <section className="settings-section">
          <h3>Conversion</h3>

          <div className="settings-field">
            <label htmlFor="tmp_dir">Temp Directory</label>
            <input
              id="tmp_dir"
              type="text"
              placeholder="(leave blank for the default)"
              value={settings.tmp_dir ?? ''}
              onChange={(e) => set('tmp_dir', e.target.value)}
            />
            <p className="settings-hint">
              GDAL writes temporary tile databases here, and legacy Planetiler tools may write large sort files here.
              If you run out of space, point this at a drive with more room,
              e.g. <code>/mnt/secondPartition/planetiler-tmp</code>. This path is inside the
              container, so you must also start the services with
              <code>PLANETILER_TMP</code> set to the same path — setting only one has no
              effect. Do not use <code>/tmp</code>.
            </p>
          </div>

          <div className="settings-row">
            <div className="settings-field">
              <label htmlFor="min_zoom">Min Zoom</label>
              <input
                id="min_zoom"
                type="number"
                min="0"
                max="22"
                value={settings.min_zoom ?? 0}
                onChange={(e) => set('min_zoom', parseInt(e.target.value, 10))}
              />
            </div>
            <div className="settings-field">
              <label htmlFor="max_zoom">Max Zoom</label>
              <input
                id="max_zoom"
                type="number"
                min="0"
                max="22"
                value={settings.max_zoom ?? 14}
                onChange={(e) => set('max_zoom', parseInt(e.target.value, 10))}
              />
            </div>
            <div className="settings-field">
              <label htmlFor="java_heap">Java Heap</label>
              <input
                id="java_heap"
                type="text"
                placeholder="2g"
                value={settings.java_heap ?? ''}
                onChange={(e) => set('java_heap', e.target.value)}
              />
              <p className="settings-hint">e.g. <code>2g</code>, <code>4g</code></p>
            </div>
          </div>
        </section>

        {message && (
          <div className={`settings-message settings-message--${message.type}`}>
            {message.text}
          </div>
        )}

        <button className="settings-save-btn" type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save settings'}
        </button>
      </form>
    </div>
  );
}
