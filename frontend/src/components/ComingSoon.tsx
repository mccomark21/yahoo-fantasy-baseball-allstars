import BallIcon from "./BallIcon";

/* Placeholder for views built in later phases (Positional Races, Team Records,
   Player Records). Reachable by direct hash URL; the nav tabs still read "Soon"
   until each view ships. */
export default function ComingSoon({ title }: { title: string }) {
  return (
    <div className="state state--soon" role="status">
      <BallIcon />
      <h2>{title}</h2>
      <p>This view is on deck — coming in a future inning.</p>
    </div>
  );
}
