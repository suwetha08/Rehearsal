import asyncio
import websockets

async def connect_dummy(client_id):
    uri = f"ws://localhost:8000/ws/demo-room/{client_id}?domain=backend"
    try:
        async with websockets.connect(uri) as ws:
            print(f"{client_id} connected.")
            while True:
                await ws.recv()
    except Exception as e:
        print(f"Error {client_id}: {e}")

async def main():
    await asyncio.gather(
        connect_dummy("Charlie"),
        connect_dummy("Dave")
    )

if __name__ == "__main__":
    asyncio.run(main())
