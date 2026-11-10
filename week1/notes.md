# Week 1: How a container really works

**Goal:** by Friday, build a container by hand and explain each part of it.
**Depth question:** What happens when you run `kubectl apply -f deployment.yaml`?

For every command: what I ran, then what it proved. Keep each line short.

---

## Mon 9 Nov: Processes, signals, /proc, fork/exec (reading)

| Command | What it proved |
|---|---|
| *example:* `echo $$; ls -l /proc/$$/exe` | *my shell is a process with a PID, and /proc shows which binary it runs* |
| | |

**One thing I didn't know before:**

---

## Tue 10 Nov: Inspect a running process

Try: `ps -ef --forest`, `cat /proc/<PID>/status`, `ls -l /proc/<PID>/fd`, `lsof -p <PID>`, `strace -c <cmd>`

| Command | What it proved |
|---|---|
| | |

**One thing I didn't know before:**

---

## Wed 11 Nov: Namespaces with unshare

Try: `sudo unshare --pid --fork --mount-proc bash` then `ps aux`; `--uts` with `hostname`; `--net` with `ip a`; `lsns`

| Command | What it proved |
|---|---|
| | |

**One thing I didn't know before:**

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
