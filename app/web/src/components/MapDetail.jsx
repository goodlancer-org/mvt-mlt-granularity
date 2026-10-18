import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useProtocol } from '../hooks/useProtocol';
import MapPreview from './MapPreview';
import ProtocolView from './ProtocolView';
import './MapDetail.css';

export default function MapDetail() {
  const { name } = useParams();
  const { protocol, loading, error } = useProtocol(name);
  const [encoding, setEncoding] = useState('mlt');

  if (loading) {
    return <div className="map-detail-loading">Loading...</div>;
  }

  if (error || !protocol) {
    return (
      <div className="map-detail-error">
        <p>Failed to load protocol for "{name}"</p>
        <Link to="/">Back to list</Link>
      </div>
    );
  }

  return (
    <div className="map-detail">
      <div className="map-detail-header">
        <Link to="/" className="back-link">&larr; Back</Link>
        <div className="map-detail-title-block">
          <h2>{protocol.dataset?.title || protocol.dataset?.id || name}</h2>
          <span className="timestamp">{protocol.profile?.origin || 'unknown profile'}</span>
        </div>
      </div>

      <div className="map-detail-grid">
        <div className="map-detail-left">
          <div className="map-preview-toolbar">
            <span>Preview encoding</span>
            <div className="map-preview-toggle">
              <button type="button" className={encoding === 'mvt' ? 'active' : ''} onClick={() => setEncoding('mvt')}>MVT</button>
              <button type="button" className={encoding === 'mlt' ? 'active' : ''} onClick={() => setEncoding('mlt')}>MLT</button>
            </div>
          </div>
          <MapPreview protocol={protocol} encoding={encoding} />
        </div>
        <div className="map-detail-right">
          <ProtocolView protocol={protocol} />
        </div>
      </div>
    </div>
  );
}
