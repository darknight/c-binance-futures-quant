use crate::protocol::ClientMessage;
use crate::state::SharedState;
use serde_json::json;
use tracing::{debug, warn};

/// Handle a parsed client message and return an optional response string.
#[allow(clippy::too_many_lines)]
pub async fn handle_message(msg: ClientMessage, state: &SharedState) -> Option<String> {
    match msg {
        ClientMessage::GetSnapshot => {
            let st = state.read().await;
            Some(st.build_snapshot())
        }

        ClientMessage::GetAllKline1m => {
            let st = state.read().await;
            Some(st.build_all_kline_1m())
        }

        ClientMessage::GetPosition => {
            let st = state.read().await;
            let resp = format!(r#"{{"s":"y","d":"{}","i":"E"}}"#, st.position.data);
            Some(resp)
        }

        ClientMessage::NextIndex1m => {
            let mut st = state.write().await;
            let idx = st.next_index_1m();
            Some(idx.to_string())
        }

        ClientMessage::NextIndexSpecial1m => {
            let mut st = state.write().await;
            let idx = st.next_index_special_1m();
            Some(idx.to_string())
        }

        ClientMessage::GetStatus => {
            let st = state.read().await;
            let status = json!({
                "symbol_count": st.symbol_count,
                "active_connections": st.active_connections,
                "tick_update_ts": st.tick.update_ts,
                "position_update_ts": st.position.update_ts,
                "balance_update_ts": st.account_balance.update_ts,
                "uptime_secs": st.start_time.elapsed().as_secs(),
            });
            Some(status.to_string())
        }

        ClientMessage::UpdateKline1m { index, data } => {
            debug!(index, "kline_1m updated");
            let mut st = state.write().await;
            st.kline_1m.insert(index, data);
            None
        }

        ClientMessage::UpdateKline1mAgg { index, data } => {
            debug!(index, "kline_1m_agg updated");
            let mut st = state.write().await;
            st.kline_1m_agg.insert(index, data);
            st.rebuild_agg_cache();
            None
        }

        ClientMessage::UpdateTick { ts, data } => {
            let mut st = state.write().await;
            if st.tick.try_update(ts, data) {
                debug!("tick updated ts={}", ts);
            } else {
                warn!(
                    "stale tick rejected incoming_ts={} current_ts={}",
                    ts, st.tick.update_ts
                );
            }
            None
        }

        ClientMessage::UpdatePosition { ts, data } => {
            let mut st = state.write().await;
            if st.position.try_update(ts, data) {
                debug!("position updated ts={}", ts);
            } else {
                warn!(
                    "stale position rejected incoming_ts={} current_ts={}",
                    ts, st.position.update_ts
                );
            }
            None
        }

        ClientMessage::UpdateBalance { ts, data } => {
            let mut st = state.write().await;
            if st.account_balance.try_update(ts, data) {
                debug!("balance updated ts={}", ts);
            } else {
                warn!(
                    "stale balance rejected incoming_ts={} current_ts={}",
                    ts, st.account_balance.update_ts
                );
            }
            None
        }

        ClientMessage::UpdateBanSymbols { data } => {
            debug!("ban_symbols updated");
            let mut st = state.write().await;
            st.ban_symbols = data;
            None
        }

        ClientMessage::SetSymbolCount { count } => {
            debug!("symbol_count set to {}", count);
            let mut st = state.write().await;
            st.symbol_count = count;
            None
        }

        ClientMessage::Unknown => {
            debug!("unknown message ignored");
            None
        }
    }
}
