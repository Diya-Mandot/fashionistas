import { NavLink } from 'react-router-dom';
import { IoCameraOutline, IoShirtOutline, IoSparklesOutline } from 'react-icons/io5';
import { ModeBadge } from './ModeBadge';
import { Wordmark } from './Wordmark';

const LINKS = [
  { to: '/', label: 'Stylist', icon: IoSparklesOutline },
  { to: '/closet', label: 'Closet', icon: IoShirtOutline },
  { to: '/scan', label: 'Scan', icon: IoCameraOutline },
];

export function NavBar({ overlay = false, dark = true }: { overlay?: boolean; dark?: boolean }) {
  const light = overlay && dark;
  return (
    <header
      className={`${overlay ? 'absolute inset-x-0 top-0 z-20' : 'relative border-b border-line-subtle bg-paper'}`}
    >
      <nav className="mx-auto flex max-w-[1280px] items-center justify-between px-5 py-5 md:px-10">
        <NavLink to="/" aria-label="Home">
          <Wordmark light={light} size={24} />
        </NavLink>
        <div className="flex items-center gap-3">
        <span className="hidden md:block">
          <ModeBadge light={light} />
        </span>
        <div className={`flex gap-1 rounded-full p-1 ${overlay ? 'glass' : 'bg-sand-100'}`}>
          {LINKS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end
              className={({ isActive }) =>
                `flex items-center gap-1.5 rounded-full px-3.5 py-2 text-[13px] font-semibold transition-colors ${
                  isActive
                    ? 'bg-forest text-white'
                    : light
                      ? 'text-white/90 hover:bg-white/15'
                      : 'text-ink hover:bg-white'
                }`
              }
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
