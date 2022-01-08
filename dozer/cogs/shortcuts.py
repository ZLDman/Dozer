
import collections
import asyncio
import csv
import io
import logging
from typing import Dict, List
import aiohttp
import discord
from discord.ext.commands import BadArgument, guild_only
from discord.ext.commands import NotOwner
from discord.ext.commands.core import has_permissions

from ._utils import *
from ..asyncdb.orm import orm
from ..asyncdb import psqlt, configcache


class Shortcuts(Cog):
    MAX_LEN = 20
    def __init__(self, bot):
        """cog init"""
        super().__init__(bot)
        self.settings_cache = configcache.AsyncConfigCache(ShortcutSetting)
        self.cache = configcache.AsyncConfigCache(Shortcuts)
        self.guild_table: Dict[int, Dict[str, str]] = {}

    """Commands for managing shortcuts/macros."""
    @has_permissions(manage_guild=True)
    @group(invoke_without_command=True)
    async def shortcuts(self, ctx):
        """
        Display shortcut information
        """
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)
        if settings is None:
            raise BadArgument("This server has no shortcut configuration.")
        if not settings.approved:
            await ctx.send("This server is not approved for shortcuts.")
            return
        e = discord.Embed()
        e.title = "Server shortcut configuration"
        #e.add_field("Shortcut spreadsheet", settings.spreadsheet or "Unset")
        e.add_field("Shortcut prefix", settings.prefix or "[unset]")
        await ctx.send(embed=e)
    
    @shortcuts.command()
    async def approve(self, ctx):
        """Approve the server to use shortcuts"""
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('you are not a developer!')
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)
        if settings is None:
            settings = ShortcutSetting() 
            settings.guild_id = ctx.guild.id
            #settings.spreadsheet = ""
            settings.prefix = "!"
            settings.approved = True
            await settings.insert()
        else:
            settings.approved = True
            await settings.update()
        self.settings_cache.invalidate_entry(guild_id=ctx.guild.id)
        

    @shortcuts.command()
    async def revoke(self, ctx):
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('you are not a developer!')
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)
        if settings is not None:
            settings.approved = False
            await settings.update()
            self.settings_cache.invalidate_entry(guild_id=ctx.guild.id)
        await ctx.send("Shortcuts have been revoked from this guild.")
    
    @has_permissions(manage_guild=True)
    @shortcuts.command()
    async def add(self, ctx, cmd_name, *, cmd_msg):
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)
        if settings is None or not settings.approved:
            raise BadArgument("this feature is not approved yet")
        if len(cmd_name) > self.MAX_LEN:
            raise BadArgument(f"command names can only be up to {self.MAX_LEN} chars long")
        if not cmd_msg:
            raise BadArgument("can't have null message")
        
        ent: ShortcutEntry = await self.cache.query_one(guild_id=ctx.guild.id, name=cmd_name)
        if ent:
            ent.value = cmd_msg
            await ent.update()
        else:
            ent = ShortcutEntry()
            ent.value = cmd_msg
            await ent.insert()
        self.cache.invalidate_entry(guild_id=ctx.guild.id, name=cmd_name)

        await ctx.send("Updated command successfully.")

    @has_permissions(manage_guild=True)
    @shortcuts.command()
    async def remove(self, ctx, cmd_name):
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)
        if settings is None or not settings.approved:
            raise BadArgument("this feature is not approved yet")
        
        ent: ShortcutEntry = await self.cache.query_one(guild_id=ctx.guild.id, name=cmd_name)
        if ent:
            await ent.delete()
        self.cache.invalidate_entry(guild_id=ctx.guild.id, name=cmd_name)

        await ctx.send("Removed command successfully.")
    
    @shortcuts.command()
    async def list(self, ctx):
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id=ctx.guild.id)
        if settings is None or not settings.approved:
            raise BadArgument("this feature is not approved yet")
        
        ents: List[ShortcutEntry] = await ShortcutEntry.select(guild_id=ctx.guild.id)
        embed = discord.Embed()
        embed.title = "shortcuts for this guild"
        for e in ents:
            embed.add_field(e.name, e.value[:20])
        await ctx.send(embed=embed)

    add.example_usage = """
    `{prefix}shortcuts add hello Hello, World!!!!` - adds !hello to the server
    """

    remove.example_usage = """
    `{prefix}shortcuts remove hello  - removes !hello
    """
    list.example_usage = """
    `{prefix}shortcuts list - lists all shortcuts
    """
        

        
    async def reload_sheets(self, guild=None):
        raise NotImplementedError("you should not call this")
        if guild is None:
            ents = ShortcutSetting.select()
        else:
            ents = [self.cache.query_one(guild_id=guild.id)]

        for e in ents:
            if not e.approved:
                # clear table if not approved
                self.guild_table[e.guild_id] = {}
                continue
            url = e.spreadsheet
            new_table: Dict[str, str] = {}
            try:
                async with self.bot.http_session.get(url) as resp:
                    csv_data = io.StringIO(await resp.read())
                reader = csv.DictReader(csv_data)
                for row in reader:
                    new_table[row['command']] = row['text']
            except Exception as e:
                logging.getLogger("dozer").exception(f"Can't read csv data for {e.guild_id} -> {url}: ", e)
                continue
        pass

    @Cog.listener()
    async def on_ready(self):
        """reload sheets on_ready"""
        pass
    
    @Cog.listener()
    async def on_message(self, msg):
        """prefix scanner"""
        if not msg.guild:
            return
        setting = self.settings_cache.query_one(guild_id=msg.guild.id)
        if setting is None or not setting.approved:
            return

        split = msg.content.split()
        if not split or len(split[0]) <= len(setting.prefix):
            return
        
        first = split[0]
        if not first.startswith(setting.prefix):
            return
        
        ent = self.cache.query_one(guild_id=msg.guild.id, name=first[len(setting.prefix):])
        if ent is None:
            return 
        await msg.channel.send(ent.value)

        


class ShortcutSetting(orm.Model):
    """Provides a DB config to track mutes."""
    __tablename__ = 'shortcut_settings'
    __primary_key__ = ("guild_id",)
    guild_id: psqlt.bigint # guild id
    approved: psqlt.boolean # whether the guild is approved for the feature or not
    spreadsheet: psqlt.text # the url of the spreadsheet
    prefix: psqlt.text # the prefix of the commands

class ShortcutEntry(orm.Model):
    """Provides a DB config to track mutes."""
    __tablename__ = 'shortcuts'
    __primary_key__ = ("guild_id", "name")
    guild_id: psqlt.bigint
    name: psqlt.varchar(Shortcuts.MAX_LEN)
    value: psqlt.text