import asyncio
import signal
import threading
from concurrent.futures.thread import ThreadPoolExecutor

from pytun import TunTapDevice
import discord
from discord.ext import tasks, commands

import os

import logging

from modem import StereoDecoder, StereoEncoder

logging.basicConfig(level=logging.INFO)

tun = TunTapDevice(name='discip')
tun.addr = os.environ['SRC_IP']
tun.dstaddr = os.environ['DST_IP']
tun.netmask = '255.255.255.0'
tun.mtu = 1600
tun.persist(True)
tun.up()


def terminate():
    tun.down()


signal.signal(signal.SIGINT, terminate)

threadpool = ThreadPoolExecutor(4)

import ctypes.util
discord.opus.load_opus(ctypes.util.find_library('opus'))
discord.opus.is_loaded()

TOKEN = os.environ["DISCORD_TOKEN"]

bot = discord.ext.commands.Bot('!', mem_cache_flags=discord.MemberCacheFlags.all())


class MyCog(commands.Cog):
    def __init__(self, bot):
        self.chan = None
        self.bot = bot
        self.other_bot = None
        self.encoder = StereoEncoder()
        self.decoder = StereoDecoder(lambda packet: self.handle_packet(packet))
        self.vcclient = None

        self.run_send_thread = True
        self.send_thread = threading.Thread(target=self.send_loop)

    def cog_unload(self):
        self.run_send_thread = False
        self.send_thread.join()
        self.vcclient.disconnect()

    def handle_packet(self,packet):
        if len(packet) >= 4:
            tun.write(packet)

    def send_loop(self):
        while self.run_send_thread:
            packet = tun.read(tun.mtu + 16)
            self.encoder.set_bytes_to_play(packet)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Ready!')
        print('Logged in as ---->', self.bot.user)
        print('ID:', self.bot.user.id)
        self.chan = discord.utils.get(bot.get_all_channels(), name="General")
        print("channel is: {}".format(self.chan))
        if not self.chan:
            bot.remove_cog('MyCog')

        self.vcclient = await self.chan.connect()
        if not self.vcclient:
            bot.remove_cog('MyCog')

        while not self.other_bot:
            print("looking for peer")
            self.other_bot = discord.utils.find(lambda m: m.id != self.bot.user.id and m.bot, self.chan.members)
            await asyncio.sleep(1)

        await self.vcclient.disconnect()
        self.vcclient = await self.chan.connect()

        self.vcclient.listen(discord.UserFilter(self.decoder, user=self.other_bot))
        # self.vcclient.listen(discord.UserFilter(discord.WaveSink('test.wav'), user=self.other_bot))
        self.vcclient.play(self.encoder)

        self.send_thread.start()


bot.add_cog(MyCog(bot))
bot.run(TOKEN)
