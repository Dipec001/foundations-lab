# A container is just a process

*One page, written after building it. Should make sense to someone who has used Docker but never looked underneath.*

## What I built

<!-- One paragraph: a shell running in its own PID, mount, UTS and network namespaces, inside a chroot, with CPU and memory limits from a cgroup. -->

## The commands

```bash
# 1. Get a root filesystem

# 2. Create the namespaces (unshare)

# 3. Change the root (chroot)

# 4. Limit it (cgroups v2)
```

## What each piece does

| Piece | What it isolates or limits | What breaks without it |
|---|---|---|
| PID namespace | | |
| Mount namespace + chroot | | |
| UTS namespace | | |
| Network namespace | | |
| cgroup | | |

## The same thing in Kubernetes

<!-- In kind: find the Pod's process on the node (crictl ps / ps / lsns) and show it is an ordinary process with the same namespaces and cgroups. -->

## What Docker adds that I didn't build

<!-- e.g. images and layers, overlayfs, networking setup, seccomp, capabilities. -->
