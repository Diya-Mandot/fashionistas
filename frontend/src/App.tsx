import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Placeholder } from './pages/Placeholder';
import { Stylist } from './pages/Stylist';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Stylist />} />
        <Route path="/closet" element={<Placeholder title="Closet" />} />
        <Route path="/scan" element={<Placeholder title="Scan" />} />
      </Routes>
    </BrowserRouter>
  );
}
