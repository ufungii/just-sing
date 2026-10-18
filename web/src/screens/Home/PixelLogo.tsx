/** The title's two rows: a smaller JUST on top of a big SING!. */
const ROWS = [
  { text: 'JUST', size: 'just' },
  { text: 'SING!', size: 'sing' },
] as const;

/**
 * The wavy "JUST / SING!" title. Each letter is stacked four times (ink, plum, rose, face)
 * at growing vertical offsets so it reads as an extruded pixel block, and each letter
 * starts its bob a little later than the one before it, carrying on from JUST into SING!.
 */
export function PixelLogo() {
  let i = 0; // letter count across both rows, for the staggered wave
  return (
    <h1 className="home-logo" aria-label="Just Sing!">
      {ROWS.map((row) => (
        <span key={row.text} className={`home-logo__row home-logo__row--${row.size}`} aria-hidden="true">
          {row.text.split('').map((ch) => {
            const delay = `${(i++ * 0.12).toFixed(2)}s`;
            return (
              <span key={ch + i} className="home-logo__letter wave" style={{ animationDelay: delay }}>
                <span className="home-logo__sizer">{ch}</span>
                <span className="home-logo__layer home-logo__layer--ink">{ch}</span>
                <span className="home-logo__layer home-logo__layer--plum">{ch}</span>
                <span className="home-logo__layer home-logo__layer--rose">{ch}</span>
                <span className="home-logo__layer home-logo__layer--face">{ch}</span>
              </span>
            );
          })}
        </span>
      ))}
    </h1>
  );
}
