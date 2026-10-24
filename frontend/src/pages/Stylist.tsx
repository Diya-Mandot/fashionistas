import { useState, type FormEvent } from 'react';
import { IoArrowForward, IoSparklesOutline } from 'react-icons/io5';
import { GlassPanel } from '../components/GlassPanel';
import { NavBar } from '../components/NavBar';
import { HERO_IMAGE } from '../theme/brand';

const EXAMPLES = [
  {
    label: 'Seattle tech conference',
    text: "Packing for a tech conference in Seattle Tue–Thu. There's a fancy dinner Tuesday night and I want to look professional but a little edgy.",
  },
  {
    label: 'NYC weekend',
    text: 'Pack my bag for NYC this weekend: networking brunch and a Broadway show',
  },
  {
    label: 'First day, new job',
    text: 'First day at a new job Monday, rainy, want to look put-together but not stiff',
  },
];

export function Stylist() {
  const [message, setMessage] = useState('');

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    // Wired to POST /api/stylist/plan in milestone 4.
  };

  return (
    <div className="min-h-screen">
      <section className="relative isolate flex min-h-screen flex-col overflow-hidden">
        <img
          src={HERO_IMAGE}
          alt=""
          className="absolute inset-0 -z-20 h-full w-full object-cover"
        />
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-black/55 via-black/30 to-black/65" />
        <NavBar overlay />

        <div className="mx-auto flex w-full max-w-[880px] flex-1 flex-col justify-center px-5 pb-16 pt-28 md:px-10">
          <p className="type-micro mb-4 text-white/80">Context-aware stylist</p>
          <h1 className="font-display text-[40px] font-bold leading-[44px] tracking-[-1px] text-white md:text-[56px] md:leading-[60px] md:tracking-[-1.4px]">
            Tell me the plan and the vibe.
            <br />
            <span className="text-sand">I’ll pack your closet for it.</span>
          </h1>
          <p className="type-body-lg mt-4 max-w-[560px] text-white/80">
            An agent checks the weather, reads your calendar and searches your closet, then lets a
            decision engine score every outfit.
          </p>

          <GlassPanel radius="hero" className="mt-10 p-3 md:p-4">
            <form onSubmit={onSubmit}>
              <label htmlFor="prompt" className="sr-only">
                Where are you headed?
              </label>
              <textarea
                id="prompt"
                rows={3}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Where are you headed? Tell me the plan and the vibe."
                className="w-full resize-none rounded-card bg-white/85 px-5 py-4 font-sans text-[16px] leading-6 text-ink placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-emerald/60"
              />
              <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-wrap gap-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex.label}
                      type="button"
                      onClick={() => setMessage(ex.text)}
                      className="rounded-full border border-white/50 bg-white/20 px-3.5 py-1.5 text-[13px] font-semibold text-white transition-colors hover:bg-white/35"
                    >
                      {ex.label}
                    </button>
                  ))}
                </div>
                <button
                  type="submit"
                  disabled={!message.trim()}
                  className="flex items-center justify-center gap-2 rounded-full bg-forest px-6 py-3 text-[15px] font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  <IoSparklesOutline size={18} />
                  Plan my outfits
                  <IoArrowForward size={16} />
                </button>
              </div>
            </form>
          </GlassPanel>
        </div>
      </section>
    </div>
  );
}
