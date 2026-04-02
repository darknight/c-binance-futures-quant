use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use tokio::net::TcpListener;
use tokio::sync::RwLock;
use tokio_tungstenite::tungstenite::Message;

use ws_server::handler::handle_message;
use ws_server::protocol;
use ws_server::state::MarketState;

/// Start a test server on an ephemeral port using the real handler/protocol/state code.
/// Returns the address and a shared state handle.
async fn start_test_server() -> (SocketAddr, Arc<RwLock<MarketState>>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let state = Arc::new(RwLock::new(MarketState::new()));
    let state_clone = state.clone();

    tokio::spawn(async move {
        loop {
            let Ok((stream, _peer)) = listener.accept().await else {
                break;
            };
            let state = state_clone.clone();
            tokio::spawn(async move {
                let Ok(ws_stream) = tokio_tungstenite::accept_async(stream).await else {
                    return;
                };

                let (mut write, mut read) = ws_stream.split();

                while let Some(Ok(msg)) = read.next().await {
                    if let Message::Text(text) = msg {
                        let parsed = protocol::parse(&text);
                        if let Some(response) = handle_message(parsed, &state).await
                            && write.send(Message::Text(response.into())).await.is_err()
                        {
                            break;
                        }
                    }
                }
            });
        }
    });

    (addr, state)
}

/// Connect a WebSocket client to the test server.
async fn connect(
    addr: SocketAddr,
) -> (
    futures_util::stream::SplitSink<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        Message,
    >,
    futures_util::stream::SplitStream<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
    >,
) {
    let url = format!("ws://127.0.0.1:{}", addr.port());
    let (ws, _) = tokio_tungstenite::connect_async(&url).await.unwrap();
    ws.split()
}

async fn send_and_recv(
    write: &mut futures_util::stream::SplitSink<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        Message,
    >,
    read: &mut futures_util::stream::SplitStream<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
    >,
    msg: &str,
) -> String {
    write
        .send(Message::Text(msg.to_string().into()))
        .await
        .unwrap();
    match tokio::time::timeout(Duration::from_secs(5), read.next()).await {
        Ok(Some(Ok(Message::Text(t)))) => t.to_string(),
        other => panic!("unexpected response: {other:?}"),
    }
}

async fn send_no_response(
    write: &mut futures_util::stream::SplitSink<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        Message,
    >,
    msg: &str,
) {
    write
        .send(Message::Text(msg.to_string().into()))
        .await
        .unwrap();
    tokio::time::sleep(Duration::from_millis(50)).await;
}

// ============ TESTS ============

#[tokio::test]
async fn test_empty_snapshot() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    let resp = send_and_recv(&mut w, &mut r, "B").await;
    assert_eq!(resp, "****");
}

#[tokio::test]
async fn test_set_symbol_count_and_kline_1m() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    // Set symbol count to 3
    send_no_response(&mut w, "bbboiyfpdufiyuyu003").await;

    // Write kline_1m for index 0, 1, 2
    send_no_response(&mut w, "sjaiyhsaoyosauio000kline_data_0").await;
    send_no_response(&mut w, "sjaiyhsaoyosauio001kline_data_1").await;
    send_no_response(&mut w, "sjaiyhsaoyosauio002kline_data_2").await;

    // Read all 1m klines (A command)
    let resp = send_and_recv(&mut w, &mut r, "A").await;
    assert_eq!(resp, "kline_data_0@kline_data_1@kline_data_2");
}

#[tokio::test]
async fn test_aggregated_kline_and_snapshot() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    // Set symbol count to 2
    send_no_response(&mut w, "bbboiyfpdufiyuyu002").await;

    // Write aggregated klines
    send_no_response(&mut w, "sajoiyfpdufiyiry000agg_kline_0").await;
    send_no_response(&mut w, "sajoiyfpdufiyiry001agg_kline_1").await;

    // Write tick data (13-digit timestamp + data)
    send_no_response(&mut w, "sjaoihsoaitowljd1707123456000tick_data_here").await;

    // Write position data
    send_no_response(&mut w, "gggoihsoaitowljd1707123456100pos_data_here").await;

    // Write ban symbols
    send_no_response(&mut w, "abcoihsoaitowljdBTCUSDT,ETHUSDT").await;

    // Write balance
    send_no_response(&mut w, "fdsoihsoaitowljd1707123455000balance_123").await;

    // Get snapshot (B command)
    let resp = send_and_recv(&mut w, &mut r, "B").await;
    assert_eq!(
        resp,
        "agg_kline_0@agg_kline_1*tick_data_here*pos_data_here*BTCUSDT,ETHUSDT*balance_123"
    );
}

#[tokio::test]
async fn test_timestamp_protection_tick() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    // Write tick with ts=1000000000000
    send_no_response(&mut w, "sjaoihsoaitowljd1000000000000new_tick").await;

    // Try to write tick with older ts — should be rejected
    send_no_response(&mut w, "sjaoihsoaitowljd0999999999999old_tick").await;

    // Write with equal ts — should be accepted (>= semantics)
    send_no_response(&mut w, "sjaoihsoaitowljd1000000000000equal_tick").await;

    let resp = send_and_recv(&mut w, &mut r, "B").await;
    let parts: Vec<&str> = resp.split('*').collect();
    assert_eq!(parts[1], "equal_tick");
}

