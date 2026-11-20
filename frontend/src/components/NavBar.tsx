import { NavLink, useLocation } from 'react-router-dom';
import { useStylistPath } from '../lib/navMemory';
import { IoCameraOutline, IoShirtOutline, IoSparklesOutline, IoSunnyOutline } from 'react-icons/io5';
import { ModeBadge } from './ModeBadge';
import { Wordmark } from './Wordmark';

const LINKS = [
  { to: '/', label: 'Stylist', icon: IoSparklesOutline },
  { to: '/today', label: 'Today', icon: IoSunnyOutline },
  { to: '/closet', label: 'Closet', icon: IoShirtOutline },
  { to: '/scan', label: 'Scan', icon: IoCameraOutline },
];

export function NavBar({ overlay = false, dark = true }: { overlay?: boolean; dark?: boolean }) {
  const light = overlay && dark;
  const stylistPath = useStylistPath();
  const { pathname } = useLocation();
  return (
    <header
      className={`${overlay ? 'absolute inset-x-0 top-0 z-20' : 'relative border-b border-line-subtle bg-paper'} ${
        light ? 'bg-gradient-to-b from-black/55 via-black/25 to-transparent pb-6' : ''
      }`}
    >
      <nav className="mx-auto flex max-w-[1280px] items-center justify-between px-5 py-5 md:px-10">
        <NavLink to="/" aria-label="Home" className={light ? 'drop-shadow-[0_2px_8px_rgba(0,0,0,0.5)]' : ''}>
          <Wordmark light={light} size={24} />
        </NavLink>
        <div className="flex items-center gap-3">
        <span className="hidden md:block">
          <ModeBadge light={light} />
        </span>
        <div className={`flex gap-1 rounded-full p-1 ${
          light ? 'border border-white/20 bg-black/35 shadow-lg backdrop-blur-xl' : overlay ? 'glass' : 'bg-sand-100'
        }`}>
          {LINKS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to === '/' ? stylistPath : to}
              end
              className={({ isActive: active }) => {
                const isActive = to === '/' ? pathname === '/' : active;
                return (
                `flex items-center gap-1.5 rounded-full px-2.5 py-2 text-[13px] font-semibold transition-colors sm:px-3.5 ${
                  isActive
                    ? 'bg-forest text-white'
                    : light
                      ? 'text-white hover:bg-white/15'
                      : 'text-ink hover:bg-white'
                }`
                );
              }}
            >
              <Icon size={16} />
              <span className="hidden sm:inline">{label}</span>
            </NavLink>
          ))}
        </div>
        </div>
      </nav>
    </header>
  );
}
