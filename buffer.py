from threading import Event, Lock

class Buffer:
    def __init__(self):
        self.transmit = None
        self.buffer_lock = Lock()
        self.packets = []
        self.totalSize = 0
        self.free_event = Event()

    def signal_free(self):
        self.free_event.set()

    def clear(self):
        self.packets.clear()
        self.totalSize = 0

    def queue_packet(self, string):
        with self.buffer_lock:
            while len(string)*2 + self.totalSize > 8*1024*1024 - len(self.packets):
                self.free_event.clear()
                self.free_event.wait()

            self.packets.append(string)
            self.totalSize += len(string)*2
