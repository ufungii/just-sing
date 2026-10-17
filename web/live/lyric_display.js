export function lyricDisplay(line, romanized) {
  if (!romanized || !line.romanized?.trim()) return { text: line.text, words: line.words };
  const tokens = line.romanized.trim().split(/\s+/u);
  // Never guess romanized word timing if a manually edited line changes spacing.
  const words = tokens.length === line.words.length
    ? line.words.map((word, i) => ({ ...word, text: tokens[i] })) : [];
  return { text: line.romanized, words };
}
