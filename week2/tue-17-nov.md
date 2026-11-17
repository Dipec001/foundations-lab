# Week 2, Tuesday 17 Nov 2026: one request, from name to response

Covered: Monday's reading (DNS resolution path, TCP handshake, TIME_WAIT, congestion) through Tuesday's lab (`dig +trace`, `curl -v --trace-time`, `ss`).
Target: `https://api.heykolet.com` (Kolet API, AWS eu-west-1, behind Cloudflare).

---

## In my own words

- DNS lookups start inside my machine (127.0.0.53) and go outwards: root → .com → Cloudflare, my domain's authority. TTL decides how long answers are cached.
- A request is DNS → TCP handshake (answered by the kernel) → TLS (answered by the app) → HTTP. `curl -v --trace-time` shows where the time goes.
- TCP controls its speed (cwnd, CUBIC on Linux), and the side that closes first waits 60 s in TIME_WAIT, so reusing connections is faster and safer.

My longer summary, as I wrote it:

> Today I learnt how to use the dig command to reach domains. It starts from our own local servers (127.0.0.53) and moves outward. For example, to reach api.heykolet.com, the local servers ask the root, which is `.`, which then moves to `.com`, and then in my case to the Cloudflare servers, which is where I host the domain.
>
> DNS gives readable names to server IPs, so instead of an IPv4 or IPv6 number which is hard to remember, we have api.heykolet.com. We traced a request with `curl -v --trace-time` and saw how it moves from us, through the TCP and TLS handshakes, to talking to Cloudflare, and Cloudflare in turn talks to my load balancer for me.
>
> Packets don't just move at any speed; they move depending on how the network copes. CUBIC is the default on Linux and works by reducing the congestion window when losses occur, which it reads as a sign that the network is full. This avoids congestion collapse. BBR works using measured bandwidth and latency instead. TIME_WAIT is a 60 s wait on the side that closes first before the connection is fully gone. It's always good for speed and reliability to reuse connections.
>
> The handshake with SYN is handled by the kernel itself, and the app is the one that handles TLS and the request.

My cold-test answers (with corrections):

1. The second `dig` took 0 ms because the first answer was cached. The TTL says how long it stays cached: 377 **seconds**, not ms.
2. TIME_WAIT connections with timers: `ss -to state time-wait` (I first wrote `ss state time-wait`; it needs `-t` for TCP only and `-o` for the timers).
3. "curl connects but never gets a response": run `ss -tn` on the server. A non-zero, growing **Recv-Q** on the server's port means the kernel completed the handshake and received the data, but the app isn't reading it. The network is fine; look at the app.
4. The kernel answers the SYN. The app (or its TLS library) answers the TLS hello.
5. `Connection reset by peer` is an **RST**: an impolite "drop this connection now". Sent when a process closes a socket that still has unread data (my Ctrl+C), or when a SYN arrives on a port with nothing listening (`Connection refused`).

---

## 1. DNS: the name becomes an IP

**What:** computers connect to IP addresses, so the name has to be looked up first.

**Every lookup starts inside the machine and works outwards:**

```
dig / curl
  → /etc/hosts                    a local list, always checked first
  → /etc/resolv.conf              says: nameserver 127.0.0.53
  → 127.0.0.53 (systemd-resolved) local cache; forwards upstream if needed
  → 192.168.252.1 (the Mac)       given to the VM by DHCP at boot
  → home router → ISP resolver
  → root (.) → .com → Cloudflare's nameservers   (only if nobody has it cached)
```

`resolvectl status` shows the upstream server (`DNS Servers: 192.168.252.1`, the Mac; the VM is .2). The root servers are the one fixed point: their addresses are built into every resolver ("root hints").

**Reading a name right to left:** each part has its own servers.

| Part | Responsible servers | Seen in `dig +trace` |
| --- | --- | --- |
| `.` | root servers | c.root-servers.net |
| `com.` | .com servers | d.gtld-servers.net |
| `heykolet.com.` | Cloudflare's nameservers (authoritative) | evelyn.ns.cloudflare.com, rocky.ns.cloudflare.com |
| `api.heykolet.com` | not a server, a **record** inside heykolet.com | the answer: 104.21.25.251, 172.67.134.244 |

