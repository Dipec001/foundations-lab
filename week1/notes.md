# Week 1: How a container really works

**Goal:** by Friday, build a container by hand and explain each part of it.
**Depth question:** What happens when you run `kubectl apply -f deployment.yaml`?

For every command: what I ran, then what it proved. Keep each line short.

---

## Mon 9 Nov: Processes, signals, /proc, fork/exec (reading)

| Command | What it proved |
|---|---|
| `exec ps` | `exec` replaces the current process instead of creating a new one. Bash became `ps`, and when `ps` exited there was no shell left, so the terminal closed and logged me out. |
| | |

**What I learned (in my own words):**

I never really knew how processes worked. When the system boots, the kernel (PID 0) starts PID 1 (systemd on Ubuntu), and every normal program descends from it.

When I run a command in the terminal, bash is its own process with a parent. Bash **forks**, which makes a copy of itself. The child then calls **exec**, which throws away the bash copy and runs the actual command. When the command finishes it **exits**, the parent **reaps** the child by collecting its exit status, and the kernel frees the PID for reuse.

PIDs are handed out in increasing order. When they hit the limit (`/proc/sys/kernel/pid_max`) they wrap around and skip any still in use.

A **zombie** is a process that has exited but hasn't been reaped by its parent yet.

**Why it matters:**
- A container is just a process (this week's deliverable).
- Stopping a container or an ECS task sends its main process a signal (SIGTERM, then SIGKILL after a timeout). If Kolet doesn't handle it, a request in the middle of a transfer can get cut off.
- If the main process in a container (PID 1) never reaps its children, zombies pile up. It's a classic production bug.

---

## Tue 10 Nov: Inspect a running process

Try: `ps -ef --forest`, `cat /proc/<PID>/status`, `ls -l /proc/<PID>/fd`, `lsof -p <PID>`, `strace -c <cmd>`

| Command | What it proved |
|---|---|
| `exec sleep 1` (in a bash terminal) | `exec` swaps bash's program for `sleep` in the same process (same PID). When `sleep` finished there was no bash left, so the terminal closed. |
| `./script.sh` with `trap 'echo "Goodbye!"' TERM`, then `kill <PID>` from another terminal | `kill` sends SIGTERM by default. The trap caught it and printed "Goodbye!", and the script kept running because the trap didn't exit. |
| `kill -9 <PID>` | SIGKILL can't be trapped. The kernel kills the process itself, and the process never gets a chance to run any code. |
| `ls /proc/$$`, `cat /proc/$$/status` | `/proc` isn't on disk. The kernel generates it when you read it. Each PID gets a folder (`exe`, `cwd`, `fd`, `status`...). |
| `cmd > out.txt`, `cmd 2> err.txt` | `>` redirects stdout (fd 1), `2>` redirects stderr (fd 2). `2>&1` sends both to the same place. |
| `bash -c 'sleep 1 & exec sleep 60'`, then `ps -o pid,ppid,stat,cmd` | A zombie (`Z` in STAT). Bash forked `sleep 1` as a child, then `exec` turned bash into `sleep 60`. `sleep` never calls `wait()`, so the child stayed a zombie until its parent exited. |
| `kill -9 <zombie PID>` | Does nothing. A zombie is already dead; it's only an entry in the process table. |

**What I learned (in my own words):**

**Signals** are messages the kernel delivers to a process. A process can ignore one, catch it with a handler (`trap` in bash), or take the default action. SIGKILL (9) and SIGSTOP can't be caught or ignored. Others: SIGINT is Ctrl+C, SIGTERM (15) is the polite "please stop" and the default for `kill`.

**Zombies** are children that have exited but haven't been reaped by their parent. There are only two ways to get rid of one: the parent calls `wait()`, or the parent dies, the zombie is adopted by PID 1 (init), and init reaps it.

**Orphans** are children still running after their parent has exited. PID 1 adopts them.

**Why it matters for containers:** the app is PID 1 inside a container. If it never reaps children, zombies pile up. That's why `docker run --init` (tini) exists. And SIGTERM is what Docker and ECS send on stop, so the app needs to handle it and finish in-flight work.

---

## Wed 11 Nov: Namespaces with unshare

| Command | What it proved |
|---|---|
| `cd`, `pwd` (`type cd`) | They're bash builtins: they run inside bash with no fork. If `cd` ran as a child process, only the child's directory would change, then it would exit and bash wouldn't move. |
| `ls -l /proc/$$/ns` | Every process belongs to 8 namespaces: cgroup, ipc, mnt, net, pid, time, user, uts. This week covers pid, net, mnt and uts. |
| `sudo unshare --pid --fork --uts --mount-proc bash`, then `hostname test`, `ps -e` | Inside, bash is PID 1 and `ps` shows only the new namespace's processes. Changing the hostname there doesn't change the host's. |
| Same thing without `--mount-proc`, then `ps -e` | `ps` still lists the host's processes, because it reads the old `/proc`. `unshare` shows up as well: with `--fork`, `unshare` stays as the parent and its child is the bash inside the new namespace. |
| `sudo unshare --net bash`, then `ip a`, `ping -c 1 127.0.0.1` | A new network namespace starts with only a loopback interface, and it's down, so even pinging itself fails. |
| `ip link set lo up`, then `ping -c 1 127.0.0.1` | Loopback works now, but there's still no route to the outside world. |
| `sudo nsenter -t <PID> --uts --pid ...` | `nsenter` joins the namespaces of a process that's already running. `unshare` creates new ones. |

**What I learned (in my own words):**

**cwd** is the directory a process is "in". Relative paths are resolved from it.

**Namespaces** give a process its own restricted view: its own PID 1 (pid), its own network stack (net), its own mounts (mnt) and its own hostname (uts).

**--mount-proc** mounts a fresh `/proc`, which is a virtual filesystem, so tools like `ps` see the new PID namespace instead of the host's.

**Libraries:** in these labs, bash still used the host's files and shared libraries, because I never changed its root. In the tiny container, I'll have to supply them myself (chroot plus a root filesystem).

**Kubernetes link (week 2):** a new network namespace is isolated. Kubernetes' network plugin (CNI) connects each Pod's namespace to the node with virtual cables (veth pairs). That's how Pods get out.

**Post line:** "A container isn't a thing. It's a process with a restricted view: its own hostname, its own PID 1, its own network. I built one by hand."

---

## Thu 12 Nov: cgroups v2 (limit CPU and memory, trigger an OOM kill)

| Command | What it proved |
|---|---|
| `pkill <name>` vs `kill -9 <PID>` | `pkill` sends SIGTERM by default, and the shell prints `Terminated`. SIGKILL prints `Killed`. |
| `cat /proc/$$/cgroup`, `ls /sys/fs/cgroup/` | Every process is already in a cgroup. The kernel exposes cgroups as a filesystem. |
| `sudo mkdir /sys/fs/cgroup/demo` | Making a cgroup is making a folder. The kernel fills it with control files (`memory.max`, `cpu.max`, `cgroup.procs`...) automatically. |
| `echo $$ \| sudo tee /sys/fs/cgroup/demo/cgroup.procs` | An empty cgroup enforces nothing. A limit only applies once a PID is written into `cgroup.procs`. |
| `echo 100M \| sudo tee .../demo/memory.max`, then `python3 hog.py` | The script grew in 10 MB steps until about 100 MB, then was killed with exit 137. The kernel converts `100M` to bytes for me (100 × 1024 × 1024). |
| `cat .../demo/memory.events` | `max` counts how often the group hit the limit and the kernel tried to reclaim memory. `oom_kill` above 0 proves the OOM killer ran. |
| `echo "50000 100000" \| sudo tee .../demo/cpu.max`, then `cat cpu.stat` | The group may run 50 ms in every 100 ms window (half a CPU). `nr_throttled` and `throttled_usec` go up. The process slows down but isn't killed. |

The memory hog ([hog.py](hog.py)):

```python
data = []
while True:
    data.append(b"x" * 10_000_000)
    print(len(data) * 10, "MB", flush=True)
```

**What I learned (in my own words):**

**cgroups are folders exposed by the kernel as a filesystem.** Since a group is a folder, creating one is as easy as `mkdir` (as root), and the kernel adds the control files itself.

**The memory wall:** when a group reaches `memory.max`, the kernel first tries to reclaim what it can (the `max` counter). When it can't, it OOM-kills a process with SIGKILL. Memory can't be throttled like CPU: once a process holds memory, the only way to get it back is to destroy the process holding it.

**Why 137:** it's a shell convention. Exit codes 0 to 127 are for programs' normal exits, so a process killed by signal N is reported as 128 + N. That keeps "killed by SIGKILL" distinguishable from "exited normally". SIGKILL is 9, so 137. Ctrl+C is SIGINT (2), so 130.

**The CPU throttle:** the budget is the limit. `50000 100000` means 50 ms of CPU in each 100 ms window. After that the group is frozen until the next window starts. CPU time can always be handed back later, so the kernel slows the process down instead of killing it.

**`sudo echo x > file` fails, `echo x | sudo tee file` works:** the redirect `>` is handled by my own (non-root) shell, which tries to open the file before `sudo` even runs, so it fails. With the pipe, `echo` runs as me and `tee` runs as root, and `tee` is the one that opens the file. `sudo sh -c 'echo x > file'` also works: the whole quoted string goes to a root `sh`, which reads it as a command line and opens the file as root.

**Kubernetes link:** a container's `resources.limits.memory` becomes `memory.max`, and `limits.cpu` becomes `cpu.max`. That's why going over the memory limit shows `OOMKilled` (exit 137), while going over the CPU limit only makes the app slow.

### Retrieval questions (answer cold on Friday, then check)

1. A container is a process plus what, what, and what?
   <details><summary>Answer</summary>Namespaces (what it sees), cgroups (what it can use) and chroot / its own root filesystem (what files it has).</details>
2. Why does `cpu.max` throttle but `memory.max` kill?
   <details><summary>Answer</summary>CPU time can be taken back and given later, so the kernel just pauses the group. Memory can't be taken back from a process without destroying it, so the kernel reclaims what it can and then kills.</details>
3. What do exit 130 and exit 137 mean?
   <details><summary>Answer</summary>128 + signal number. 130 = SIGINT (Ctrl+C). 137 = SIGKILL: an OOM kill, or a process that ignored SIGTERM and was killed when its grace period ran out.</details>
4. Why must `unshare --pid` use `--fork`?
   <details><summary>Answer</summary>A process can't move itself into a new PID namespace. Only its children are born into it. So `unshare` has to fork, and the child becomes PID 1 inside.</details>
5. Who sees the `>` in `sudo sh -c '... > file'`, and why?
   <details><summary>Answer</summary>The inner root `sh`. The outer shell passes everything in the quotes as one string. The root `sh` reads it as a command line and opens the file as root.</details>
6. Which counter in `memory.events` proves an OOM kill?
   <details><summary>Answer</summary><code>oom_kill</code> (greater than 0).</details>

---

## Fri 13 Nov: Assemble the tiny container, then find a Pod's process in kind

Write-up goes in [tiny-container.md](tiny-container.md).

| Command | What it proved |
|---|---|
| | |

**One thing I didn't know before:**

---

## Depth ladder

Say it aloud cold on Monday, then 3 more times this week. Write down what I got wrong or couldn't explain.

| Try | Date | Gaps I found |
|---|---|---|
| Cold | | |
| 1 | | |
| 2 | | |
| 3 | | |

---

## Sat 14 Nov: Weekly review

- **Deliverable done?** yes / no
- **Score (1 to 5):**
- **What went well:**
- **What I'll change next week:**
- **Post for Friday:** "A container is just a process: I built one by hand" (link: )
