# Week 2: Networking (TCP/IP, DNS, TLS, HTTP)

**Goal:** by Friday, an annotated packet capture of one request, from DNS lookup to response.
**Depth question:** How does a packet get from one Pod to another Pod on a different node?

For every command: what I ran, then what it proved. Keep each line short.

---

## Mon 16 Nov: finding a Pod's process (week 1 leftover: kind)

Full notes for the day: **[mon-16-nov.md](mon-16-nov.md)**. They cover the Kubernetes Namespace vs Linux namespace, the shim and pause, one process with three PIDs, and how Kubernetes lays out cgroups.

---

## Tue 17 Nov: one request, from name to response

Full notes for the day: **[tue-17-nov.md](tue-17-nov.md)**. They cover DNS from inside the machine outwards (`dig +trace`, TTL, Cloudflare's two roles), the TCP handshake (the kernel answers SYN; the listen-but-never-accept lab), where the time goes in one request to the Kolet API (TCP 69 ms, TLS 342 ms, response 644 ms), TIME_WAIT, and congestion (`cwnd`, CUBIC vs BBR).

---

## Wed 18 Nov: capture one request with tcpdump or Wireshark

| Command | What it proved |
|---|---|
| | |

---

## Thu 19 Nov: ss and iptables; find the slow part (DNS, connect, TLS or first byte)

| Command | What it proved |
|---|---|
| | |

---

## Fri 20 Nov: the annotated packet capture

| Command | What it proved |
|---|---|
| | |

---

## Depth ladder

| Try | Date | Gaps I found |
|---|---|---|
| Cold | | |
| 1 | | |
| 2 | | |
| 3 | | |

---

## Sat 21 Nov: Weekly review

- **Deliverable done?** yes / no
- **Score (1 to 5):**
- **What went well:**
- **What I'll change next week:**
