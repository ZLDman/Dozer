"""Reactable role management commands."""

import discord
import discord.utils
from discord.ext.commands import cooldown, BucketType, has_permissions, BadArgument, MissingPermissions

from ._utils import *


try:
    from ..asyncdb.orm import orm
    from ..asyncdb import psqlt
    DatabaseClass = orm.Model
    is_asyncdb = True
    col = psqlt.Column
except ImportError:
    from .. import db
    DatabaseClass = db.DatabaseTable
    is_asyncdb = False
    class col:
        """substitute for psqlt.Column"""
        def __init__(self, sql):
            self.sql = sql

class ReactableBoard(DatabaseClass):
    """Table for react boards."""
    __tablename__ = "reactable_boards"
    __primary_key__ = ("guild_id",)
    __uniques__ = __primary_key__

    guild_id: col("bigint NOT NULL")
    channel_id: col("bigint NOT NULL")
    message_id: col("bigint NOT NULL")

    message: col("text")


def setup(bot):
    """Setup cog"""
    bot.ReactableBoard = ReactableBoard
    #bot.add_cog(News(bot))