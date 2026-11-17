# Week 2, Monday 16 Nov 2026: finding a Pod's process

## In my own words

Read this section before the next session. The rest of the page is reference.

1. **Kubernetes Namespace vs Linux namespace.** A Kubernetes Namespace is a more permanent namespace that is created using `kubectl create ns new-namespace`; it lives independent of anything. A Linux namespace lives as long as the processes running in it live. When you run `unshare --pid`, it creates a PID namespace and runs the command in it; when that process ends, the Linux namespace does too.
   *Fix:* a Linux namespace isn't a process, it's kept by the kernel and attached to processes. A Kubernetes Namespace only groups and names objects; it doesn't isolate anything in the kernel.
2. **pause.** A pause process is created automatically for every Pod and managed by Kubernetes because of how Linux namespaces behave. It is created and sleeps forever. The IP of the Pod remains after a container restarts because the pause process stays alive to keep the namespace.
   *Fix:* one pause per Pod, not per node.
3. **The shim.** When you run a command to create a Pod, containerd is in charge of creating the container. The shim is the parent, and it detaches itself from containerd to be adopted by systemd, which is more stable, so when containerd is restarted the Pods don't vanish with it.
   *Add:* the shim stays the parent of the Pod's processes, so it collects their exit codes (like 137) and passes them on.
4. **Why the VM sees nginx.** Because they are children in the tree, which starts from the VM. The VM is able to see all the child processes, but not the reverse.
   *Add the two key words:* one kernel, and nested PID namespaces.
5. **Why different PIDs.** In the tree, everyone keeps their own record of it: from the VM a high number, from within the node container another number, and in the Pod itself another.
   *Add:* each PID namespace numbers its processes independently.

**Follow-ups I asked about:**

- **If systemd (PID 1) dies:** on a real server the kernel panics and the machine goes down; in a kind node, its PID namespace ends and every Pod on it dies. systemd upgrades itself with `daemon-reexec`, keeping PID 1.
- **Why not make everything a child of PID 1:** the parent collects the child's exit code (that's how `echo $?` showed 137). Short commands should stay with your shell; long-running services (sshd, containerd, kubelet, shims) do detach. That's called daemonizing.
- **Who restarts a crashed container:** shim collects the exit code → containerd passes it on → kubelet checks `restartPolicy`, starts a new one, and reports `OOMKilled`, exit code 137, `restartCount` to the API server. The new container joins the same pause, so the Pod keeps its IP.

---

## Two kinds of namespace

Kubernetes uses the same word for two unrelated things. Always say which one you mean.

| | Kubernetes Namespace | Linux namespace |
|---|---|---|
| Example | `kubectl create ns dev`, `kube-system` | `unshare --pid`, a Pod's network |
| What it is | a label/folder for API objects | a kernel feature that changes what a process can see |
| Where it lives | a record in etcd | in the kernel, attached to processes |
| Lives with no processes? | Yes, until deleted | No. Gone when its last process exits |
| Real isolation? | Only by name and permissions (RBAC, quotas) | Yes: PIDs, network, mounts |

---

## Set-up commands, with the why

**Grow the VM** (on the Mac, VM stopped). kind runs every node as a heavy container; the default 1 CPU / 1 GB isn't enough.

```bash
multipass get local.snappy-monarch.cpus      # read a setting
multipass stop snappy-monarch
multipass set local.snappy-monarch.cpus=4
multipass set local.snappy-monarch.memory=8G
multipass start snappy-monarch
# inside the VM:
nproc        # number of CPUs
free -h      # memory, human-readable (or top, then press 1 for each CPU)
```

The VM only takes Mac memory as it uses it, and keeps it until the VM stops. When done: `kind delete cluster`, then `multipass stop snappy-monarch`.

**Docker.** The `docker` command only sends requests to the `dockerd` daemon through a socket.

```bash
sudo apt install docker.io
systemctl status docker      # one service
systemctl status             # no name: the whole cgroup tree
ls -l /var/run/docker.sock   # srw-rw---- root docker
```

**Use Docker without sudo.** Add yourself to the `docker` group. Being in it is almost the same as root.

```bash
sudo usermod -aG docker ubuntu   # -a = append; -G alone REPLACES all groups
grep docker /etc/group           # the file changed
id                               # but this shell hasn't: log out and back in
```

A process's groups are fixed when it starts, and children inherit them. A new login reads `/etc/group` again.

**kind and kubectl.**

```bash
sudo apt install kind
sudo snap install kubectl --classic   # --classic = no snap sandbox
kind --version
kubectl version --client
```

