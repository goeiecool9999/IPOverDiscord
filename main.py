import signal
from concurrent.futures.thread import ThreadPoolExecutor

from pytun import TunTapDevice
import discord
from discord.ext import tasks, commands

import os

import logging
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
    def __init__(self,bot):
        self.printer.start()
        self.chan = None
        self.bot = bot

    def cog_unload(self):
        self.printer.cancel()

    @tasks.loop(seconds=1)
    async def printer(self):
        if not self.chan:
            return
        packet = await bot.loop.run_in_executor(threadpool, (lambda : tun.read(tun.mtu+16)))
        converted = ''.join([chr(i + int('0x2800',16)) for i in packet])
        encoded = converted.encode('utf-8').decode('utf-8')
        await self.chan.send(content=encoded)

    @commands.Cog.listener()
    async def on_message(self,message):
        if message.author == self.bot.user:
            return
        decoded_bytes = message.content
        decoded_bytes = bytes([ord(i)-int('0x2800',16) for i in decoded_bytes])
        tun.write(decoded_bytes)


    @commands.Cog.listener()
    async def on_ready(self):
        print('Ready!')
        print('Logged in as ---->', self.bot.user)
        print('ID:', self.bot.user.id)
        self.chan = discord.utils.get(bot.get_all_channels(), name="general")
        print ("channel is: {}".format(self.chan))
        if not self.chan:
            bot.remove_cog('MyCog')

bot.add_cog(MyCog(bot))
bot.run(TOKEN)