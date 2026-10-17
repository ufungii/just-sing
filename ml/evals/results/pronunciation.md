# Pronunciation baselines: evals

12 Korean phrases synthesized with MMS-TTS (clean, single speaker). A = faster-whisper small + jamo comparison. B = kresnik wav2vec2 CTC forced alignment.
**Limits:** TTS speech, no human speakers, no fluent reviewer. This shows each scorer can tell right text from wrong text and find a swapped word; it does not validate accent or phoneme quality.

## Right text vs wrong text (AUC; 0.5 = chance, 1.0 = perfect)

| Condition | A auc | B auc | A matched / mismatched | B matched / mismatched |
|---|---|---|---|---|
| clean | 1.000 | 0.998 | 0.93 / 0.19 | 0.64 / 0.06 |
| noise 20 dB SNR | 1.000 | 0.996 | 0.96 / 0.19 | 0.52 / 0.04 |
| noise 10 dB SNR | 1.000 | 0.979 | 0.92 / 0.19 | 0.38 / 0.04 |
| noise 5 dB SNR | 1.000 | 0.955 | 0.88 / 0.18 | 0.29 / 0.04 |
| noise 0 dB SNR | 1.000 | 0.793 | 0.90 / 0.18 | 0.16 / 0.04 |
| speed x0.8 | 1.000 | 0.946 | 0.92 / 0.19 | 0.34 / 0.05 |
| speed x1.25 | 1.000 | 0.950 | 0.83 / 0.19 | 0.28 / 0.04 |

## Does the scorer flag the swapped word? (clean audio)

39 cases (one word of the expected text replaced). Top-1 hit rate; random guessing would be about 0.31.

| A | B |
|---|---|
| 0.97 | 0.87 |

## What each model heard (clean)

| Expected | A (whisper) | B (wav2vec2 greedy) |
|---|---|---|
| 안녕하세요 만나서 반갑습니다 | 안녕하세요. 만나서 반갑습니다. | 안님한 세요 만나서 판가칩니다 |
| 오늘 날씨가 정말 좋아요 | 오늘 날씨가 정말 좋아요 | 오늘날 시가 정말 초하요 |
| 나는 너를 사랑해 | 나는 너를 산해 | 나는 노 산해 동  제다 |
| 우리 함께 노래해요 | 우리 함께 노래해요. | 우리 함께 도래해요 |
| 보고 싶어요 매일 매일 | 고고 싶어요. 매일 매일. | 고 싶어요 마메 |
| 사랑이 뭐길래 이렇게 아파 | 사랑이 모길라에 이렇게 왔다 | 사랑이 뭐라의 이렇게 다 |
| 별이 빛나는 밤에 | 피어시 빛나는 밤에 | 계월이 핀나는 밤에 |
| 내 마음을 받아줘요 | 내 마음을 받아 둬요 | 랜 마음을 받아돼요 |
| 다시 한번 말해줘요 | 다시 한 번 말해줘요 | 다시 한번 말에 줘요 |
| 너무너무 행복해요 | 너무너무 행복해요 | 너무 어무 행복하요 |
| 나와 함께 춤을 춰요 | 나와 함께 춤을 춰요 | 나와 함께 숨을 어요 |
| 영원히 널 기억할게 | 영원히 널 기억할기 | 이억뭐니 인노을 뒤억할게 |
