/* The span of seasons a records view draws from, shown in the control bar.

   Team Records reach back to each league's earliest reachable season, because
   their inputs (team season totals + matchups) survive Yahoo's game archival.
   The player-facing views can't: retired players are unreachable, so they stay
   2021+. That makes the two record views cover different ranges — this label
   states each view's span outright instead of letting "all-time" quietly paper
   over the asymmetry. Non-interactive: it reports scope, it doesn't filter. */
export default function SeasonRange({ lo, hi }: { lo: number; hi: number }) {
  const single = lo === hi;
  return (
    <p
      className="tv-range"
      aria-label={single ? `Seasons: ${lo}` : `Seasons: ${lo} to ${hi}`}
    >
      <span className="tv-range__key" aria-hidden="true">
        Seasons
      </span>
      <span className="tv-range__val">
        {single ? lo : `${lo}–${hi}`}
      </span>
    </p>
  );
}
