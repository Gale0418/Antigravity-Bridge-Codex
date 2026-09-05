#![forbid(unsafe_code)]

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SupervisorState {
    Active,
    Quiet,
    Suspect,
    Stalled,
    InputRequired,
    DeliveryUnknown,
    Done,
}

impl SupervisorState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Active => "ACTIVE",
            Self::Quiet => "QUIET",
            Self::Suspect => "SUSPECT",
            Self::Stalled => "STALLED",
            Self::InputRequired => "INPUT_REQUIRED",
            Self::DeliveryUnknown => "DELIVERY_UNKNOWN",
            Self::Done => "DONE",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeliveryState {
    NotSent,
    Preparing,
    InProgress,
    Delivering,
    AcceptedPending,
    InputRequired,
    DeliveryUnknown,
    Completed,
    Error,
}

impl DeliveryState {
    pub fn parse(value: &str) -> Self {
        match value.trim().to_ascii_uppercase().as_str() {
            "NOT_SENT" => Self::NotSent,
            "PREPARING" => Self::Preparing,
            "IN_PROGRESS" => Self::InProgress,
            "DELIVERING" => Self::Delivering,
            "ACCEPTED_PENDING" => Self::AcceptedPending,
            "INPUT_REQUIRED" => Self::InputRequired,
            "DELIVERY_UNKNOWN" => Self::DeliveryUnknown,
            "COMPLETED" => Self::Completed,
            _ => Self::Error,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct ActivityFingerprint {
    pub steps: u64,
    pub response_bytes: u64,
    pub tool_events: u64,
    pub error_events: u64,
}

impl ActivityFingerprint {
    pub const fn progressed_from(self, previous: Self) -> bool {
        self.steps > previous.steps
            || self.response_bytes > previous.response_bytes
            || self.tool_events > previous.tool_events
            || self.error_events > previous.error_events
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SupervisorConfig {
    pub min_idle_ms: u64,
    pub max_idle_ms: u64,
    pub suspect_fraction: f64,
    pub ewma_alpha: f64,
    pub gap_multiplier: f64,
    pub gap_padding_ms: u64,
}

impl Default for SupervisorConfig {
    fn default() -> Self {
        Self {
            min_idle_ms: 90_000,
            max_idle_ms: 600_000,
            suspect_fraction: 0.65,
            ewma_alpha: 0.35,
            gap_multiplier: 4.0,
            gap_padding_ms: 30_000,
        }
    }
}

#[derive(Debug, Clone)]
pub struct ProgressSupervisor {
    config: SupervisorConfig,
    started_ms: u64,
    last_progress_ms: u64,
    previous: ActivityFingerprint,
    ewma_gap_ms: Option<f64>,
    has_progress: bool,
}

impl ProgressSupervisor {
    pub fn new(started_ms: u64, initial: ActivityFingerprint, config: SupervisorConfig) -> Self {
        Self {
            config,
            started_ms,
            last_progress_ms: started_ms,
            previous: initial,
            ewma_gap_ms: None,
            has_progress: false,
        }
    }

    pub fn idle_threshold_ms(&self) -> u64 {
        let dynamic = self
            .ewma_gap_ms
            .map(|gap| gap * self.config.gap_multiplier + self.config.gap_padding_ms as f64)
            .unwrap_or(self.config.min_idle_ms as f64);
        dynamic
            .round()
            .clamp(self.config.min_idle_ms as f64, self.config.max_idle_ms as f64)
            as u64
    }

    pub fn observe(
        &mut self,
        now_ms: u64,
        fingerprint: ActivityFingerprint,
        delivery: DeliveryState,
    ) -> SupervisorState {
        if delivery == DeliveryState::Completed {
            self.previous = fingerprint;
            return SupervisorState::Done;
        }
        if delivery == DeliveryState::InputRequired {
            self.previous = fingerprint;
            return SupervisorState::InputRequired;
        }
        if delivery == DeliveryState::DeliveryUnknown {
            self.previous = fingerprint;
            return SupervisorState::DeliveryUnknown;
        }

        if fingerprint.progressed_from(self.previous) {
            let gap = now_ms.saturating_sub(self.last_progress_ms) as f64;
            if self.has_progress && gap > 0.0 {
                self.ewma_gap_ms = Some(match self.ewma_gap_ms {
                    Some(previous) => {
                        self.config.ewma_alpha * gap + (1.0 - self.config.ewma_alpha) * previous
                    }
                    None => gap,
                });
            }
            self.last_progress_ms = now_ms;
            self.has_progress = true;
            self.previous = fingerprint;
            return SupervisorState::Active;
        }

        self.previous = fingerprint;
        let idle_ms = now_ms.saturating_sub(self.last_progress_ms);
        let threshold = self.idle_threshold_ms();
        if idle_ms >= threshold {
            SupervisorState::Stalled
        } else if idle_ms as f64 >= threshold as f64 * self.config.suspect_fraction {
            SupervisorState::Suspect
        } else {
            SupervisorState::Quiet
        }
    }

    pub const fn started_ms(&self) -> u64 {
        self.started_ms
    }

    pub const fn last_progress_ms(&self) -> u64 {
        self.last_progress_ms
    }

    pub const fn has_progress(&self) -> bool {
        self.has_progress
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HandoffSafety {
    pub may_read: bool,
    pub may_write_same_workspace: bool,
    pub remote_may_resume: bool,
}

pub fn handoff_safety(state: SupervisorState, delivery: DeliveryState) -> HandoffSafety {
    if matches!(
        delivery,
        DeliveryState::Preparing
            | DeliveryState::InProgress
            | DeliveryState::Delivering
            | DeliveryState::AcceptedPending
            | DeliveryState::InputRequired
            | DeliveryState::DeliveryUnknown
    ) {
        return HandoffSafety {
            may_read: true,
            may_write_same_workspace: false,
            remote_may_resume: true,
        };
    }

    match state {
        SupervisorState::Stalled if delivery == DeliveryState::NotSent => HandoffSafety {
            may_read: true,
            may_write_same_workspace: true,
            remote_may_resume: false,
        },
        SupervisorState::Done => HandoffSafety {
            may_read: true,
            may_write_same_workspace: true,
            remote_may_resume: false,
        },
        _ => HandoffSafety {
            may_read: true,
            may_write_same_workspace: false,
            remote_may_resume: delivery != DeliveryState::NotSent,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn active_progress_prevents_false_stall() {
        let mut supervisor = ProgressSupervisor::new(
            0,
            ActivityFingerprint::default(),
            SupervisorConfig::default(),
        );
        assert_eq!(
            supervisor.observe(
                80_000,
                ActivityFingerprint { steps: 1, ..ActivityFingerprint::default() },
                DeliveryState::InProgress,
            ),
            SupervisorState::Active
        );
        assert_eq!(
            supervisor.observe(
                160_000,
                ActivityFingerprint { steps: 2, tool_events: 1, ..ActivityFingerprint::default() },
                DeliveryState::InProgress,
            ),
            SupervisorState::Active
        );
        assert!(supervisor.last_progress_ms() >= 160_000);
    }

    #[test]
    fn ambiguous_delivery_never_allows_second_writer() {
        let safety = handoff_safety(SupervisorState::Stalled, DeliveryState::DeliveryUnknown);
        assert!(safety.may_read);
        assert!(!safety.may_write_same_workspace);
        assert!(safety.remote_may_resume);
    }

    #[test]
    fn not_sent_stall_can_handoff_write() {
        let safety = handoff_safety(SupervisorState::Stalled, DeliveryState::NotSent);
        assert!(safety.may_write_same_workspace);
        assert!(!safety.remote_may_resume);
    }
}
