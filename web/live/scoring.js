// Port of ml/scoring/live.py. Both implementations use the shared fixtures.
const valid = (hz) => typeof hz === "number" && Number.isFinite(hz) && hz > 0;
const cents = (a, b) => Math.abs(1200 * Math.log2(a / b));

function onsets(values, hop, offset, config) {
  const result = [];
  let previous = null;
  values.forEach((hz, i) => {
    const t = offset + i * hop;
    if (valid(hz)) {
      if (previous === null || (cents(hz, previous) >= config.onset_change_cents &&
          (!result.length || t - result.at(-1) >= config.onset_min_gap_seconds - 1e-9))) result.push(t);
      previous = hz;
    } else previous = null;
  });
  return result;
}

export function scorePhrase(reference, observations, start, end, register, latencySeconds, config) {
  if (![-12, 0, 12].includes(register)) throw new Error("Invalid register");
  const hop = reference.hop_seconds;
  const first = Math.max(0, Math.ceil(start / hop - 1e-9));
  const last = Math.min(reference.hz.length, Math.ceil(end / hop - 1e-9));
  const padding = Math.ceil(config.timing_window_seconds / hop);
  const eventFirst = Math.max(0, first - padding), eventLast = Math.min(reference.hz.length, last + padding);
  const slots = new Map();
  for (const frame of observations) {
    const t = frame.time - latencySeconds;
    const index = t >= 0 ? Math.floor(t / hop + 0.5) : -1;
    if (eventFirst <= index && index < eventLast) slots.set(index, frame.hz);
  }
  const excluded = (i) => (reference.excluded ?? []).some((r) => r.start <= i * hop && i * hop < r.end);
  const target = [], user = [];
  for (let i = first; i < last; i++) {
    const hz = excluded(i) ? null : reference.hz[i];
    target.push(valid(hz) ? hz * 2 ** (register / 12) : null);
    user.push(slots.get(i) ?? null);
  }
  const expected = target.filter(valid).length;
  if (!expected) return { status: "unavailable", pitch: null, timing: null, total: null,
                         coverage: 0, scoreable_seconds: 0, rating: null };
  let voiced = 0, credit = 0;
  target.forEach((hz, i) => {
    if (valid(hz) && valid(user[i])) {
      voiced++;
      credit += Math.max(0, Math.min(1, (config.zero_credit_cents - cents(user[i], hz)) /
                                    (config.zero_credit_cents - config.full_credit_cents)));
    }
  });
  const coverage = voiced / expected, pitch = 100 * credit / expected;
  const eventTarget = [], eventUser = [];
  for (let i = eventFirst; i < eventLast; i++) {
    eventTarget.push(excluded(i) ? null : reference.hz[i]);
    eventUser.push(excluded(i) ? null : slots.get(i) ?? null);
  }
  const wanted = onsets(eventTarget, hop, eventFirst * hop, config)
    .filter((t) => first * hop - 1e-9 <= t && t < last * hop - 1e-9);
  const actual = onsets(eventUser, hop, eventFirst * hop, config), used = new Set();
  let timingCredit = 0;
  for (const t of wanted) {
    let best = null;
    actual.forEach((other, i) => {
      const distance = Math.abs(t - other);
      if (!used.has(i) && distance <= config.timing_window_seconds && (!best || distance < best.distance)) best = { i, distance };
    });
    if (best) { used.add(best.i); timingCredit += Math.max(0, 1 - best.distance / config.timing_window_seconds); }
  }
  const timing = voiced ? wanted.length ? 100 * timingCredit / wanted.length : 100 : 0;
  const total = config.pitch_weight * pitch + (1 - config.pitch_weight) * timing;
  const rating = coverage < config.miss_coverage ? "Miss" : config.rating_bands.find(([minimum]) => total >= minimum)[1];
  return { status: "provisional", pitch, timing, total, coverage, scoreable_seconds: expected * hop,
           rating, timing_events: wanted.length };
}

export function aggregate(scores) {
  const available = scores.filter((s) => s.status !== "unavailable");
  const duration = available.reduce((sum, s) => sum + s.scoreable_seconds, 0);
  if (!duration) return { status: "unavailable", total: null, pitch: null, timing: null };
  const result = { status: "provisional" };
  for (const key of ["pitch", "timing", "total"]) result[key] = available.reduce((sum, s) => sum + s[key] * s.scoreable_seconds, 0) / duration;
  return result;
}
