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

Try: `ls /sys/fs/cgroup`, make a cgroup dir, write `memory.max` and `cpu.max`, add a PID to `cgroup.procs`, read `memory.events` after the OOM

| Command | What it proved |
|---|---|
| | |

**One thing I didn't know before:**

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
