import time
from threading import Thread

def wait():
    time.sleep(1)

def run_threads():
    ts = [Thread(target=wait) for _ in range(4)]
    for t in ts: t.start()
    for t in ts: t.join()

t0 = time.perf_counter()
for _ in range(4): wait()
print("one after another:", round(time.perf_counter() - t0, 2))

t0 = time.perf_counter()
run_threads()
print("four threads:     ", round(time.perf_counter() - t0, 2))
