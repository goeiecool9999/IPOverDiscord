from asyncio import Event

class Buffer:
    def __init__(self, mtu):
        self.transmit = None
        self.mtu = mtu
        self.packets = []
        self.totalSize = 0
        self.free_event = Event()

    async def signal_free(self):
        self.free_event.set()

    def flush_action(self, transmit_fun):
        self.transmit = transmit_fun

    async def flush_packets(self):
        await self.transmit(self)
        self.packets.clear()
        self.totalSize = 0

    async def queue_packet(self, string):
        while len(string) + self.totalSize > self.mtu + 4 - (max(0, len(self.packets) - 1)):
            self.free_event.clear()
            await self.free_event.wait()

        self.packets.append(string)
        self.totalSize += len(string)
        print(self.totalSize)
