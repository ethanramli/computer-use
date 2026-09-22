use std::f64::consts::LN_2;

const MT_N: usize = 624;
const MT_M: usize = 397;
const UPPER_MASK: u32 = 0x8000_0000;
const LOWER_MASK: u32 = 0x7fff_ffff;
const MATRIX_A: u32 = 0x9908_b0df;

/// Python-compatible MT19937 draws used by the existing seeded path model.
pub(crate) struct PythonRandom {
    state: [u32; MT_N],
    index: usize,
}

impl PythonRandom {
    pub(crate) fn new(seed: i64) -> Self {
        let mut key = seed.unsigned_abs();
        let mut words = Vec::new();
        while key != 0 {
            words.push(key as u32);
            key >>= 32;
        }
        if words.is_empty() {
            words.push(0);
        }

        let mut rng = Self::from_word(19_650_218);
        let mut i = 1;
        let mut j = 0;
        for _ in 0..MT_N.max(words.len()) {
            let previous = rng.state[i - 1];
            rng.state[i] = (rng.state[i] ^ ((previous ^ (previous >> 30)).wrapping_mul(1_664_525)))
                .wrapping_add(words[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= MT_N {
                rng.state[0] = rng.state[MT_N - 1];
                i = 1;
            }
            if j >= words.len() {
                j = 0;
            }
        }
        for _ in 0..MT_N - 1 {
            let previous = rng.state[i - 1];
            rng.state[i] = (rng.state[i]
                ^ ((previous ^ (previous >> 30)).wrapping_mul(1_566_083_941)))
            .wrapping_sub(i as u32);
            i += 1;
            if i >= MT_N {
                rng.state[0] = rng.state[MT_N - 1];
                i = 1;
            }
        }
        rng.state[0] = UPPER_MASK;
        rng.index = MT_N;
        rng
    }

    fn from_word(seed: u32) -> Self {
        let mut state = [0; MT_N];
        state[0] = seed;
        for i in 1..MT_N {
            state[i] = 1_812_433_253_u32
                .wrapping_mul(state[i - 1] ^ (state[i - 1] >> 30))
                .wrapping_add(i as u32);
        }
        Self { state, index: MT_N }
    }

    fn next_u32(&mut self) -> u32 {
        if self.index >= MT_N {
            for i in 0..MT_N {
                let y = (self.state[i] & UPPER_MASK) | (self.state[(i + 1) % MT_N] & LOWER_MASK);
                self.state[i] = self.state[(i + MT_M) % MT_N]
                    ^ (y >> 1)
                    ^ if y & 1 == 0 { 0 } else { MATRIX_A };
            }
            self.index = 0;
        }
        let mut y = self.state[self.index];
        self.index += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^= y >> 18;
        y
    }

    fn getrandbits(&mut self, bits: u32) -> u32 {
        self.next_u32() >> (32 - bits)
    }

    fn below(&mut self, exclusive: u32) -> u32 {
        let bits = u32::BITS - exclusive.leading_zeros();
        loop {
            let value = self.getrandbits(bits);
            if value < exclusive {
                return value;
            }
        }
    }

    fn randint(&mut self, low: i32, high: i32) -> i32 {
        low + self.below((high - low + 1) as u32) as i32
    }

    pub(crate) fn random(&mut self) -> f64 {
        let a = self.next_u32() >> 5;
        let b = self.next_u32() >> 6;
        ((a as u64 * 67_108_864 + b as u64) as f64) / 9_007_199_254_740_992.0
    }
}

/// Seed-compatible cubic Bezier path used by Python's `desktop.move.points`.
pub fn points(start: (i64, i64), end: (i64, i64), seed: i64, steps: usize) -> Vec<(i64, i64)> {
    if steps == 0 {
        return Vec::new();
    }
    let mut rng = PythonRandom::new(seed);
    let span = ((end.0 - start.0) as f64).hypot((end.1 - start.1) as f64);
    let scale = (span.max(8.0) / 80.0).min(1.0);
    let mut offset = || {
        let magnitude = rng.randint(20, 40);
        let signed = if rng.randint(0, 1) == 1 {
            -magnitude
        } else {
            magnitude
        };
        (signed as f64 * scale).round_ties_even() as i64
    };
    let p1 = (start.0 + offset(), start.1 + offset());
    let p2 = (end.0 + offset(), end.1 + offset());

    let mut zones = Vec::new();
    for index in 0..20 {
        if rng.random() < 0.15 {
            zones.push((index as f64 * 0.05, (index + 1) as f64 * 0.05));
        }
    }
    let offsets: Vec<_> = zones
        .iter()
        .map(|_| {
            let x = rng.randint(1, 5) * if rng.randint(0, 1) == 1 { -1 } else { 1 };
            let y = rng.randint(1, 5) * if rng.randint(0, 1) == 1 { -1 } else { 1 };
            (x, y)
        })
        .collect();

    let mut path = Vec::with_capacity(steps);
    for index in 1..=steps {
        let t = index as f64 / steps as f64 * 4.5;
        let warped = logistic(t.clamp(0.0, 4.5));
        let normalized = warped / logistic(4.5);
        let mut point = (
            bezier(start.0, p1.0, p2.0, end.0, normalized),
            bezier(start.1, p1.1, p2.1, end.1, normalized),
        );
        for ((z0, z1), (ox, oy)) in zones.iter().zip(offsets.iter()) {
            if *z0 <= normalized && normalized <= *z1 {
                let progress = (normalized - z0) / (z1 - z0);
                let factor = if progress < 0.5 {
                    progress * 2.0
                } else {
                    1.0 - (progress - 0.5) * 2.0
                };
                point.0 += (*ox as f64 * factor).round_ties_even() as i64;
                point.1 += (*oy as f64 * factor).round_ties_even() as i64;
                break;
            }
        }
        path.push(point);
    }
    *path.last_mut().expect("steps is nonzero") = end;
    path
}

fn logistic(x: f64) -> f64 {
    2.0 / (1.0 + (-x).exp()) - 1.0
}

fn bezier(p0: i64, p1: i64, p2: i64, p3: i64, t: f64) -> i64 {
    let t1 = 1.0 - t;
    (t1.powi(3) * p0 as f64
        + 3.0 * t * t1.powi(2) * p1 as f64
        + 3.0 * t1 * t.powi(2) * p2 as f64
        + t.powi(3) * p3 as f64)
        .round_ties_even() as i64
}

/// Python-compatible Fitts-law duration. Callers clamp negative time to zero.
pub fn movement_time(distance: f64, target_size: f64) -> f64 {
    let d = distance.max(1.0);
    let width = target_size.max(1.0);
    0.5500 + 0.1276 * ((2.0 * d / width).ln() / LN_2)
}
