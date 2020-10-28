import signal
from concurrent.futures.thread import ThreadPoolExecutor

from pytun import TunTapDevice
import discord
from discord.ext import tasks, commands

import os

import logging

from buffer import Buffer

logging.basicConfig(level=logging.INFO)

tun = TunTapDevice(name='discip')
tun.addr = os.environ['SRC_IP']
tun.dstaddr = os.environ['DST_IP']
tun.netmask = '255.255.255.0'
tun.mtu = 1990
tun.persist(True)
tun.up()


def terminate():
    tun.down()


signal.signal(signal.SIGINT, terminate)

threadpool = ThreadPoolExecutor(2)

TOKEN = os.environ["DISCORD_TOKEN"]

bot = discord.ext.commands.Bot('!')


class MyCog(commands.Cog):
    def __init__(self, bot):
        self.chan = None
        self.ownMessage = None
        self.recvMessage = None
        self.bot = bot
        self.send_buffer = Buffer(tun.mtu)
        self.send_buffer.flush_action((lambda buffer: self.transmit_bulk_packets(buffer)))

    async def transmit_bulk_packets(self, buffer):
        if not len(buffer.packets):
            return
        message = ''
        for packet in buffer.packets:
            message += packet + " "
        message = message[:-1]
        await self.ownMessage.edit(content=message)
        await buffer.signal_free()

    def cog_unload(self):
        self.printer.cancel()
        self.autoflusher.cancel()

    @tasks.loop(seconds=1)
    async def autoflusher(self):
        if len(self.send_buffer.packets):
            print("autoflushing")
        await self.send_buffer.flush_packets()

    @tasks.loop(seconds=1)
    async def printer(self):
        if not self.chan:
            return
        while True:
            packet = await bot.loop.run_in_executor(threadpool, (lambda: tun.read(tun.mtu + 16)))
            converted = ''.join([chr(i + int('0x2800', 16)) for i in packet])
            await self.send_buffer.queue_packet(converted)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        print("message edit")
        message = after
        if message.author == self.bot.user:
            return
        packets = message.content.split()
        print("received {} packets.".format(len(packets)))
        for packet in packets:
            decoded_bytes = packet
            decoded_bytes = bytes([ord(i) - int('0x2800', 16) for i in decoded_bytes])
            tun.write(decoded_bytes)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Ready!')
        print('Logged in as ---->', self.bot.user)
        print('ID:', self.bot.user.id)
        self.chan = discord.utils.get(bot.get_all_channels(), name="general")
        print("channel is: {}".format(self.chan))
        if not self.chan:
            bot.remove_cog('MyCog')
        self.ownMessage = discord.utils.get(await self.chan.history(limit=20).flatten(), author=bot.user)
        if not self.ownMessage:
            self.ownMessage = await self.chan.send("x")
        print("waiting for other message")
        while not self.recvMessage:
            self.recvMessage = discord.utils.find(lambda m: m.author != bot.user, await self.chan.history(limit=20).flatten())
        print("found other message with content: ", self.recvMessage.content)

        self.printer.start()
        self.autoflusher.start()


bot.add_cog(MyCog(bot))
bot.run(TOKEN)
