#![forbid(unsafe_code)]

use abc_core::{
    ActivityFingerprint, DeliveryState, ProgressSupervisor, SupervisorConfig, handoff_safety,
};
use std::io::{self, BufRead, Write};

fn main() {
    if let Err(error) = run() {
        eprintln!("abc-supervisor: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let stdin = io::stdin();
    let mut supervisor: Option<ProgressSupervisor> = None;

    for line in stdin.lock().lines() {
        let line = line.map_err(|error| error.to_string())?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if trimmed == "quit" {
            break;
        }

        let mut fields = trimmed.split_whitespace();
        match fields.next().unwrap_or_default() {
            "start" => {
                let now_ms = parse_u64(fields.next(), "now_ms")?;
                let fingerprint = parse_fingerprint(&mut fields)?;
                supervisor = Some(ProgressSupervisor::new(
                    now_ms,
                    fingerprint,
                    SupervisorConfig::default(),
                ));
                println!("READY");
                io::stdout().flush().map_err(|error| error.to_string())?;
            }
            "observe" => {
                let now_ms = parse_u64(fields.next(), "now_ms")?;
                let fingerprint = parse_fingerprint(&mut fields)?;
                let delivery = DeliveryState::parse(fields.next().unwrap_or("ERROR"));
                let supervisor = supervisor
                    .as_mut()
                    .ok_or_else(|| "observe received before start".to_owned())?;
                let state = supervisor.observe(now_ms, fingerprint, delivery);
                let safety = handoff_safety(state, delivery);
                println!(
                    "STATE {} idle_ms={} threshold_ms={} may_read={} may_write={} remote_may_resume={}",
                    state.as_str(),
                    now_ms.saturating_sub(supervisor.last_progress_ms()),
                    supervisor.idle_threshold_ms(),
                    safety.may_read,
                    safety.may_write_same_workspace,
                    safety.remote_may_resume,
                );
                io::stdout().flush().map_err(|error| error.to_string())?;
            }
            other => return Err(format!("unknown command: {other}")),
        }
    }

    Ok(())
}

fn parse_fingerprint<'a>(
    fields: &mut impl Iterator<Item = &'a str>,
) -> Result<ActivityFingerprint, String> {
    Ok(ActivityFingerprint {
        steps: parse_u64(fields.next(), "steps")?,
        response_bytes: parse_u64(fields.next(), "response_bytes")?,
        tool_events: parse_u64(fields.next(), "tool_events")?,
        error_events: parse_u64(fields.next(), "error_events")?,
    })
}

fn parse_u64(value: Option<&str>, name: &str) -> Result<u64, String> {
    value
        .ok_or_else(|| format!("missing {name}"))?
        .parse::<u64>()
        .map_err(|error| format!("invalid {name}: {error}"))
}
