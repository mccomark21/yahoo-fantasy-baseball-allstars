/* The diamond — drawn entirely in SVG (no photo dependency).
   viewBox 1320×660 — a broadcast wide-shot; the field box is locked to this
   aspect ratio so the percentage-based card coordinates in positions.ts line
   up exactly. Home plate sits bottom-center, second base up the middle, the
   outfield grass spreads wide so the field fills a landscape screen. */

const W = 1320;
const H = 660;
const STRIPE_COUNT = 9;

export default function Field() {
  // Infield base coordinates (also referenced by the basepaths + bases).
  // A true square diamond, centered: equal horizontal/vertical reach from the
  // mid-point so it never reads as stretched in the wider box.
  const home = { x: 660, y: 556 };
  const first = { x: 824, y: 392 };
  const second = { x: 660, y: 228 };
  const third = { x: 496, y: 392 };
  const moundY = 408;

  return (
    <svg
      className="field-svg"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Baseball diamond under stadium lights"
      focusable="false"
    >
      <defs>
        <radialGradient id="turf" cx="50%" cy="38%" r="82%">
          <stop offset="0%" stopColor="oklch(0.33 0.05 150)" />
          <stop offset="45%" stopColor="oklch(0.27 0.044 150)" />
          <stop offset="100%" stopColor="oklch(0.16 0.032 150)" />
        </radialGradient>
        <radialGradient id="skin" cx="50%" cy="60%" r="60%">
          <stop offset="0%" stopColor="oklch(0.49 0.062 60)" />
          <stop offset="100%" stopColor="oklch(0.4 0.056 55)" />
        </radialGradient>
        <radialGradient id="moundGrad" cx="50%" cy="42%" r="60%">
          <stop offset="0%" stopColor="oklch(0.52 0.062 60)" />
          <stop offset="100%" stopColor="oklch(0.41 0.055 55)" />
        </radialGradient>
        <radialGradient id="fieldVignette" cx="50%" cy="36%" r="78%">
          <stop offset="40%" stopColor="oklch(0 0 0 / 0)" />
          <stop offset="100%" stopColor="oklch(0.05 0.006 255 / 0.92)" />
        </radialGradient>
        <linearGradient id="poleLight" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="oklch(0.98 0.02 95 / 0.22)" />
          <stop offset="100%" stopColor="oklch(0.98 0.02 95 / 0)" />
        </linearGradient>
      </defs>

      {/* Turf */}
      <rect x="0" y="0" width={W} height={H} fill="url(#turf)" />

      {/* Broadcast mow stripes — subtle alternating bands */}
      <g opacity="0.5">
        {Array.from({ length: STRIPE_COUNT }).map((_, i) =>
          i % 2 === 0 ? (
            <rect
              key={i}
              x={(W / STRIPE_COUNT) * i}
              y="0"
              width={W / STRIPE_COUNT}
              height={H}
              fill="oklch(0.3 0.05 150)"
              opacity="0.5"
            />
          ) : null
        )}
      </g>

      {/* Outfield fence + warning track — a wide arc over second base */}
      <path
        d="M 70 408 A 770 770 0 0 1 1250 408"
        fill="none"
        stroke="oklch(0.46 0.06 60)"
        strokeWidth="22"
        strokeLinecap="round"
        opacity="0.55"
      />
      <path
        d="M 70 408 A 770 770 0 0 1 1250 408"
        fill="none"
        stroke="oklch(0.7 0.03 120 / 0.5)"
        strokeWidth="2.5"
      />

      {/* Infield skin (dirt) — diamond around the basepaths */}
      <path
        d={`M ${home.x} ${home.y + 22}
            L ${first.x + 30} ${first.y}
            L ${second.x} ${second.y - 34}
            L ${third.x - 30} ${third.y}
            Z`}
        fill="url(#skin)"
      />

      {/* Grass infield cut inside the skin — calm, flat green (no hot center) */}
      <path
        d={`M ${home.x} ${home.y - 26}
            L ${first.x - 40} ${first.y}
            L ${second.x} ${second.y + 40}
            L ${third.x + 40} ${third.y}
            Z`}
        fill="oklch(0.285 0.044 150)"
      />

      {/* Foul lines — home plate out to the foul poles */}
      <g stroke="oklch(0.95 0.015 110 / 0.7)" strokeWidth="3" strokeLinecap="round">
        <line x1={home.x} y1={home.y} x2="96" y2="150" />
        <line x1={home.x} y1={home.y} x2="1224" y2="150" />
      </g>

      {/* Basepaths */}
      <path
        d={`M ${home.x} ${home.y} L ${first.x} ${first.y} L ${second.x} ${second.y} L ${third.x} ${third.y} Z`}
        fill="none"
        stroke="oklch(0.5 0.062 58)"
        strokeWidth="11"
      />

      {/* Pitcher's mound */}
      <circle cx={home.x} cy={moundY} r="46" fill="url(#moundGrad)" />
      <rect x={home.x - 9} y={moundY - 4} width="18" height="6" rx="1.5" fill="oklch(0.95 0.01 100 / 0.85)" />

      {/* Bases */}
      <g>
        {[first, second, third].map((b, i) => (
          <rect
            key={i}
            x={b.x - 9}
            y={b.y - 9}
            width="18"
            height="18"
            rx="2.5"
            fill="oklch(0.96 0.008 100)"
            transform={`rotate(45 ${b.x} ${b.y})`}
          />
        ))}
        {/* Home plate */}
        <path
          d={`M ${home.x - 11} ${home.y - 6}
              L ${home.x + 11} ${home.y - 6}
              L ${home.x + 11} ${home.y + 3}
              L ${home.x} ${home.y + 13}
              L ${home.x - 11} ${home.y + 3} Z`}
          fill="oklch(0.96 0.008 100)"
        />
      </g>

      {/* Floodlight pours from the arc-light towers (top corners) */}
      <path d="M 210 -40 L 620 0 L 360 330 L 110 180 Z" fill="url(#poleLight)" />
      <path d="M 1110 -40 L 700 0 L 960 330 L 1210 180 Z" fill="url(#poleLight)" />

      {/* Stadium vignette to seat the field in the dark */}
      <rect x="0" y="0" width={W} height={H} fill="url(#fieldVignette)" />
    </svg>
  );
}
