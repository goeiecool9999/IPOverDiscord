class Buffer:
    def __init__(self, mtu):
        self.transmit = None
        self.mtu = mtu
        self.packets = []
        self.totalSize = 0

    def flush_action(self, transmit_fun):
        self.transmit = transmit_fun

    async def flush_packets(self):
        await self.transmit(self)
        self.packets.clear()
        self.totalSize = 0


    async def queue_packet(self, string):
        if len(string) + self.totalSize >= self.mtu - (max(0, len(self.packets) - 1)):
            await self.flush_packets()

        self.packets.append(string)
        self.totalSize += len(string)
        print(self.totalSize)
