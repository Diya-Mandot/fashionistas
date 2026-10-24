import type { ReactNode } from 'react';
import { HERO_IMAGE } from '../theme/brand';
import { BackButton } from './BackButton';
import { NavBar } from './NavBar';

/** Soft photo backdrop + glass nav, like the capstone's Closet/Insights screens. */
export function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen">
      <div className="fixed inset-0 -z-10">
        <img src={HERO_IMAGE} alt="" className="h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-[rgba(250,249,246,0.55)] via-[rgba(250,249,246,0.82)] to-paper" />
      </div>
      <NavBar overlay dark={false} />
      <main className="mx-auto max-w-[1280px] px-5 pb-20 pt-24 md:px-10">
        <div className="mb-5">
          <BackButton />
        </div>
        {children}
      </main>
    </div>
  );
}
