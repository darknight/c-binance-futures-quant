/// Parsed client message.
#[derive(Debug)]
pub enum ClientMessage {
    // Read commands (single character)
    GetSnapshot,        // B
    GetAllKline1m,      // A
    GetPosition,        // E
    NextIndex1m,        // F
    NextIndexSpecial1m, // G
    GetStatus,          // S (new)

    // Write commands (16-byte prefix + data)
    UpdateKline1m { index: u16, data: String },
    UpdateKline1mAgg { index: u16, data: String },
    UpdateTick { ts: i64, data: String },
    UpdatePosition { ts: i64, data: String },
    UpdateBalance { ts: i64, data: String },
    UpdateBanSymbols { data: String },
    SetSymbolCount { count: u16 },

    Unknown,
}

// Legacy 16-byte magic prefixes
const PREFIX_KLINE_1M: &str = "sjaiyhsaoyosauio";
const PREFIX_KLINE_1M_AGG: &str = "sajoiyfpdufiyiry";
const PREFIX_TICK: &str = "sjaoihsoaitowljd";
const PREFIX_POSITION: &str = "gggoihsoaitowljd";
const PREFIX_BAN: &str = "abcoihsoaitowljd";
const PREFIX_BALANCE: &str = "fdsoihsoaitowljd";
const PREFIX_SYMBOL_COUNT: &str = "bbboiyfpdufiyuyu";

/// Parse a raw WebSocket text message into a `ClientMessage`.
pub fn parse(msg: &str) -> ClientMessage {
    if msg.is_empty() {
        return ClientMessage::Unknown;
    }

    // Single-character read commands
    if msg.len() == 1 {
        return match msg {
            "B" => ClientMessage::GetSnapshot,
            "A" => ClientMessage::GetAllKline1m,
            "E" => ClientMessage::GetPosition,
            "F" => ClientMessage::NextIndex1m,
            "G" => ClientMessage::NextIndexSpecial1m,
            "S" => ClientMessage::GetStatus,
            _ => ClientMessage::Unknown,
        };
    }

    // Write commands require at least 19 chars (16 prefix + 3 data minimum)
    // matching C++ check: clientToServerMsg.size() >= 19
    if msg.len() < 19 {
        return ClientMessage::Unknown;
    }

    let prefix = &msg[..16];
    let value = &msg[16..];

    match prefix {
        PREFIX_KLINE_1M => {
            let index = value[..3].parse::<u16>().unwrap_or(0);
            ClientMessage::UpdateKline1m {
                index,
                data: value[3..].to_string(),
            }
        }
        PREFIX_KLINE_1M_AGG => {
            let index = value[..3].parse::<u16>().unwrap_or(0);
            ClientMessage::UpdateKline1mAgg {
                index,
                data: value[3..].to_string(),
            }
        }
        PREFIX_TICK => {
            let ts = value[..13].parse::<i64>().unwrap_or(0);
            ClientMessage::UpdateTick {
                ts,
                data: value[13..].to_string(),
            }
        }
        PREFIX_POSITION => {
            let ts = value[..13].parse::<i64>().unwrap_or(0);
            ClientMessage::UpdatePosition {
                ts,
                data: value[13..].to_string(),
            }
        }
        PREFIX_BAN => ClientMessage::UpdateBanSymbols {
            data: value.to_string(),
        },
        PREFIX_BALANCE => {
            let ts = value[..13].parse::<i64>().unwrap_or(0);
            ClientMessage::UpdateBalance {
                ts,
                data: value[13..].to_string(),
            }
        }
        PREFIX_SYMBOL_COUNT => {
            let count = value[..3].parse::<u16>().unwrap_or(0);
            ClientMessage::SetSymbolCount { count }
        }
        _ => ClientMessage::Unknown,
    }
}
