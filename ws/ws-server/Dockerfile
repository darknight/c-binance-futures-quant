FROM rust:1-slim AS builder

WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim

COPY --from=builder /app/target/release/ws-server /usr/local/bin/
EXPOSE 3698
CMD ["ws-server", "--port", "3698", "--log-level", "info"]
