use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::RwLock;

/// Data protected by timestamp comparison — only newer updates are accepted.
pub struct TimestampedData {
    pub data: String,
    pub update_ts: i64,
}

impl TimestampedData {
    fn new() -> Self {
        Self {
            data: String::new(),
            update_ts: 0,
        }
    }

    /// Update data only if the incoming timestamp is >= current.
    /// Returns true if the update was accepted.
    pub fn try_update(&mut self, ts: i64, data: String) -> bool {
        if ts >= self.update_ts {
            self.update_ts = ts;
            self.data = data;
            true
        } else {
            false
        }
    }
}

/// All market data state held in memory.
pub struct MarketState {
    // Kline arrays — HashMap keyed by symbol index, replacing fixed-size C++ arrays
    pub kline_1m: HashMap<u16, String>,
    pub kline_1m_agg: HashMap<u16, String>,

    // Timestamped data
    pub tick: TimestampedData,
    pub position: TimestampedData,
    pub account_balance: TimestampedData,

    // No timestamp protection
    pub ban_symbols: String,

    // Metadata
    pub symbol_count: u16,
    pub index_1m: u16,
    pub index_special_1m: u16,

    // Pre-joined cache for aggregated 1m kline (rebuilt on every write)
    pub kline_1m_agg_joined: String,

    // Server start time for uptime calculation
    pub start_time: Instant,

    // Active connection count
    pub active_connections: u32,
}

impl Default for MarketState {
    fn default() -> Self {
        Self::new()
    }
}

impl MarketState {
    pub fn new() -> Self {
        Self {
            kline_1m: HashMap::new(),
            kline_1m_agg: HashMap::new(),
            tick: TimestampedData::new(),
            position: TimestampedData::new(),
            account_balance: TimestampedData::new(),
            ban_symbols: String::new(),
            symbol_count: 0,
            index_1m: 0,
            index_special_1m: 0,
            kline_1m_agg_joined: String::new(),
            start_time: Instant::now(),
            active_connections: 0,
        }
    }

    /// Rebuild the pre-joined aggregated 1m kline string.
    /// Called after every `kline_1m_agg` update, matching C++ behavior.
    pub fn rebuild_agg_cache(&mut self) {
        let mut parts = Vec::with_capacity(self.symbol_count as usize);
        for i in 0..self.symbol_count {
            parts.push(
                self.kline_1m_agg
                    .get(&i)
                    .map_or("", std::string::String::as_str),
            );
        }
        self.kline_1m_agg_joined = parts.join("@");
    }

    /// Build the "A" command response: all 1m klines joined by "@".
    pub fn build_all_kline_1m(&self) -> String {
        let mut parts = Vec::with_capacity(self.symbol_count as usize);
        for i in 0..self.symbol_count {
            parts.push(
                self.kline_1m
                    .get(&i)
                    .map_or("", std::string::String::as_str),
            );
        }
        parts.join("@")
    }

    /// Build the "B" command response: aggregated snapshot.
    pub fn build_snapshot(&self) -> String {
        format!(
            "{}*{}*{}*{}*{}",
            self.kline_1m_agg_joined,
            self.tick.data,
            self.position.data,
            self.ban_symbols,
            self.account_balance.data,
        )
    }

    /// Advance the 1m round-robin index and return the new value.
    pub fn next_index_1m(&mut self) -> u16 {
        self.index_1m += 1;
        if self.index_1m >= self.symbol_count {
            self.index_1m = 0;
        }
        self.index_1m
    }

    /// Advance the special 1m round-robin index and return the new value.
    pub fn next_index_special_1m(&mut self) -> u16 {
        self.index_special_1m += 1;
        if self.index_special_1m >= self.symbol_count {
            self.index_special_1m = 0;
        }
        self.index_special_1m
    }
}

pub type SharedState = Arc<RwLock<MarketState>>;