**A 3-node cluster** (`~/kind/cluster.yaml`):

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
- role: worker
- role: worker
```

```bash
kind create cluster --config cluster.yaml
docker ps                       # 3 containers, one per node
kubectl run nginx --image=nginx
kubectl get pod nginx -o wide   # which node it landed on
```

---

## Inside a kind node: the shim and pause

A kind node is a container running a small Linux with systemd as PID 1, which then runs more containers. Look inside with `docker exec <node> ps -o pid,ppid,cmd -e`.

| Process | What it does |
|---|---|
| systemd (PID 1) | starts and looks after the services |
| containerd | builds the containers |
| kubelet | the node agent: watches the API server and tells containerd what to run |
| containerd-shim | one per Pod; the babysitter and parent of that Pod's processes |
| pause | one per Pod; holds the Pod's Linux namespaces open |
| kube-proxy, kindnetd | these are Pods (DaemonSets), not node services |

On the control plane, etcd, the API server, the scheduler and the controller manager are static Pods, each with its own shim and pause.

**Why a shim:** containerd builds the Pod, then hands it to the shim and steps away. The shims' parent is systemd, not containerd, so containerd can crash or be upgraded without killing every Pod on the node.

**Why pause:** a Pod's containers share one Linux network namespace, which gives the Pod one IP. A Linux namespace only lives while a process is in it. So:

1. pause starts first and gets the new network namespace. It does nothing else, it sleeps forever.
2. The network plugin (kindnet) gives that namespace the Pod IP, e.g. `10.244.1.2`.
3. nginx starts and joins pause's namespace, so it sees the Pod IP as its own.
4. If nginx crashes and restarts, it rejoins. Same IP, because pause never left.
5. Delete the Pod: pause stops, the namespace has no processes left and disappears, and the IP is freed.

Pods with `hostNetwork: true` (most control-plane Pods, kube-proxy, kindnet) use the node's network. Their pause still exists but doesn't hold a separate network namespace, so they show the node's IP.

**nginx's five processes:** 1 master (reads the config, manages the workers) + 4 workers (serve requests), one worker per CPU the container can see.

---

## One process, three PIDs

The nginx master is 783 inside the node, 26631 on the VM, and most likely 1 inside its own container. There is one kernel, and Linux PID namespaces are nested: a process is visible in its own namespace and every namespace above it, with a different PID at each level. The VM's namespace is at the top, so it sees everything.

Two shims are stacked: Docker's shim babysits the node container (its `-id` is kind-worker2's container ID), and inside the node, containerd's shim babysits the Pod.

```bash
# on the VM
ps -e | grep nginx
ps -eo pid,ppid,cmd | grep nginx
ps -o pid,ppid,cmd -p 26026    # the shim: same -id as 658 inside the node
```

---

## How Kubernetes lays out cgroups

Run `docker exec <node> systemctl status` to see it. It's the same `/sys/fs/cgroup` from Week 1.

| Level | What it is |
|---|---|
| `kubelet-kubepods.slice` | all Pods on this node |
| `...-besteffort.slice` / `...-burstable.slice` | a QoS class. Guaranteed Pods sit directly under kubepods, with no QoS folder |
| `...-pod<uid>.slice` | one Pod |
| `cri-containerd-<id>.scope` | one container in that Pod (pause has its own) |

- QoS classes are cgroup folders. nginx has no requests or limits, so it's BestEffort.
- A Pod's memory limit becomes `memory.max` on its slice. `limits.memory: 50Mi` would put `52428800` in that file: [Saturday's OOM test](../week1/tiny-container.md) is what happens to a Pod.
- The nginx master and its 4 workers share one scope: one container, five processes.
- `systemctl status docker` shows `Memory: 48.7M (peak 54.5M)`, read from that service's `memory.current` and `memory.peak`.

---

## Mistakes and rules

| What happened | The rule |
|---|---|
| `docker ps` → permission denied on `docker.sock` | The CLI talks to the daemon through a socket owned by root and the docker group. |
| `id` didn't show docker after `usermod` | Groups are fixed when a process starts. Log in again. |
| `ps -o pid,ppid` showed only 2 lines | `-o` picks columns, not processes. Add `-e` for every process. |
| `ps -oe pid,ppid` → syntax error | Same as `tar -xfzC`: a flag that takes a value grabs the next thing. Write `-eo`. |
| `cat /proc/681/ns/net` on the VM → no such file | 681 is the PID inside the node. The VM knows it by another number. |
| `cat .../ns/net` → invalid argument | Files in `ns/` are links. Read them with `ls -l`. |
| Read 5 nginx processes as image-pull retries | No process starts until the image is pulled. It's 1 master + 4 workers. |
| Thought a Kubernetes Namespace and a Linux namespace were the same | Same word, unrelated things. See the table above. |

---

## Still open

- [ ] Prove pause and nginx share a network namespace: `docker exec <node> ls -l /proc/681/ns/net /proc/783/ns/net /proc/329/ns/net`. Which two match?
- [ ] Say in one sentence why every Pod needs a pause process.
- [ ] Post idea: "Every Kubernetes Pod has a process that does nothing, and your Pod's IP depends on it."
