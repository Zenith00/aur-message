import aursync
import asyncio

async def test_pub():
    print("ending")

    messager_1 = aursync.sync.Sync()
    await messager_1.init()
    messager_2 = aursync.sync.Sync()
    await messager_2.init()

    async def handle(message):
        print(f"Handling {message}")

    messager_2.subscribe(handle, "test")

    for i in range(2000):
        await messager_1.publish(str(i), "test")

    await asyncio.sleep(10)
    print("ending")

asyncio.run(test_pub())