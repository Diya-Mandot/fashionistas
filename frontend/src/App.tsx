import { useLayoutEffect, useRef } from 'react';
import { BrowserRouter, useLocation } from 'react-router-dom';
import { BuyCheck } from './pages/BuyCheck';
import { Closet } from './pages/Closet';
import { Scan } from './pages/Scan';
import { Stylist } from './pages/Stylist';

type Tab = 'stylist' | 'closet' | 'scan' | 'buy';

function tabFor(pathname: string): Tab {
  if (pathname.startsWith('/closet')) return 'closet';
  if (pathname.startsWith('/scan')) return 'scan';
  if (pathname.startsWith('/buy')) return 'buy';
  return 'stylist';
}

/** All tabs stay mounted so a running plan or scan keeps going while you look elsewhere. */
function Tabs() {
  const tab = tabFor(useLocation().pathname);
  const scroll = useRef<Record<Tab, number>>({ stylist: 0, closet: 0, scan: 0, buy: 0 });
  const prev = useRef<Tab>(tab);

  useLayoutEffect(() => {
    if (prev.current === tab) return;
    scroll.current[prev.current] = window.scrollY;
    prev.current = tab;
    window.scrollTo(0, scroll.current[tab]);
  }, [tab]);

  return (
    <>
      <div hidden={tab !== 'stylist'}>
        <Stylist active={tab === 'stylist'} />
      </div>
      <div hidden={tab !== 'closet'}>
        <Closet active={tab === 'closet'} />
      </div>
      <div hidden={tab !== 'scan'}>
        <Scan />
      </div>
      <div hidden={tab !== 'buy'}>
        <BuyCheck active={tab === 'buy'} />
      </div>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Tabs />
    </BrowserRouter>
  );
}
