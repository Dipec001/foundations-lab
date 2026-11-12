import time
from threading import Thread
from multiprocessing import Process

def count():
    n = 30_000_000
    while n > 0:
        n -= 1

def timed(label, fn):
    t0 = time.perf_counter()
    fn()
    print(label, round(time.perf_counter() - t0, 2), "s")

def sequential():
    count(); count()

def run_all(kind):
    workers = [kind(target=count) for _ in range(2)]
    for w in workers: w.start()
    for w in workers: w.join()

if __name__ == "__main__":
    timed("one after another  ", sequential)
    timed("two threads        ", lambda: run_all(Thread))
    timed("two processes      ", lambda: run_all(Process))
