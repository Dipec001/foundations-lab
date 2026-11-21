# One HTTPS request to the Kolet API, packet by packet

Week 2 deliverable. Captured Wednesday 18 November 2026, annotated Friday 20 and Saturday 21 November.

**Goal:** explain, with proof, exactly what happens on the network when someone calls `https://api.heykolet.com`.

- Client: my Multipass VM, `192.168.252.2`
- Server: `172.67.134.244:443`, a **Cloudflare** IP (Cloudflare proxies the API; the origin is AWS eu-west-1, Ireland)
- Flow shown: the second of two requests in the capture, source port **59612**

---

## In my own words

> The response can't come earlier because the TCP handshake has to happen first, then the key and certificate have to be exchanged, since this is port 443 and things are encrypted. Without the lines before it, the response is useless, because it couldn't be decrypted to see the actual data.

Completed: TCP handshake → TLS keys agreed → request sent → server works (~313 ms) → response. Each step depends on the one before.

---

## How I captured it

```bash
# record: packets → file (sudo: capturing needs CAP_NET_RAW)
sudo tcpdump -ni enp0s1 -w tcpdumps.pcap 'host api.heykolet.com and port 443'
# in another terminal, twice:
curl https://api.heykolet.com
# stop with Ctrl+C

# play back: file → readable lines, only one flow
tcpdump -nr tcpdumps.pcap port 59612
```

- `-n` numbers, not names · `-i enp0s1` the interface with the default route · `-w` write to a file · `-r` read a file
- A `.pcap` file is binary: `cat` shows garbage. tcpdump is both the recorder (`-w`) and the player (`-r`).
- **A flow** = one connection, identified by 5 things: source IP, source port, destination IP, destination port, protocol. Each new curl gets a new source port, so a new flow.

---

## How to read a line

```
07:11:19.947248 IP 192.168.252.2.59612 > 172.67.134.244.443: Flags [S], seq ..., win ..., options [...], length 0
└── 1. time ──┘    └──── 2. direction: who → who ─────────┘  └ 3. flags ┘                                └ 4. length
```

Only four things matter for tracing: **time, direction, flags, length**. `seq`/`ack` count bytes (useful to confirm), `win` is the receive window, `options` are handshake settings (mss, timestamps, wscale, sack).

| tcpdump | Flag | Means |
| --- | --- | --- |
| `S` | SYN | let's start a connection |
| `.` | ACK | I've received your data up to here |
| `P` | PSH | this packet carries data; pass it to the app now |
| `F` | FIN | I'm done sending; close politely |
| `R` | RST | drop this connection now |

A dot after a letter means "and ACK": `[S.]` = SYN-ACK, `[P.]` = data + ACK, `[F.]` = FIN + ACK.

**Handshake:** `[S]` → `[S.]` → `[.]` · **Polite close:** `[F.]` → `[.]` → `[F.]` → `[.]`

### The reading recipe

**Know the script → find the anchors → drop the ACKs → group → size → gaps.**

1. **The script:** every HTTPS request runs TCP handshake → client hello → server's TLS reply → client finishes TLS + sends request → response → close.
2. **Anchors:** `[S]`/`[S.]` mark the start, `[F.]` marks the end.
3. **Drop every `length 0` line** (kernel ACKs). What's left reads like a conversation.
4. **Group:** packets in the same direction within a millisecond are one message split up.
5. **Size as a fingerprint:** first client data (~300–1600 bytes) = Client Hello; several KB from the server = certificate; ~80 bytes right after = Finished; the response = headers + body.
6. **Gaps:** a tiny gap = network or kernel; a big gap = someone thinking (crypto, the app).
7. **Confirm with `ack`; write "probably" when encryption hides the content.**

---

## The annotation

