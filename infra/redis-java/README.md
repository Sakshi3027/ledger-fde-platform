# redis-java

A Redis server clone built from scratch in Java: real RESP protocol parsing (not string matching), a working command set, AOF-style persistence, thread-per-connection concurrency, and LRU eviction. Built as the infrastructure layer for the Ledger platform.

## Commands supported

`PING`, `SET`, `GET`, `DEL`, `EXPIRE`, `HSET`, `HGET`, `HGETALL`, `HDEL`

## Architecture

- **Protocol**: full RESP (REdis Serialization Protocol) parsing — arrays, bulk strings, simple strings, integers, nil
- **Concurrency**: thread-per-connection, backed by `ConcurrentHashMap` / `synchronizedMap` for thread-safe shared state
- **Persistence**: append-only file (AOF) — every mutating command is logged and flushed to disk immediately; on startup, the log is replayed to rebuild state. Verified to survive a full process restart with no data loss.
- **Eviction**: LRU, implemented via `LinkedHashMap` in access-order mode with a configurable max-entry cap (default 1000)

## Benchmark (vs real Redis, `redis-benchmark -n 10000`)

| Operation | Real Redis | redis-java | Ratio |
|---|---|---|---|
| SET | 147,058 req/s | 67,567 req/s | ~46% |
| GET | 185,185 req/s | 114,942 req/s | ~62% |

The SET gap is largely attributable to a deliberate durability tradeoff: every `SET` synchronously flushes to the AOF file before returning, guaranteeing no write is ever lost, at the cost of throughput. `GET` never touches disk and tracks real Redis's performance much more closely.

## Running locally

```bash
mvn compile
mvn exec:java -Dexec.mainClass="com.ledger.rediscache.App"
```

Server listens on port 6380 (deliberately not 6379, so it never collides with a real Redis instance running alongside it).

## Testing

```bash
redis-cli -p 6380
```
