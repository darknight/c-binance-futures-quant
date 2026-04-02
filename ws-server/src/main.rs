mod handler;
mod protocol;
mod server;
mod state;

use std::net::SocketAddr;
use std::sync::Arc;

use clap::Parser;
use tokio::sync::RwLock;
use tracing_subscriber::EnvFilter;

use state::MarketState;

#[derive(Parser)]
#[command(name = "ws-server", about = "Market data aggregation WebSocket server")]
struct Args {
    /// Port to listen on
    #[arg(long, default_value = "3698")]
    port: u16,

    /// Log level (trace, debug, info, warn, error)
    #[arg(long, default_value = "info")]
    log_level: String,

    /// Optional auth token. Clients must connect with ?token=<value>
    #[arg(long)]
    token: Option<String>,
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let args = Args::parse();

    // Initialize tracing
    let filter = EnvFilter::try_new(&args.log_level).unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::fmt().with_env_filter(filter).init();

    let addr: SocketAddr = ([0, 0, 0, 0], args.port).into();
    let state = Arc::new(RwLock::new(MarketState::new()));

    server::run(addr, state, args.token).await;
}
