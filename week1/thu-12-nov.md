# Week 1, Thursday 12 Nov 2026: cgroups, LeetCode, Python concurrency

Format of this file: **My words** are Divine's own explanations (spelling fixed only). **Tutor fix** marks where the tutor corrected or sharpened something, so the notes don't carry a wrong idea into Saturday. Code and outputs are real, from today.

---

## 1. Cold questions (5:30 am, no notes)

**Q1. What happens when I type `ls`?**
My words: when I type ls firstly bash reads the text typed through stdin, the parent being bash itself forks and creates a child process, the child process now calls exec which replaces the running program from bash to ls, which executes the actual ls command to get the dir list, the child exits and the parent reaps it by calling wait() on it and the kernel clears the pid back into the pool.
Tutor fix: ls prints its listing through stdout; its *exit* is separate. It hands an exit status back to the parent, and that is what `wait()` collects.

**Q2. Why must `cd` be a builtin?**
My words: if it is not built in, a child process will be created and the cd will only run in the child process, after which the child process exits. The cd only took effect in the child process, which is different from the bash calling process, and the dir never changes.

**Q3. What are fd 0, 1, 2? What does `2>/dev/null` do?**
My words: 0, 1, 2 stand for stdin, stdout and stderr. 2>/dev/null redirects stderr so the terminal is not noisy.
Tutor fix: `/dev/null` **throws the output away**; nothing is saved to read later. Test:
```
ubuntu@snappy-monarch:~$ ls /nonexistent 2>/dev/null; echo "exit: $?"
exit: 2
```
The message vanished but the failure (exit 2) did not.

**Q4. Why does `unshare --pid` need `--fork`?**
My words: a process can't put itself in a new pid namespace. Only the processes it creates afterwards get placed there, so fork creates a child process which is then placed there, starting from pid 1.

---

## 2. cgroups v2 lab

### What I learned (my words, after the tutor's fixes)
- **Cgroups are folders.** Since a group is a folder, creating one is as easy as creating a folder in the cgroup directory (`sudo mkdir /sys/fs/cgroup/demo`). Only root can do it, and the kernel then fills in the files (memory.max, cpu.max, ...) by itself. *(Tutor: say "exposed by the kernel as a filesystem", not "retrieved on demand".)*
- **Memory is a wall, CPU is a throttle.** Memory can't be taken back without destroying the data in it, so going over `memory.max` gets the process **killed** (OOM). CPU can be taken back later, so going over the budget gets the process **frozen** until the next window. *(Tutor: in my first notes I wrote that memory is "throttled"; that was wrong. The kernel first tries to reclaim memory, which is the `max` counter, and only kills if it can't.)*
- **137 = 128 + 9.** A process killed by signal N is reported by the shell as 128 + N (convention, so signal deaths differ from normal exit codes 0 to 127). SIGKILL = 9, so 137. Ctrl+C is SIGINT = 2, so 130. *(Careful: fd 2 is stderr, signal 2 is SIGINT. Different numbering systems.)*
- `100M` is `100 x 1024 x 1024 = 104857600` bytes. The kernel converts it.
- **A cgroup with no process enforces nothing.** To add a process, as root write its PID into the group's `cgroup.procs`. A child process starts in its parent's cgroup.
- **`cpu.max` is a ceiling, not a guarantee.** `50000 100000` = 50 ms of CPU per 100 ms window = half of one core. The group never exceeds it and may get less.
- **Why `sudo echo x > file` fails but `echo x | sudo tee file` works:** the shell itself reads the `>` and tries to open the file, as `ubuntu`, before `sudo` has even run. With the pipe, `tee` runs as root and opens the file itself.
- **Why `sudo sh -c '... > file'` works:** the single quotes hide the `>` and the `$$` from my shell. The root `sh` receives the string, reads it as a command line, expands `$$` to its own PID and opens the file as root.
- **Quotes:** single `'...'` = literal; double `"..."` = grouped but `$` still expands; none = expands and splits into words. `sudo 'echo x > f'` = one word, so sudo looks for a program with that name: *command not found*.

