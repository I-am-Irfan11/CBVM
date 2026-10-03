import asyncio

from fastapi.encoders import jsonable_encoder


class EventHub:
    def __init__(self):
        self.clients = set()

    def subscribe(self):
        queue = asyncio.Queue(maxsize=100)
        self.clients.add(queue)
        return queue

    def unsubscribe(self, queue):
        self.clients.discard(queue)

    async def publish(self, kind, data):
        event = jsonable_encoder({"type": kind, "data": data})
        for queue in tuple(self.clients):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
