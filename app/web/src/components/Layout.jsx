import { Link } from 'react-router-dom';
import './Layout.css';

export default function Layout({ children }) {
  return (
    <div className="layout">
      <header className="layout-header">
        <Link to="/" className="logo">
          <h1>GEOMAPS</h1>
          <span className="subtitle">Structure-first tile research</span>
        </Link>
        <nav>
          <Link to="/">Maps</Link>
          <Link to="/settings">Settings</Link>
        </nav>
      </header>
      <main className="layout-main">
        {children}
      </main>
    </div>
  );
}