### Commands and results
```
$ cat /proc/$$/cgroup
0::/user.slice/user-1000.slice/session-67.scope          # "0::" = cgroup v2

$ sudo mkdir /sys/fs/cgroup/demo
$ ls /sys/fs/cgroup/demo                                 # kernel created memory.max, cpu.max, cgroup.procs, ...

$ echo 100M | sudo tee /sys/fs/cgroup/demo/memory.max
$ cat /sys/fs/cgroup/demo/memory.max
104857600

$ echo 100M > /sys/fs/cgroup/demo/memory.max
-bash: /sys/fs/cgroup/demo/memory.max: Permission denied   # "-bash:" = my own shell was refused

$ sudo sh -c 'echo $$ > /sys/fs/cgroup/demo/cgroup.procs; cat /proc/self/cgroup'
0::/demo

$ echo "$$" '$$'
144847 $$

$ printf '[%s]\n' echo hi there        -> [echo] [hi] [there]
$ printf '[%s]\n' 'echo hi there'     -> [echo hi there]
```

**A test that did not work (my mistake to check, the tutor's to apologise for):** `exec tail /dev/zero` inside the group did not use memory: `memory.peak` was 1572864 and all `memory.events` counters stayed 0. Lesson: check that the test tool does what you assume.

**Memory wall: [`hog.py`](hog.py)**
```python
data = []
while True:
    data.append(b"x" * 10_000_000)
    print(len(data) * 10, "MB", flush=True)
```
```
$ sudo sh -c 'echo $$ > /sys/fs/cgroup/demo/cgroup.procs; exec python3 hog.py'
10 MB ... 100 MB
Killed
$ echo "exit: $?"
exit: 137
$ cat /sys/fs/cgroup/demo/memory.events
low 0 / high 0 / max 37 / oom 1 / oom_kill 1 / oom_group_kill 0 / sock_throttled 0
$ cat /sys/fs/cgroup/demo/memory.peak
104857600
```
`oom_kill 1` is the counter that proves an OOM kill. `max 37` = the group hit the limit 37 times (the kernel tried to reclaim memory each time).

**CPU throttle**
```
$ echo "50000 100000" | sudo tee /sys/fs/cgroup/demo/cpu.max
$ sudo sh -c 'echo $$ > /sys/fs/cgroup/demo/cgroup.procs; exec yes > /dev/null' &
$ ps -o pid,pcpu,etime,cmd -C yes
151081 40.8 00:29 yes
cpu.stat, 2 s apart:  nr_periods 484 -> 504,  nr_throttled 310 -> 321,  throttled_usec 24814863 -> 25964567
$ sudo pkill yes          # sends SIGTERM (15); the shell printed "Terminated" (SIGKILL would print "Killed")
```
The loop got about 37 to 41% of a CPU, below the 50% cap. Throttled in 11 of 20 windows, not all of them (the tutor's guess of ~10 per second was wrong).
Also noticed: `sudo` was PID 151074 and `yes` was PID 151081, because sudo forks the command it launches.

---

## 3. LeetCode (Arrays and hashing)

Full log: [leetcode.md](leetcode.md).

**Contains Duplicate, redone cold (yesterday's problem): Accepted, 3m 21s, 80/80.**
```python
class Solution:
    def containsDuplicate(self, nums: list[int]) -> bool:
        new_set = set()
        for num in nums:
            if num in new_set:
                return True
            new_set.add(num)
        return False
```
Complexity: O(n). One pass, with an O(1) set lookup per item.

**Valid Anagram (new): Accepted, 56/56, 26m 12s, 11 ms.**
```python
class Solution:
    def isAnagram(self, s: str, t: str) -> bool:
        if len(s) != len(t):
            return False
        new_dict_s = {}
        new_dict_t = {}
        num_seen = 1
        for letter in s:
            if letter in new_dict_s:
                new_dict_s[letter] += 1
            else:
                new_dict_s[letter] = num_seen
        for letter in t:
            if letter in new_dict_t:
                new_dict_t[letter] += 1
            else:
                new_dict_t[letter] = num_seen
        for k, v in new_dict_s.items():
            if k not in new_dict_t:
                return False
            if k in new_dict_t:
                if v != new_dict_t[k]:
                    return False
        return True
```
Time O(n) (three passes, O(1) lookups), space O(distinct letters). Pattern: **counting with a hash map**. A set fails because it loses counts ("aab" vs "abb").
**Tomorrow's cold rewrite (before the new problem), cleanup to try:** drop `num_seen`; remove the redundant `if k in new_dict_t`; compare the two dicts directly with `==`; harder: use one dict (add for `s`, subtract for `t`). Also: `sorted(s) == sorted(t)` works but is O(n log n).
Big-O in plain words: O(1) = work doesn't grow; O(n) = grows in step with input; O(n^2) = loop inside a loop.
Add Two Sum (day 1) to Saturday's cold review with the rest of the week.

---

## 4. Python: GIL, threads, processes, asyncio

Terms: **process** = running program with private memory. **Thread** = a line of execution inside a process, sharing its memory. **CPU-bound** = time spent calculating. **I/O-bound** = time spent waiting (network, disk, database). **Concurrency** = tasks take turns so waits overlap. **Parallelism** = work at the same instant on several cores. **CPU core** = one independent worker in the chip that runs one instruction stream at a time; the multipass VM has 1 core (`nproc` = 1), so this test ran on the Mac.

**The GIL (Global Interpreter Lock):** one lock in CPython. A thread must hold it to run Python code and only one thread can hold it at a time. It exists because CPython counts references to objects; two threads changing a count at once could corrupt it. A thread that is *waiting* lets go of the GIL.

**Test 1: [`gil_test.py`](gil_test.py) (CPU-bound, run on the Mac)**
```
one after another   0.53 s
two threads         0.52 s
two processes       0.32 s
```
My words (why threads took as long as sequential): the two threads took as long as running it one after the other because threads all use the GIL and inside a process they take turns, only one can run at a time.
Tutor fix: the lock isn't protecting my variables. In `count()` each thread had its own local `n`, and they still ran serially. The GIL is one lock for the whole interpreter. Threads swap the lock every few milliseconds, so they take turns, not strictly one-then-the-other.

**Test 2: [`io_test.py`](io_test.py) (I/O-bound: waiting)**
```
one after another: 4.02
four threads:      1.01
```
My words: 4 threads take 1 sec since they are able to wait on all four at the same time. With counting, work is actually being done and it can only be faster if more CPUs work on it; inside a process only one thread is allowed to work, the GIL makes sure of that, regardless of how many CPUs your machine has.
Missing piece (tutor): a waiting thread **releases** the GIL, so the others run in the meantime.

**Test 3: [`async_test.py`](async_test.py)**
```
good 1.0
bad 4.02
```
My words: with asyncio only the await switches the tasks, so without it the sleep runs synchronously and each one finishes before the next.
Tutor fix: a task that never awaits never gives the loop a chance to switch, so it holds the thread. The classic mistake is a **blocking call inside async code** (`time.sleep`, a blocking HTTP library, a long calculation), not "forgetting await" (forgetting await means the coroutine never runs, and Python warns "coroutine was never awaited"). In FastAPI an `async def` endpoint runs on the event loop, so one blocking call stalls every request; a plain `def` endpoint is run in a thread pool. *(Check the FastAPI docs before saying this in an interview.)*

**My words on asyncio vs threads:** both let us run multiple things at once but they differ in how the switching works: with asyncio you run multiple tasks inside a thread and the switch happens at await, while threads take turns because the GIL allows only one to run at a time.
Tutor fix: say concurrency (taking turns, waits overlap) not "at once". The OS can pause a thread between any two lines (so shared data needs locks); an asyncio task is paused only at `await`.

**Which tool?** My words: 100 web pages = threads, because we are just waiting on the downloads. 100 large images = processes, because that is actual processing and needs CPU, so processes let us use more cores. (Tutor: about one process per core.)

Post idea (in Posts tab as Idea): "I measured it: Python threads gave me zero speedup on CPU work" (0.53 s / 0.52 s / 0.32 s).

---

## 5. The 8 Python interview questions (answer aloud first, then check)

1. What is the GIL, and why does CPython have it?
2. Why don't two threads speed up CPU-bound Python code? Use my numbers (0.53 / 0.52 / 0.32).
3. When do threads *do* help in Python, and why? (what happens to the lock while a thread waits?)
4. How do I speed up CPU-bound work, and how many processes would I start?
5. asyncio vs threads: how does each switch, and what is the difference between concurrency and parallelism?
6. What happens if I call `time.sleep(1)` inside an `async def`? What does that mean for a FastAPI endpoint?
7. 100 web pages to download versus 100 large images to resize: which tool for each, and why?
8. How would I run a Python web service so it uses all the cores of a multi-core machine? (Think: one process per core, each with its own GIL.)

<details><summary>Answer key (check after answering, don't read first)</summary>

1. A lock letting one thread run Python code at a time; protects reference counts.
2. Threads take turns on the one lock; same total work, ~2T.
3. I/O-bound work: a waiting thread releases the lock.
4. `multiprocessing`/process pool; about one per core; processes don't share memory and cost start-up time.
5. OS switches threads anywhere; asyncio switches only at `await`; concurrency = overlapping by taking turns, parallelism = literally simultaneous on several cores.
6. It blocks the whole loop: every other task and request waits.
7. Threads/asyncio for downloads (waiting); processes for images (CPU).
8. Several worker processes behind one server; each has its own interpreter and GIL.

</details>

---

## 6. Saturday retrieval list (answer cold, no notes, then check)

Linux:
1. A container is a process plus what, what and what? (namespaces = what it sees, cgroups = what it can use, chroot = its own root filesystem)
2. Why does `cpu.max` throttle but `memory.max` kill?
3. What do exit 130 and exit 137 mean?
4. Why must `unshare --pid` use `--fork`?
5. Who sees the `>` in `sudo sh -c '... > file'`, and why? (the inner root shell, because the quotes hide it from mine; it then opens the file as root)
6. Which counter in `memory.events` proves an OOM kill? (`oom_kill`)

LeetCode: What is the time complexity of Valid Anagram, and why isn't a set enough? Redo Two Sum, Contains Duplicate and Valid Anagram cold.

Python: the 8 questions above.

---

## 7. Three things I learned today (say these aloud tomorrow)
- A container is a normal process with a restricted view (namespaces) and restricted resources (cgroups). Memory limits kill (137), CPU limits throttle.
- Quotes decide *which shell* sees `>` and `$$`: that is why `sudo sh -c '...'` works and `sudo echo x > file` doesn't.
- The GIL lets only one thread run Python code at a time, so threads help with waiting (I/O) and processes help with calculating (CPU). `asyncio` switches only at `await`, so one blocking call freezes everything.

**Post sentence (Friday's container post):** "A container isn't a thing, it's a process that's been told a different story about what exists."

## 8. Next
- **Fri 13 Nov:** cold questions (from the lists above), assemble the tiny container (unshare + chroot + cgroups), find the Pod's process on the node in a kind cluster, one-page explanation, FULL MOCK interview.
- **Open items from the sheet:** Kolet fixes #1 (`network.tf` comment) and #2 (`database.tf` comment), enter the CKA pass date, check/book the A2 exam date, empty Job hunt tab, German speaking practice (no partner yet).
- **CKAD:** 2 hours every other day (pick the days). Order: CKAD, then CKS, then KCSA (renews automatically with CKS).
