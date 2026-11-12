# foundations-lab

My notes and labs for weeks 1 to 3 of my 15-week plan (Nov 2026): Linux, containers and networking, learned by running real commands.

The rule for every note: **write down the command, then write down what it proved.** If I can't say what a command proved, I don't understand it yet.

## Weeks

| Week | Focus | Deliverable | Depth question (say it aloud, no notes) | Status |
|---|---|---|---|---|
| [1](week1/) | Processes, namespaces, cgroups: how a container really works | A tiny container built by hand (unshare, chroot, cgroup limits) plus a one-page explanation | What happens when you run `kubectl apply -f deployment.yaml`? | In progress |
| 2 | Networking: TCP/IP, DNS, TLS, HTTP | An annotated packet capture of one request, from DNS lookup to response | How does a packet get from one Pod to another Pod on a different node? | Not started |
| 3 | Linux performance and debugging: strace, perf, /proc, I/O | One request traced end to end, with a timing breakdown | You call a Kubernetes Service IP. What actually happens? | Not started |

## Layout

```
week1/
  notes.md            daily commands and what each one proved
  tiny-container.md   the week's deliverable
  hog.py              memory hog for the cgroup OOM lab
```

Each new week gets the same layout: copy `week1/`, then clear the notes.

## Setup

The labs need Linux (namespaces and cgroups don't exist on macOS), so I run them in an Ubuntu VM:

```bash
multipass launch 24.04 --name lab --cpus 2 --memory 2G --disk 10G
multipass shell lab
```

Ubuntu 24.04 uses cgroups v2 by default. To delete the VM: `multipass delete lab && multipass purge`.
