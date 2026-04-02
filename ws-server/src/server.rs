use std::net::SocketAddr;

use futures_util::{SinkExt, StreamExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::broadcast;
use tokio_tungstenite::tungstenite::Message;
use tracing::{error, info, warn};

use crate::handler::handle_message;
use crate::protocol;
use crate::state::SharedState;

/// Run the WebSocket server.
pub async fn run(addr: SocketAddr, state: SharedState, token: Option<String>) {
    let listener = TcpListener::bind(addr)
        .await
        .expect("failed to bind address");

    info!("listening on {}", addr);

    // Shutdown signal: broadcast to all connection tasks
    let (shutdown_tx, _) = broadcast::channel::<()>(1);

    loop {
        tokio::select! {
            accept_result = listener.accept() => {
                match accept_result {
                    Ok((stream, peer)) => {
                        let state = state.clone();
                        let token = token.clone();
                        let mut shutdown_rx = shutdown_tx.subscribe();
                        tokio::spawn(async move {
                            tokio::select! {
                                () = handle_connection(stream, peer, state, token) => {}
                                _ = shutdown_rx.recv() => {
                                    info!(peer = %peer, "connection closed by shutdown");
                                }
                            }
                        });
                    }
                    Err(e) => {
                        error!("accept error: {}", e);
                    }
                }
            }
            _ = tokio::signal::ctrl_c() => {
                info!("shutdown signal received, closing server...");
                let _ = shutdown_tx.send(());
                // Give connections a moment to close
                tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                info!("server stopped");
                break;
            }
        }
    }
}

async fn handle_connection(
    stream: TcpStream,
    peer: SocketAddr,
    state: SharedState,
    token: Option<String>,
) {
    // Perform WebSocket handshake with optional token validation
    let ws_stream = if let Some(ref expected_token) = token {
        let expected = expected_token.clone();
        let callback =
            |req: &tokio_tungstenite::tungstenite::handshake::server::Request,
             resp: tokio_tungstenite::tungstenite::handshake::server::Response| {
                // Check token in query string
                let uri = req.uri();
                let authorized = uri
                    .query()
                    .is_some_and(|q| q.split('&').any(|pair| pair == format!("token={expected}")));
                if authorized {
                    Ok(resp)
                } else {
                    warn!(peer = %peer, "auth failed, rejecting connection");
                    Err(
                        tokio_tungstenite::tungstenite::handshake::server::ErrorResponse::new(
                            Some("unauthorized".into()),
                        ),
                    )
                }
            };
        match tokio_tungstenite::accept_hdr_async(stream, callback).await {
            Ok(ws) => ws,
            Err(e) => {
                warn!(peer = %peer, "handshake failed: {}", e);
                return;
            }
        }
    } else {
        match tokio_tungstenite::accept_async(stream).await {
            Ok(ws) => ws,
            Err(e) => {
                warn!(peer = %peer, "handshake failed: {}", e);
                return;
            }
        }
    };

    info!(peer = %peer, "client connected");
    {
        let mut st = state.write().await;
        st.active_connections += 1;
    }

    let (mut write, mut read) = ws_stream.split();

    while let Some(msg_result) = read.next().await {
        match msg_result {
            Ok(Message::Text(text)) => {
                let parsed = protocol::parse(&text);
                if let Some(response) = handle_message(parsed, &state).await
                    && let Err(e) = write.send(Message::Text(response.into())).await
                {
                    warn!(peer = %peer, "send error: {}", e);
                    break;
                }
            }
            Ok(Message::Close(_)) => break,
            Err(e) => {
                warn!(peer = %peer, "read error: {}", e);
                break;
            }
            _ => {} // ignore binary, ping, pong
        }
    }

    {
        let mut st = state.write().await;
        st.active_connections = st.active_connections.saturating_sub(1);
    }
    info!(peer = %peer, "client disconnected");
}
