import { describe, expect, it } from 'vitest';
import song from '../../../contracts/song.example.json';
import { isSpokenKorean, practicePhrases } from './practicePhrases';

describe('spoken Korean practice eligibility', () => {
  it.each([
    ['안녕 내 사랑', true], ['  안녕, 사랑!  ', true], ['', false], ['  ', false],
    ['hello', false], ['안녕 hello', false], ['사랑 123', false], ['사랑é', false],
    ['ㄱㄴ', false], ['你好', false],
  ])('%s -> %s', (text, expected) => expect(isSpokenKorean(text)).toBe(expected));

  it('keeps singing phrases but excludes them from practice when their text is unsupported', () => {
    const copy = structuredClone(song);
    const phrase = copy.phrases[0];
    copy.lines[phrase.line_index].practice_text = 'hello';
    expect(practicePhrases(copy).some(p => p.id === phrase.id)).toBe(false);
    expect(copy.phrases.some(p => p.id === phrase.id)).toBe(true);
    copy.lines[phrase.line_index].practice_text = '안녕';
    expect(practicePhrases(copy).some(p => p.id === phrase.id)).toBe(true);
  });
});