#[tokio::test]
async fn test_timestamp_protection_position() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    send_no_response(&mut w, "gggoihsoaitowljd2000000000000pos_new").await;
    send_no_response(&mut w, "gggoihsoaitowljd1999999999999pos_old").await;

    let resp = send_and_recv(&mut w, &mut r, "E").await;
    assert_eq!(resp, r#"{"s":"y","d":"pos_new","i":"E"}"#);
}

#[tokio::test]
async fn test_timestamp_protection_balance() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    send_no_response(&mut w, "fdsoihsoaitowljd3000000000000bal_new").await;
    send_no_response(&mut w, "fdsoihsoaitowljd2999999999999bal_old").await;

    let resp = send_and_recv(&mut w, &mut r, "B").await;
    let parts: Vec<&str> = resp.split('*').collect();
    assert_eq!(parts[4], "bal_new");
}

#[tokio::test]
async fn test_round_robin_index_f() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    send_no_response(&mut w, "bbboiyfpdufiyuyu003").await;

    // F: 1, 2, 0, 1, ...
    assert_eq!(send_and_recv(&mut w, &mut r, "F").await, "1");
    assert_eq!(send_and_recv(&mut w, &mut r, "F").await, "2");
    assert_eq!(send_and_recv(&mut w, &mut r, "F").await, "0");
    assert_eq!(send_and_recv(&mut w, &mut r, "F").await, "1");
}

#[tokio::test]
async fn test_round_robin_index_g() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    send_no_response(&mut w, "bbboiyfpdufiyuyu002").await;

    // G: 1, 0, 1, 0, ...
    assert_eq!(send_and_recv(&mut w, &mut r, "G").await, "1");
    assert_eq!(send_and_recv(&mut w, &mut r, "G").await, "0");
    assert_eq!(send_and_recv(&mut w, &mut r, "G").await, "1");
}

#[tokio::test]
async fn test_get_position_e_command() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    send_no_response(
        &mut w,
        r#"gggoihsoaitowljd1707123456000{"symbol":"BTCUSDT"}"#,
    )
    .await;

    let resp = send_and_recv(&mut w, &mut r, "E").await;
    // The server does simple string concatenation (like C++), no escaping
    assert_eq!(resp, r#"{"s":"y","d":"{"symbol":"BTCUSDT"}","i":"E"}"#);
}

#[tokio::test]
async fn test_unknown_message_no_crash() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    // Unknown single char — no response
    w.send(Message::Text("X".to_string().into())).await.unwrap();

    // Server should still work
    let resp = send_and_recv(&mut w, &mut r, "B").await;
    assert_eq!(resp, "****");
}

#[tokio::test]
async fn test_ban_symbols_no_timestamp() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    send_no_response(&mut w, "abcoihsoaitowljdBTC,ETH").await;
    send_no_response(&mut w, "abcoihsoaitowljdDOGE").await;

    let resp = send_and_recv(&mut w, &mut r, "B").await;
    let parts: Vec<&str> = resp.split('*').collect();
    assert_eq!(parts[3], "DOGE");
}

#[tokio::test]
async fn test_status_command() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    send_no_response(&mut w, "bbboiyfpdufiyuyu005").await;

    let resp = send_and_recv(&mut w, &mut r, "S").await;
    let v: serde_json::Value = serde_json::from_str(&resp).unwrap();
    assert_eq!(v["symbol_count"], 5);
    assert!(v["uptime_secs"].as_u64().is_some());
}

#[tokio::test]
async fn test_multiple_clients_share_state() {
    let (addr, _state) = start_test_server().await;

    // Client 1 writes data
    let (mut w1, mut _r1) = connect(addr).await;
    send_no_response(&mut w1, "bbboiyfpdufiyuyu002").await;
    send_no_response(&mut w1, "sjaoihsoaitowljd1707123456000shared_tick").await;

    // Client 2 reads it
    let (mut w2, mut r2) = connect(addr).await;
    let resp = send_and_recv(&mut w2, &mut r2, "B").await;
    let parts: Vec<&str> = resp.split('*').collect();
    assert_eq!(parts[1], "shared_tick");
}

#[tokio::test]
async fn test_f_g_indices_shared_across_clients() {
    let (addr, _state) = start_test_server().await;

    let (mut w1, mut r1) = connect(addr).await;
    send_no_response(&mut w1, "bbboiyfpdufiyuyu003").await;

    // Client 1 advances F index
    assert_eq!(send_and_recv(&mut w1, &mut r1, "F").await, "1");

    // Client 2 should continue from where client 1 left off
    let (mut w2, mut r2) = connect(addr).await;
    assert_eq!(send_and_recv(&mut w2, &mut r2, "F").await, "2");
    assert_eq!(send_and_recv(&mut w2, &mut r2, "F").await, "0");
}

#[tokio::test]
async fn test_e_response_wraps_position_in_json() {
    let (addr, _state) = start_test_server().await;
    let (mut w, mut r) = connect(addr).await;

    // Empty position
    let resp = send_and_recv(&mut w, &mut r, "E").await;
    assert_eq!(resp, r#"{"s":"y","d":"","i":"E"}"#);
}
