"""Role management commands."""

import typing
import logging
import discord
import discord.utils
from discord.ext.commands import cooldown, BucketType, has_permissions, BadArgument, MissingPermissions, guild_only

from ._utils import *
from ..asyncdb.orm import orm
from ..asyncdb import psqlt
blurple = discord.Color.blurple()
dozer_logger = logging.getLogger('dozer')

class Roles(Cog):
    """Commands for role management."""

    def __init__(self, bot):
        super().__init__(bot)
        for command in self.giveme.walk_commands():
            @command.before_invoke
            async def givemeautopurge(self, ctx):
                """Before invoking a giveme command, run a purge"""
                if await self.ctx_purge(ctx):
                    await ctx.send("Purged missing roles")

    @staticmethod
    def normalize(name):
        """Normalizes a role for consistency in the DB."""
        return name.strip().casefold()

    @staticmethod
    async def safe_message_fetch(ctx, menu=None, channel=None, message_id=None):
        """Used to safely get a message and raise an error message cannot be found"""
        try:
            if menu:
                channel = ctx.guild.get_channel(menu.channel_id)
                return await channel.fetch_message(menu.message_id)
            else:
                if channel:
                    return await channel.fetch_message(message_id)
                else:
                    return await ctx.message.channel.fetch_message(message_id)
        except discord.HTTPException:
            raise BadArgument("That message does not exist or is not in this channel!")

    @staticmethod
    async def add_to_message(message, entry):
        """Adds a reaction role to a message"""
        await message.add_reaction(entry.reaction)
        await entry.update_or_add()

    @staticmethod
    async def del_from_message(message, entry):
        """Removes a reaction from a message"""
        await message.clear_reaction(entry.reaction)

    @Cog.listener()
    async def on_raw_message_delete(self, payload):
        """Used to remove dead reaction role entries"""
        message_id = payload.message_id
        await ReactionRole.delete(message_id=message_id)
        await RoleMenu.delete(message_id=message_id)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Raw API event for reaction add, passes event to action handler"""
        await self.on_raw_reaction_action(payload)

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Raw API event for reaction remove, passes event to action handler"""
        await self.on_raw_reaction_action(payload)

    async def on_raw_reaction_action(self, payload):
        """Called whenever a reaction is added or removed"""
        message_id = payload.message_id
        reaction = str(payload.emoji)
        reaction_roles = await ReactionRole.select(message_id=message_id, reaction=reaction)
        if len(reaction_roles):
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(reaction_roles[0].role_id)
            if member.bot:
                return
            if role:
                try:
                    if payload.event_type == "REACTION_ADD":
                        await member.add_roles(role, reason="Automatic Reaction Role")
                    elif payload.event_type == "REACTION_REMOVE":
                        await member.remove_roles(role, reason="Automatic Reaction Role")
                except discord.Forbidden:
                    dozer_logger.debug(f"Unable to add reaction role in guild {guild} due to missing permissions")

    @Cog.listener('on_member_join')
    async def on_member_join(self, member):
        """Restores a member's roles when they join if they have joined before."""
        if 'silent' in self.bot.config and self.bot.config['silent']:
            return

        me = member.guild.me
        top_restorable = me.top_role.position if me.guild_permissions.manage_roles else 0

        missing_roles = await MissingRole.select(guild_id=member.guild.id, member_id=member.id)
        # no missing rules to return
        if not missing_roles:
            return

        valid, cant_give, missing = set(), set(), set()
        for missing_role in missing_roles:
            role = member.guild.get_role(missing_role.role_id)
            if role is None:  # Role with that ID does not exist
                missing.add(missing_role.role_name)
            elif role.position > top_restorable:
                cant_give.add(role.name)
            else:
                valid.add(role)

        await member.add_roles(*valid)
        if not missing and not cant_give:
            return

        e = discord.Embed(title=f'Welcome back to the {member.guild.name} server, {member}!', color=discord.Color.blue())
        if missing:
            e.add_field(name='I couldn\'t restore these roles, as they don\'t exist.', value='\n'.join(sorted(missing)))
        if cant_give:
            e.add_field(name='I couldn\'t restore these roles, as I don\'t have permission.',
                        value='\n'.join(sorted(cant_give)))

        # let's also make regiving roles atomic...ish.
        async with orm.acquire() as conn:
            for missing_role in missing_roles:
                await missing_role.delete(_conn=conn)

        # mmmm i love questionable code i didn't write.
        send_perms = discord.Permissions()
        send_perms.update(send_messages=True, embed_links=True)
        try:
            dest = next(channel for channel in member.guild.text_channels if channel.permissions_for(me) >= send_perms)
        except StopIteration:
            dest = await member.guild.owner.create_dm()

        await dest.send(embed=e)

    @Cog.listener('on_member_remove')
    async def on_member_remove(self, member):
        """Saves a member's roles when they leave in case they rejoin."""
        guild_id = member.guild.id
        member_id = member.id
        async with orm.acquire() as conn:
            await conn.fetch(f"DELETE FROM {MissingRole.table_name()} WHERE member_id=$1 AND guild_id=$2", member_id, guild_id)
            for role in member.roles[1:]:  # Exclude the @everyone role
                await MissingRole(role_id=role.id, role_name=role.name,
                                  member_id=member_id, guild_id=guild_id).insert(_upsert="ON CONFLICT DO NOTHING", _conn=conn)

    async def giveme_purge(self, role_id_list):
        """Purges roles in the giveme database that no longer exist"""
        if not role_id_list:
            return
        async with orm.acquire() as conn:
            await conn.fetch(f"DELETE FROM {GiveableRole.table_name()} "
                             f"WHERE role_id=ANY({','.join('$' + str(i + 1) for i in range(len(role_id_list)))})", role_id_list)

    async def ctx_purge(self, ctx):
        """Purges all giveme roles that no longer exist in a guild"""
        counter = 0
        roles = await GiveableRole.select(guild_id=ctx.guild.id)
        guild_roles = []
        role_id_list = []
        for i in ctx.guild.roles:
            guild_roles.append(i.id)
        for ent in roles:
            if ent.role_id not in guild_roles:
                role_id_list.append(ent.role_id)
                counter += 1
        await self.giveme_purge(role_id_list)
        return counter

    @Cog.listener("on_guild_role_delete")
    async def on_guild_role_delete(self, role):
        """Automatically delete giveme roles if they are deleted from the guild"""
        rolelist = [role.id]
        await self.giveme_purge(rolelist)

    @group(invoke_without_command=True, case_insensitive=True)
    @bot_has_permissions(manage_roles=True)
    async def giveme(self, ctx, *, roles):
        """Give you one or more giveable roles, separated by commas."""
        norm_names = set(self.normalize(name) for name in roles.split(','))

        giveable_ids = set(gr.role_id for gr in await GiveableRole.select(guild_id=ctx.guild.id))
        valid = set(role for role in ctx.guild.roles if role.id in giveable_ids and self.normalize(role.name) in norm_names)

        already_have = valid & set(ctx.author.roles)
        given = valid - already_have
        await ctx.author.add_roles(*given)

        e = discord.Embed(color=discord.Color.blue())
        if given:
            given_names = sorted((role.name for role in given), key=str.casefold)
            e.add_field(name='Gave you {} role(s)!'.format(len(given)), value='\n'.join(given_names), inline=False)
        if already_have:
            already_have_names = sorted((role.name for role in already_have), key=str.casefold)
            e.add_field(name='You already have {} role(s)!'.format(len(already_have)),
                        value='\n'.join(already_have_names), inline=False)
        extra = len(norm_names) - len(valid)
        if extra > 0:
            e.add_field(name='{} role(s) could not be found!'.format(extra),
                        value='Use `{0.prefix}{0.invoked_with} list` to find valid giveable roles!'.format(ctx),
                        inline=False)
        await ctx.send(embed=e)

    giveme.example_usage = """
    `{prefix}giveme Java` - gives you the role called Java, if it exists
    `{prefix}giveme Java, Python` - gives you the roles called Java and Python, if they exist
    """

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def purge(self, ctx):
        """Force a purge of giveme roles that no longer exist in the guild"""
        counter = await self.ctx_purge(ctx)
        await ctx.send("Purged {} role(s)".format(counter))

    @cooldown(1, 10, BucketType.channel)
    @giveme.group(name='list', invoke_without_command=True)
    @bot_has_permissions(manage_roles=True)
    async def list_roles(self, ctx):
        """Lists all giveable roles for this server."""
        names = [ctx.guild.get_role(ent.role_id).name for ent in await GiveableRole.select(guild_id=ctx.guild.id)]
        e = discord.Embed(title='Roles available to self-assign', color=discord.Color.blue())
        e.description = '\n'.join(sorted(names, key=str.casefold))
        await ctx.send(embed=e)

    list_roles.example_usage = """
    `{prefix}giveme list` - lists all giveable roles
    """

    @list_roles.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_guild=True)
    async def add(self, ctx, role: discord.Role):
        """Makes an existing role giveable, or creates one if it doesn't exist. Name must not contain commas.
        Similar to create, but will use an existing role if one exists."""
        if ',' in role.name:
            raise BadArgument('giveable role names must not contain commas!')
        norm_name = self.normalize(role.name)

        if await GiveableRole.select_one(role_id=role.id):
            raise BadArgument('that role already exists and is giveable!')
        candidates = [role for role in ctx.guild.roles if self.normalize(role.name) == norm_name]

        if len(candidates) > 1:
            raise BadArgument('{} roles with that name exist!'.format(len(candidates)))

        await GiveableRole(role_id=role.id, guild_id=ctx.guild.id).insert()
        await ctx.send(f'Role "{role.name}" added! Use `{ctx.prefix}giveme {role.name}` to get it!')

    add.example_usage = """
    `{prefix}giveme list add Java` - creates or finds a role named "Java" and makes it giveable
    `{prefix}giveme Java` - gives you the Java role that was just found or created
    """

    @list_roles.command(name="remove")
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_guild=True)
    async def removefromlist(self, ctx, role: discord.Role):
        """Deletes and removes a giveable role."""

        norm_name = self.normalize(role.name)
        ent = await GiveableRole.select_one(role_id=role.id)
        if ent is None:
            raise BadArgument('that role does not exist or is not giveable!')
        await ent.delete()

        await ctx.send('Role "{0}" deleted from list!'.format(role.name))

    removefromlist.example_usage = """
    `{prefix}giveme list remove Java` - removes the role "Java" from the list of giveable roles but does not remove it from the server or members who have it 
    """

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    async def remove(self, ctx, *, roles):
        """Removes multiple giveable roles from you. Names must be separated by commas."""
        norm_names = [self.normalize(name) for name in roles.split(',')]
        giveable_ids = set(gr.role_id for gr in await GiveableRole.select(guild_id=ctx.guild.id))
        valid = set(role for role in ctx.guild.roles if role.id in giveable_ids and self.normalize(role.name) in norm_names)

        removed = valid & set(ctx.author.roles)
        dont_have = valid - removed
        await ctx.author.remove_roles(*removed)

        e = discord.Embed(color=discord.Color.blue())
        if removed:
            removed_names = sorted((role.name for role in removed), key=str.casefold)
            e.add_field(name='Removed {} role(s)!'.format(len(removed)), value='\n'.join(removed_names), inline=False)
        if dont_have:
            dont_have_names = sorted((role.name for role in dont_have), key=str.casefold)
            e.add_field(name='You didn\'t have {} role(s)!'.format(len(dont_have)), value='\n'.join(dont_have_names),
                        inline=False)
        extra = len(norm_names) - len(valid)
        if extra > 0:
            e.add_field(name='{} role(s) could not be found!'.format(extra),
                        value='Use `{0.prefix}giveme list` to find valid giveable roles!'.format(ctx),
                        inline=False)
        await ctx.send(embed=e)

    remove.example_usage = """
    `{prefix}giveme remove Java` - removes the role called "Java" from you (if it can be given with `{prefix}giveme`)
    `{prefix}giveme remove Java, Python` - removes the roles called "Java" and "Python" from you
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def give(self, ctx, member: discord.Member, *, role: discord.Role):
        """Gives a member a role. Not restricted to giveable roles."""
        if role > ctx.author.top_role:
            raise BadArgument('Cannot give roles higher than your top role!')
        await member.add_roles(role)
        await ctx.send(f'Successfully gave {member} `{role}`!')
    give.example_usage = """
    `{prefix}give cooldude#1234 Java` - gives cooldude any role, giveable or not, named Java
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def take(self, ctx, member: discord.Member, *, role: discord.Role):
        """Takes a role from a member. Not restricted to giveable roles."""
        if role > ctx.author.top_role:
            raise BadArgument('Cannot take roles higher than your top role!')
        await member.remove_roles(role)
        await ctx.send(f'Successfully took `{role}` from {member}!')

    take.example_usage = """
    `{prefix}take cooldude#1234 Java` - takes any role named Java, giveable or not, from cooldude
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    async def rolecolor(self, ctx, role: discord.Role, color: discord.Color = None):
        """Displays the color of a given role, or sets it to a new value."""
        # required perms are conditional based on arguments
        if color is not None:
            if not ctx.channel.permissions_for(ctx.author).manage_roles:
                raise MissingPermissions(["manage_roles"])
            await role.edit(color=color)
            message = f"Set role color of `{role}` to **{color}**!"
        else:
            message = f"The role color of `{role}` is **{role.color}**"

        await ctx.send(embed=discord.Embed(description=message, color=role.color))

    rolecolor.example_usage = """
    `{prefix}rolecolor "Simbot Red"` - displays the color of the "Simbot Red" role in hexcode format
    `{prefix}rolecolor Bolb #FCC21B` - set the color of the "Bolb" role to #FCC21B
    """
    async def update_role_menu(self, ctx, menu):
        """Updates a reaction role menu"""
        menu_message = await self.safe_message_fetch(ctx, menu=menu)

        menu_embed = discord.Embed(title=f"Role Menu: {menu.name}")
        menu_entries = await ReactionRole.select(message_id=menu.message_id)
        for entry in menu_entries:
            role = ctx.guild.get_role(entry.role_id)
            menu_embed.add_field(name=f"Role: {role}", value=f"{entry.reaction}: {role.mention}", inline=False)
        menu_embed.set_footer(text=f"React to get a role\nMenu ID: {menu_message.id}, Total roles: {len(menu_entries)}")
        await menu_message.edit(embed=menu_embed)

    @group(invoke_without_command=True, aliases=["reactionrole", "reactionroles"], case_insensitive=True)
    @bot_has_permissions(manage_roles=True, embed_links=True)
    @has_permissions(manage_roles=True)
    @guild_only()
    async def rolemenu(self, ctx):
        """Base command for setting up and tracking reaction roles"""
        rolemenus = await RoleMenu.select(guild_id=ctx.guild.id)
        embed = discord.Embed(title="Reaction Role Messages", color=blurple)
        boundroles = []
        for rolemenu in rolemenus:
            menu_entries = await ReactionRole.select(message_id=rolemenu.message_id)
            for role in menu_entries:
                boundroles.append(role.message_id)
            link = f"https://discordapp.com/channels/{rolemenu.guild_id}/{rolemenu.channel_id}/{rolemenu.message_id}"
            embed.add_field(name=f"Menu: {rolemenu.name}", value=f"[Contains {len(menu_entries)} role watchers]({link})", inline=False)
        unbound_reactions = await ReactionRole.fetchrow(f"""SELECT * FROM {ReactionRole.__tablename__} WHERE message_id != all($1)"""
                                                f""" and guild_id = $2;""", boundroles, ctx.guild.id)
        combined_unbound = {}  # The following code is too group individual reaction role entries into the messages they are associated with
        if unbound_reactions:
            for unbound in unbound_reactions:
                guild_id = unbound.get("guild_id")
                channel_id = unbound.get("channel_id")
                message_id = unbound.get("message_id")
                if combined_unbound.get(message_id):
                    combined_unbound[message_id]["total"] += 1
                else:
                    combined_unbound[message_id] = {"guild_id": guild_id, "channel_id": channel_id, "message_id": message_id, "total": 1}
        for combined in combined_unbound.values():
            gid = combined["guild_id"]
            cid = combined["channel_id"]
            mid = combined["message_id"]
            total = combined["total"]
            link = f"https://discordapp.com/channels/{gid}/{cid}/{mid}"
            embed.add_field(name=f"Custom Message: {mid}", value=f"[Contains {total} role watchers]({link})", inline=False)
        embed.description = f"{ctx.bot.user.display_name} is tracking ({len(rolemenus) + len(combined_unbound)}) " \
                            f"reaction role message(s) in **{ctx.guild}**"
        await ctx.send(embed=embed)

    rolemenu.example_usage = """
    `{prefix}rolemenu createmenu #roles Example role menu`: Creates an empty role menu embed
    `{prefix}rolemenu addrole <message id> @robots 🤖:` adds the reaction role 'robots' to the target message
    `{prefix}rolemenu delrole <message id> @robots:` removes the reaction role 'robots' from the target message
    """

    @rolemenu.command()
    @bot_has_permissions(manage_roles=True, embed_links=True)
    @has_permissions(manage_roles=True)
    @guild_only()
    async def createmenu(self, ctx, channel: discord.TextChannel, *, name):
        """Creates a blank reaction role menu"""
        menu_embed = discord.Embed(title=f"Role Menu: {name}", description="React to get a role")
        message = await channel.send(embed=menu_embed)

        e = RoleMenu(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            message_id=message.id,
            name=name
        )
        await e.update_or_add()

        menu_embed.set_footer(text=f"Menu ID: {message.id}, Total roles: {0}")
        await message.edit(embed=menu_embed)

        e = discord.Embed(color=blurple)
        link = f"https://discordapp.com/channels/{ctx.guild.id}/{message.channel.id}/{message.id}"
        e.add_field(name='Success!', value=f"I added created role menu [\"{name}\"]({link}) in channel {channel.mention}")
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    createmenu.example_usage = """
    `{prefix}rolemenu createmenu #roles Example role menu`: Creates an empty role menu embed
    """

    @rolemenu.command(aliases=["add"])
    @bot_has_permissions(manage_roles=True, embed_links=True)
    @has_permissions(manage_roles=True)
    @guild_only()
    async def addrole(self, ctx, channel: typing.Optional[discord.TextChannel], message_id: int, role: discord.Role,
                      emoji: typing.Union[discord.Emoji, str]):
        """Adds a reaction role to a message or a role menu"""
        if isinstance(emoji, discord.Emoji) and emoji.guild_id != ctx.guild.id:
            raise BadArgument(f"The emoji {emoji} is a custom emoji not from this server!")

        if role > ctx.author.top_role:
            raise BadArgument('Cannot give roles higher than your top role!')

        if role > ctx.me.top_role:
            raise BadArgument('Cannot give roles higher than my top role!')

        if role == ctx.guild.default_role:
            raise BadArgument("Cannot give @\N{ZERO WIDTH SPACE}everyone!")

        if role.managed:
            raise BadArgument("I am not allowed to assign that role!")

        menu_return = await RoleMenu.select(guild_id=ctx.guild.id, message_id=message_id)
        menu = menu_return[0] if len(menu_return) else None
        message = await self.safe_message_fetch(ctx, menu=menu, channel=channel, message_id=message_id)

        reaction_role = ReactionRole(
            guild_id=ctx.guild.id,
            channel_id=message.channel.id,
            message_id=message.id,
            role_id=role.id,
            reaction=str(emoji)
        )

        old_reaction = await ReactionRole.select(message_id=message.id, role_id=role.id)
        if len(old_reaction):
            await self.del_from_message(message, old_reaction[0])
        await self.add_to_message(message, reaction_role)

        if menu:
            await self.update_role_menu(ctx, menu)

        e = discord.Embed(color=blurple)
        link = f"https://discordapp.com/channels/{ctx.guild.id}/{message.channel.id}/{message_id}"
        shortcut = f"[{menu.name}]({link})" if menu else f"[{message_id}]({link})"
        e.add_field(name='Success!', value=f"I added {role.mention} to message \"{shortcut}\" with reaction {emoji}")
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    addrole.example_usage = """
    -----To target a role menu use this format-----
    `{prefix}rolemenu addrole <message id> <@robots or "Robots"> 🤖`
   -----To target a custom message use this format-----
    `{prefix}rolemenu addrole <channel> <message id> <@robots or "Robots"> 🤖`
    """

    @rolemenu.command(aliases=["del"])
    @bot_has_permissions(manage_roles=True, embed_links=True)
    @has_permissions(manage_roles=True)
    @guild_only()
    async def delrole(self, ctx, channel: typing.Optional[discord.TextChannel], message_id: int, role: discord.Role):
        """Removes a reaction role from a message or a role menu"""

        menu_return = await RoleMenu.select(guild_id=ctx.guild.id, message_id=message_id)
        menu = menu_return[0] if len(menu_return) else None
        message = await self.safe_message_fetch(ctx, menu=menu, channel=channel, message_id=message_id)

        reaction = await ReactionRole.select(message_id=message.id, role_id=role.id)
        if len(reaction):
            await self.del_from_message(message, reaction[0])
            await ReactionRole.delete(message_id=message.id, role_id=role.id)
        if menu:
            await self.update_role_menu(ctx, menu)

        e = discord.Embed(color=blurple)
        link = f"https://discordapp.com/channels/{ctx.guild.id}/{message.channel.id}/{message_id}"
        shortcut = f"[{menu.name}]({link})" if menu else f"[{message_id}]({link})"
        e.add_field(name='Success!', value=f"I removed {role.mention} from message {shortcut}")
        e.set_footer(text='Triggered by ' + ctx.author.display_name)
        await ctx.send(embed=e)

    delrole.example_usage = """
    -----To target a role menu use this format-----
    `{prefix}rolemenu delrole <message id> <@robots or "Robots">`
    -----To target a custom message use this format-----
    `{prefix}rolemenu delrole <channel> <message id> <@robots or "Robots">`
    """

class RoleMenu(orm.Model):
    """Contains a role menu, used for editing and initial create"""
    __tablename__ = 'role_menus'
    __primary_key__ = ('message_id',)

    guild_id: psqlt.bigint
    channel_id: psqlt.bigint
    message_id: psqlt.bigint
    name: psqlt.text

class ReactionRole(orm.Model):
    """Contains a role menu entry"""
    __tablename__ = 'reaction_roles'
    __primary_key__ = ('message_id', 'role_id')

    guild_id: psqlt.bigint
    channel_id: psqlt.bigint
    message_id: psqlt.bigint
    role_id: psqlt.bigint
    reaction: psqlt.varchar(100)

class GiveableRole(orm.Model):
    """Database object for maintaining a list of giveable roles."""
    __tablename__ = 'giveable_roles'
    __primary_key__ = ("role_id",)

    role_id: psqlt.bigint
    guild_id: psqlt.bigint

class MissingRole(orm.Model):
    """Holds what roles a given member had when they last left the guild."""
    __tablename__ = 'missing_roles'
    __primary_key__ = ('role_id', 'member_id')

    role_id: psqlt.bigint
    guild_id: psqlt.bigint
    member_id: psqlt.bigint
    role_name: psqlt.varchar(100)


def setup(bot):
    """Adds the roles cog to the main bot project."""
    bot.add_cog(Roles(bot))
