const TITLE = 'JUST SING!';

/**
 * The wavy "JUST SING!" title. Each letter is stacked four times (ink, plum, rose, face)
 * at growing vertical offsets so it reads as an extruded pixel block, and each letter
 * starts its bob a little later than the one before it.
 */
export function PixelLogo() {
  return (
    <h1 className="home-logo" aria-label="Just Sing!">
      {TITLE.split('').map((ch, i) =>
        ch === ' ' ? (
          <span key={i} className="home-logo__space" aria-hidden="true" />
        ) : (
          <span key={i} className="home-logo__letter wave" aria-hidden="true" style={{ animationDelay: `${(i * 0.12).toFixed(2)}s` }}>
            <span className="home-logo__sizer">{ch}</span>
            <span className="home-logo__layer home-logo__layer--ink">{ch}</span>
            <span className="home-logo__layer home-logo__layer--plum">{ch}</span>
            <span className="home-logo__layer home-logo__layer--rose">{ch}</span>
            <span className="home-logo__layer home-logo__layer--face">{ch}</span>
          </span>
        ),
      )}
    </h1>
  );
}
