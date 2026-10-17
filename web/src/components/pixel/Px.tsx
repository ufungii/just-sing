/** One flat-colored pixel path. `fill` may be a CSS variable like `var(--ink)`. */
export function Px({ d, fill, transform }: { d: string; fill: string; transform?: string }) {
  // Fill goes through `style` so CSS variables resolve in every browser.
  return <path d={d} transform={transform} style={{ fill }} />;
}