**How to read `dig +trace`:** each block is one conversation with one server. The records at the top are what it said; the `;; Received ... from X` line is who said it. Every server either **refers** you ("ask these servers", NS records) or **answers** (A records).

**TTL:** how many seconds an answer may be cached. It counts down in real time (237 → 199 over 37 seconds). Query time drops from ~216 ms to 0 ms while cached. When it reaches 0, the next query goes upstream again. The authoritative TTL for api.heykolet.com is **300** (set in Cloudflare). I saw 377 at first; most likely an upstream resolver raised it to its own minimum (not confirmed).

**Two A records** for one name; their order rotates between queries (round robin).

**Noise to ignore in `dig +trace`:** `network unreachable` on long `2001:`/`2606:` addresses is IPv6, which the VM can't reach, so dig falls back to IPv4. `DS`, `RRSIG`, `NSEC3` lines are DNSSEC signatures.

**`NXDOMAIN`** = the name doesn't exist. The AUTHORITY section then shows the domain's SOA record (the authority saying "I have no such name").

**Cloudflare plays two roles for heykolet.com:**

1. **DNS host:** evelyn/rocky.ns.cloudflare.com answer "what's the IP?"
2. **Proxy:** the IPs it returns (104.21.x.x, 172.67.x.x) are Cloudflare's own servers, which forward traffic to AWS. The VM never talks to AWS directly. The certificate and `server: cloudflare` header come from that.

**When to use `dig` for real:**

- a DNS change isn't showing up: see the old IP and the TTL still cached
- ask one specific server directly, skipping caches: `dig @evelyn.ns.cloudflare.com api.heykolet.com`
- check other record types: `dig MX heykolet.com`, `dig TXT heykolet.com`
- "down for some users only": different resolvers giving different answers

**Ops lesson:** before moving the API to a new IP, lower the TTL a day ahead so clients pick up the change quickly.

---

## 2. TCP: the handshake

**Flags** are on/off switches in each TCP segment's header:

| Flag | Stands for | Means |
| --- | --- | --- |
| SYN | synchronize | let's start; here's my starting sequence number |
| ACK | acknowledge | I received what you sent up to here |
| FIN | finish | I'm done sending; let's close politely |
| RST | reset | something's wrong; drop this connection now |

```
client → server   SYN       "let's talk, my counting starts at X"
server → client   SYN-ACK   "got X; mine starts at Y"
client → server   ACK       "got Y"
```

The sequence numbers are why TCP can guarantee complete, in-order data: every byte is counted, so gaps can be resent. The handshake costs **one round trip** before any data moves.

**Kernel vs app:** the app asks the kernel to `listen` on a port. The **kernel** answers every SYN, completes the handshake and queues finished connections. The app later calls `accept` to pick one up. The app never sees the SYN. (Kernel = receptionist who answers and puts callers on hold; app = the person who picks up.)

**The proof lab:**

```bash
# terminal 1: a server that listens but never accepts
python3 -c "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',9000)); s.listen(); time.sleep(600)"

# terminal 2
curl -v --trace-time http://127.0.0.1:9000
#   Established connection ... in 0.4 ms, request sent, then hangs

# terminal 3
ss -tn | grep 9000
#   ESTAB  78  0  127.0.0.1:9000   127.0.0.1:40438   ← server side: 78 unread bytes
#   ESTAB  0   0  127.0.0.1:40438  127.0.0.1:9000    ← client side
```

The 78 bytes are exactly curl's HTTP request (four header lines plus a blank line, each ending in `\r\n`). The kernel received them; the app never read them.

**Stopping the server with Ctrl+C** gave curl `Connection reset by peer`: closing a socket with unread data sends an **RST**, not a FIN. A reset aborts the connection, so no TIME_WAIT follows.

---

## 3. TLS, and where the time goes

From `curl -v --trace-time https://api.heykolet.com`:

