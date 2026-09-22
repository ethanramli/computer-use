use crate::motion::{PythonRandom, movement_time};
use std::time::{SystemTime, UNIX_EPOCH};

pub const MODES: &[&str] = &["human", "compatibility", "native"];
const GAPS: [((f64, f64), f64); 3] = [
    ((0.0, 0.1), 0.377),
    ((0.1, 0.2), 0.5492),
    ((0.2, 0.4), 0.0738),
];

pub fn gaps_for(mode: &str, text: &str) -> Result<Vec<f64>, String> {
    let seed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as i64;
    gaps_for_seed(mode, text, seed)
}

/// Seeded form for deterministic parity tests; normal human timing uses a fresh clock seed.
pub fn gaps_for_seed(mode: &str, text: &str, seed: i64) -> Result<Vec<f64>, String> {
    match mode {
        "native" => Ok(vec![0.0; text.chars().count()]),
        "compatibility" => Ok(vec![0.01; text.chars().count()]),
        "human" => {
            let mut rng = PythonRandom::new(seed);
            Ok(text.chars().map(|_| next_type_gap(&mut rng)).collect())
        }
        _ => Err(format!(
            "unknown timing mode: {mode} (use human, compatibility, native)"
        )),
    }
}

pub fn movement_seconds(
    mode: &str,
    start: (i64, i64),
    end: (i64, i64),
    target_size: f64,
) -> Result<f64, String> {
    if !MODES.contains(&mode) {
        return Err(format!(
            "unknown timing mode: {mode} (use human, compatibility, native)"
        ));
    }
    if mode == "native" {
        return Ok(0.0);
    }
    let distance = ((end.0 - start.0) as f64).hypot((end.1 - start.1) as f64);
    Ok(movement_time(distance, target_size).max(0.0))
}

fn next_type_gap(rng: &mut PythonRandom) -> f64 {
    let draw = rng.random();
    let mut cumulative = 0.0;
    for ((low, high), probability) in GAPS {
        cumulative += probability;
        if draw <= cumulative {
            return low + (high - low) * rng.random();
        }
    }
    let (low, high) = GAPS[2].0;
    low + (high - low) * rng.random()
}
