/** Pitch error in cents (positive = user sharp). Hz is the unit in all data; cents only measure error. */
export const centsBetween = (userHz: number, targetHz: number) => 1200 * Math.log2(userHz / targetHz);

/** Round half to even, like Python's round(): frame indices must agree with the reference engine on ties (10.25 / 0.02 = 512.5). */
export function roundHalfEven(x: number): number {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}
