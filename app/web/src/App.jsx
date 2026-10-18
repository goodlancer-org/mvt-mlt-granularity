import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import MapsList from './components/MapsList';
import MapDetail from './components/MapDetail';
import Settings from './components/Settings';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<MapsList />} />
        <Route path="/map/:name" element={<MapDetail />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Layout>
  );
}
