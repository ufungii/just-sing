/** Pitch error in cents (positive = user sharp). Hz is the unit in all data; cents only measure error. */
export const centsBetween = (userHz: number, targetHz: number) => 1200 * Math.log2(userHz / targetHz);
