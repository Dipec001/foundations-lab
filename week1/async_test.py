import asyncio, time

async def good():
    await asyncio.sleep(1)

async def bad():
    time.sleep(1)

async def run(fn):
    t0 = time.perf_counter()
    await asyncio.gather(*[fn() for _ in range(4)])
    print(fn.__name__, round(time.perf_counter() - t0, 2))

async def main():
    await run(good)
    await run(bad)

asyncio.run(main())
