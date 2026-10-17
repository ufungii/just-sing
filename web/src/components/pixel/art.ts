/*
 * Pixel art shared by several sprites, copied from the approved mockup.
 * Paths are drawn on a 1-unit grid; scale them up with a transform.
 */

/** 7x6 heart. */
export const HEART = 'M1 0h2v1h-2z M4 0h2v1h-2z M0 1h7v2h-7z M1 3h5v1h-5z M2 4h3v1h-3z M3 5h1v1h-1z';

/** 5x5 thin plus sparkle. */
export const SPARKLE_PLUS = 'M2 0h1v5h-1z M0 2h5v1h-5z';

/** 7x7 sparkle with a chunky center. */
export const SPARKLE_STAR = 'M3 0h1v7h-1z M0 3h7v1h-7z M2 2h3v3h-3z';

/** 6x7 eighth note. */
export const NOTE = 'M3 0h1v6h-1z M4 0h2v1h-2z M5 1h1v1h-1z M1 5h2v2h-2z M0 6h1v1h-1z';

/** 16x6 cloud. */
export const CLOUD = 'M5 0h4v1h-4z M3 1h10v1h-10z M1 2h14v1h-14z M0 3h16v2h-16z M1 5h14v1h-14z';

/** Mockup colors that have no design token yet. */
export const COLOR = {
  heartFaint: '#FFC2DC', // background hearts
  micFace: '#FFB3D6', // Mic-chan body
  micShine: '#FFE1EF', // Mic-chan highlight
  sparkleSky: '#7CC8FF',
  sparkleMint: '#6EE7C5',
} as const;
