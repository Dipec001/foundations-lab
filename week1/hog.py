# Allocates memory in 10 MB steps until the cgroup's memory.max OOM-kills it.
# Run inside a cgroup with a memory limit, e.g. memory.max = 100M.
data = []
while True:
    data.append(b"x" * 10_000_000)
    print(len(data) * 10, "MB", flush=True)