| # | Time (07:11:…) | Direction | Flags | Bytes | What it is |
| --- | --- | --- | --- | --- | --- |
| 1 | 19.947 | VM → CF | `[S]` | 0 | SYN: the VM asks to open a connection (handshake 1/3) |
| 2 | 19.995 | CF → VM | `[S.]` | 0 | SYN-ACK: Cloudflare accepts and sends its own starting number (2/3). No data. |
| 3 | 19.995 | VM → CF | `[.]` | 0 | ACK: the VM confirms. TCP is open (3/3). **Handshake ≈ 49 ms** |
| 4 | 19.998 | VM → CF | `[.]` | 1388 | TLS Client Hello, part 1 |
| 5 | 19.998 | VM → CF | `[P.]` | 188 | TLS Client Hello, part 2. Total 1576 bytes (large because of the post-quantum key), split because Cloudflare's `mss` is 1400 |
| 6 | 20.035 | CF → VM | `[.]` | 0 | Cloudflare's kernel: got part 1 |
| 7 | 20.040 | CF → VM | `[.]` | 0 | Cloudflare's kernel: got part 2 |
| 8 | 20.240 | CF → VM | `[P.]` | 2776 | TLS Server Hello + certificate + key exchange, part 1. **~242 ms after the hello was sent, ~200 ms after Cloudflare's kernel had it (line 7): the server's app doing crypto.** (2776 > mss: the VM's network card merged two packets before tcpdump saw them.) |
| 9 | 20.240 | CF → VM | `[.]` | 1388 | part 2 |
| 10 | 20.240 | VM → CF | `[.]` | 0 | the VM's kernel: got part 1 |
| 11 | 20.240 | VM → CF | `[.]` | 0 | the VM's kernel: got part 2 |
| 12 | 20.240 | CF → VM | `[P.]` | 660 | part 3, the last piece of Cloudflare's TLS reply (2776 + 1388 + 660 = 4824 bytes) |
| 13 | 20.240 | VM → CF | `[.]` | 0 | the VM's kernel: got everything (`ack 4825`) |
| 14 | 20.247 | VM → CF | `[P.]` | 80 | TLS Finished: the VM's last handshake message. Encryption is ready. |
| 15 | 20.247 | VM → CF | `[P.]` | 127 | the HTTP request, encrypted |
| 16 | 20.247 | VM → CF | `[P.]` | 48 | more of the request (HTTP/2 sends small pieces). **Request finished at .248** |
| 17 | 20.293 | CF → VM | `[.]` | 0 | got 14 |
| 18 | 20.293 | CF → VM | `[.]` | 0 | got 15 |
| 19 | 20.293 | CF → VM | `[.]` | 0 | got 16: Cloudflare has the whole request |
| 20 | 20.409 | CF → VM | `[P.]` | 575 | probably TLS session tickets + HTTP/2 settings (housekeeping) |
| 21 | 20.409 | VM → CF | `[P.]` | 31 | probably the VM acknowledging the HTTP/2 settings |
| 22 | 20.436 | CF → VM | `[.]` | 0 | got 21 |
| 23 | 20.561 | CF → VM | `[P.]` | 506 | ★ **The response**: `404` and `{"detail":"Not Found"}` (`/` isn't a route). **~313 ms after the request** |
| 24 | 20.562 | VM → CF | `[P.]` | 48 | probably curl closing the HTTP/2 connection |
| 25 | 20.562 | VM → CF | `[P.]` | 24 | probably the TLS close message |
| 26 | 20.564 | VM → CF | `[F.]` | 0 | FIN: the VM closes first, so the VM will wait in TIME_WAIT |
| 27 | 20.657 | CF → VM | `[.]` + sack | 0 | "got your FIN, but still missing 24 and 25" (they arrived out of order) |
| 28 | 20.657 | CF → VM | `[.]` + sack | 0 | "got 24, still missing 25" |
| 29 | 20.657 | CF → VM | `[.]` | 0 | "now I have everything, including your FIN" |
| 30 | 21.246 | CF → VM | `[F.]` | 0 | Cloudflare's FIN: it closes its side too |
| 31 | 21.246 | VM → CF | `[.]` | 0 | final ACK. Connection done; the VM starts its 60 s TIME_WAIT |

**sack** = selective acknowledgment: "I've got this later piece but am still missing an earlier one." TCP reordered 24 and 25 by itself.

---

## Where the time went

| Stage | From the capture (port 59612) | From `curl -w`, Friday |
| --- | --- | --- |
| DNS | (cached, not in the capture) | ~1 ms |
| TCP handshake | lines 1 → 2: ~49 ms | ~45 ms |
| TLS | lines 5 → 8: ~242 ms of waiting | ~264 ms |
| First byte (server work) | lines 16 → 23: ~313 ms | ~313 ms |

Two different tools, the same answer. TLS and first byte dominate; DNS and TCP are small.

**Request 1 vs request 2:** request 1 (port 36100), three seconds earlier, took ~643 ms from request to response; request 2 took ~313 ms. Probable reason (unconfirmed): on request 1, Cloudflare had to open a fresh connection to the AWS origin; on request 2 it reused a warm one.

```bash
curl -o /dev/null -s -w 'dns: %{time_namelookup}\nconnect: %{time_connect}\ntls: %{time_appconnect}\nfirst byte: %{time_starttransfer}\n' https://api.heykolet.com
```

The `time_` values are seconds since the start of the request, so subtract the previous one to get each stage's own time.

**Next step to split network from app:** check the ALB's `TargetResponseTime` metric in CloudWatch (time measured on the AWS side). If it's small, most of the 313 ms is the Cloudflare route (`cf-ray: ...-GIG`, probably Rio de Janeiro, to Ireland).

---

## Refused vs timed out (from the same lab)

```bash
sudo tcpdump -ni lo 'port 9999'
curl http://127.0.0.1:9999        # nothing listening
#   [S]  then  [R.] 22 µs later, from the kernel
```

| Symptom | On the wire | Look first at |
| --- | --- | --- |
| Refused, instant | SYN → RST | the app: not running, or wrong port |
| Timed out | SYN, SYN again… no reply | the network: security groups, NACLs, routes, or host down |
| Connects, then hangs | handshake OK, no response; data stuck in Recv-Q | the app: stuck, not reading |

AWS security groups drop blocked traffic silently, so they cause timeouts, not refusals.

---

## Mistakes and the rule each taught

| What happened | The rule |
| --- | --- |
| `tcpdump -i interface` | `interface` is a placeholder; give the real name (`enp0s1`). |
| `tcpdump` without sudo → `CAP_NET_RAW may be required` | Capturing needs a capability, one slice of root's powers. |
| `pcap-filter` in the command | That's the name of the manual page, not a keyword. |
| `host snappy-monarch` | Every packet involves my VM; filter on the other end. |
| `(` in the filter → `-bash: syntax error` | Quote the whole filter so bash passes it untouched. |
| `tcpdump -r` → Permission denied, even with sudo | Most likely AppArmor: Ubuntu's tcpdump profile allows file names ending in `.pcap`. Renaming fixed it. |
| File owned by user `tcpdump` | tcpdump drops root and writes as a harmless user. |
| `truncated dump file` | tcpdump writes in chunks; stop with Ctrl+C before reading, or capture with `-U`. |
| `ls -r` to read | Flags belong to each command; for `ls`, `-r` means reverse. |

---

## Still open

- [ ] One-page summary of this week, in my own words
- [ ] Apply the same reading recipe to request 1 (port 36100) on my own
- [ ] Check the ALB `TargetResponseTime` metric to split network time from app time
- [ ] `openssl s_client -connect api.heykolet.com:443` to see the certificate chain directly
