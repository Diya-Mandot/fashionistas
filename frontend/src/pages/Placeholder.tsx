import { NavBar } from '../components/NavBar';

export function Placeholder({ title }: { title: string }) {
  return (
    <div className="min-h-screen">
      <NavBar />
      <main className="mx-auto max-w-[1280px] px-5 py-12 md:px-10">
        <p className="type-micro mb-2">Coming soon</p>
        <h1 className="type-display-lg">{title}</h1>
      </main>
    </div>
  );
}
