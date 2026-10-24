import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Closet } from './pages/Closet';
import { Scan } from './pages/Scan';
import { Stylist } from './pages/Stylist';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Stylist />} />
        <Route path="/closet" element={<Closet />} />
        <Route path="/scan" element={<Scan />} />
      </Routes>
    </BrowserRouter>
  );
}