| Step | Timestamps | Time |
| --- | --- | --- |
| DNS | resolved at .138605 | ~0 ms (cached) |
| TCP handshake | Trying .138847 → TLS starts .208287 | **~69 ms** (one round trip) |
| TLS handshake | .208287 → established .550809 | **~342 ms** |
| Request → response | sent .551558 → `HTTP/2 404` 16.195757 | **~644 ms** |

**Why TLS is slow:** almost all of it is one wait, from curl's Client hello (.208609) to the Server hello (.544435), 336 ms. A round trip is ~69 ms, so ~270 ms is the server doing work: key agreement (`X25519MLKEM768`, a heavier post-quantum hybrid) and signing proof that it owns the certificate. TCP's SYN is answered by the kernel instantly; the TLS hello needs a program to do crypto. (How the 270 ms splits between crypto, load and distance wasn't measured.)

**Certificate:** `CN=heykolet.com`, wildcard `*.heykolet.com`, issued by Let's Encrypt, served by Cloudflare.

**The 404** (`{"detail":"Not Found"}`) is because `/` isn't a route; the app answered.

**A Kolet finding to investigate:** `cf-ray: ...-GIG`. The last three letters are the Cloudflare data centre's airport code; GIG is, as far as I know, Rio de Janeiro. With the origin in eu-west-1 (Ireland), the path may be Cameroon → Brazil → Ireland → back, which could explain much of the 644 ms. To check: repeat from different networks and times, and compare `cf-ray` codes.

---

## 4. TIME_WAIT

The side that **closes first** keeps the connection in TIME_WAIT for **60 seconds** (fixed in the Linux kernel), so that:

1. the final ACK can be resent if it was lost, and
2. stray delayed packets from the old connection can't get mixed into a new one using the same ports.

```bash
curl https://api.heykolet.com
ss -to state time-wait
#   192.168.252.2:52158  172.67.134.244:https  timer:(timewait,50sec,0)  → counts down to 0, then gone
```

My VM's side waited (curl closed first); Cloudflare's side didn't.

**Why it matters:** each TIME_WAIT holds a local port for 60 s. The range is limited (`cat /proc/sys/net/ipv4/ip_local_port_range`, about 28,000 ports). A client that opens and closes a new connection per request, hundreds of times a second, can run out (`Cannot assign requested address`).

**Fix in code, not the kernel:** reuse connections (keep-alive, connection pooling). In Python, create one `httpx.AsyncClient` or `requests.Session` at start-up and share it, not one per call. `tcp_fin_timeout` controls a different state (FIN_WAIT_2); `tcp_tw_reuse` exists but is a last resort.

**Kolet:** I measured it; Kolet opens a new connection per outbound call. Reusing would save ~100 ms per call. Not urgent at current volume. Added to the Kolet fixes backlog.

---

## 5. Congestion

**What:** TCP controls its own sending speed based on how the network copes.

**Why:** if everyone sent at full speed, router queues would overflow, packets would drop, everyone would resend, and the network would jam (congestion collapse).

**Underneath:** the sender keeps a **congestion window (`cwnd`)**: how many segments may be in flight, unacknowledged.

- **Slow start:** begins at about 10 segments and doubles each round trip while ACKs arrive.
- On loss, it cuts `cwnd` back, then grows again more carefully.
- **CUBIC** (Linux default) reacts to loss. **BBR** models the path's bandwidth and round-trip time instead.
- A new connection always starts slow; a reused one already has a large `cwnd`. Another reason to reuse connections. (Caveat: by default Linux shrinks `cwnd` again after a connection sits idle, `net.ipv4.tcp_slow_start_after_idle = 1`, so the benefit is biggest for connections that stay busy.)

```bash
cat /proc/sys/net/ipv4/tcp_congestion_control    # cubic
curl -o /dev/null -w '%{http_code}\n' https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.12.tar.xz
ss -ti                                           # in another terminal, during the download
```

**What I saw:** my `cwnd` stayed at 10. `cwnd` belongs to the **sender**; in a download I'm the receiver (`data_segs_out:9`, `app_limited`). The server's `cwnd` grows on its side. On the receiving side I could see `bytes_received` climbing, `rcv_wnd` (~2.8 MB: how much I can take at once; speed is limited by both the sender's `cwnd` and my `rcv_wnd`), `rtt` ~300 ms to kernel.org's CDN vs 69 ms to Cloudflare, and `rcv_ooopack:3993` (packets arriving out of order, reordered by TCP).

---

## Command cheat sheet

```bash
cat /etc/resolv.conf                     # who the machine asks for DNS
resolvectl status                        # systemd-resolved's upstream DNS servers
dig api.heykolet.com                     # answer + TTL + query time
dig +trace api.heykolet.com              # walk root → .com → authoritative yourself
dig @evelyn.ns.cloudflare.com api.heykolet.com   # ask one server directly
dig MX heykolet.com                      # other record types
curl -v --trace-time https://api.heykolet.com    # timestamps for TCP, TLS, request
curl -o /dev/null -w '%{http_code}\n' URL        # print only the status code
ss -tn                                   # TCP connections, numeric
ss -to state time-wait                   # only TIME_WAIT, with timers
ss -ti                                   # internal TCP info: cwnd, rtt, rcv_wnd
cat /proc/sys/net/ipv4/tcp_congestion_control
cat /proc/sys/net/ipv4/ip_local_port_range
```

---

## Mistakes and the rule each taught

| What happened | The rule |
| --- | --- |
| Didn't know what a hostname was | The part of a URL between `https://` and the first `/`; the part DNS turns into an IP. |
| Said query time keeps dropping | Query time drops once (cache hit); the **TTL** is what counts down. |
| Thought lookups start at Cloudflare | They start inside the machine; the authority is the end of the chain. |
| Said 172.67.134.244 was my server | It's Cloudflare's proxy. AWS is behind it. |
| Couldn't measure the handshake | Subtract timestamps: `Trying` to the first TLS line. |
| Thought the app answers SYN | The kernel does. The app answers TLS and HTTP. |
| `ss -n` printed `RTNETLINK answers: Invalid argument` | Add `-t` to list only TCP. |
| `--tipcinfo` for TCP info | TIPC is a different protocol. The flag is `-i` / `--info`. |
| Cloudflare speed-test URL returned 403 | 403 = Forbidden (401 = Unauthorized). Use `-w '%{http_code}'` to see it. |
| Expected `cwnd` to grow during a download | `cwnd` is the sender's. The receiver shows `rcv_wnd`. |

---

## Still open

- [ ] Kolet: check the `cf-ray` code from different networks. Is traffic really going via Rio?
- [ ] Kolet fixes: reuse one HTTP client (connection pooling).
- [ ] Wednesday: `tcpdump` packet capture of one request (this week's deliverable).
- [ ] Monday's pause proof: `docker exec <node> ls -l /proc/681/ns/net /proc/783/ns/net /proc/329/ns/net`

---

## Post ideas from this session

Written as explaining to people who don't know the topic.

1. **"Connected, but no response: the network is fine, your app isn't reading."** The listen-but-never-accept lab, `ss -tn`, and 78 bytes sitting in Recv-Q. Strong, practical, and short.
2. **"Where one second of an API request goes."** The timeline table: DNS 0 ms, TCP 69 ms, TLS 342 ms, response 644 ms, and why TLS costs five times TCP (kernel vs app). Possibly the Rio → Ireland detour, once confirmed.
3. **"TIME_WAIT: why your server waits 60 seconds after every connection."** The countdown screenshot, port exhaustion, and why connection pooling fixes it.
4. **"DNS doesn't start at the internet. It starts inside your machine."** The inside-out chain, `dig +trace`, and Cloudflare's two roles.
5. **From Monday: "Every Kubernetes Pod has a process that does nothing, and your Pod's IP depends on it."** pause, with the `ns/net` screenshot once taken.

**Fits for this week's sheet:** the Tuesday Kolet post could be #2 (it's about Kolet's own API). The Friday K8s post is "How a packet gets from one Pod to another", and #5 (pause) is its natural first part.
