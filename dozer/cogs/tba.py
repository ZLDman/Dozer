"""A series of commands that talk to The Blue Alliance."""
import datetime
import itertools

from datetime import timedelta
from pprint import pformat
from urllib.parse import quote as urlquote, urljoin

import discord
from discord.ext.commands import BadArgument
import googlemaps
import async_timeout
#import tbapi
import aiotba
from geopy.geocoders import Nominatim

from ._utils import *

blurple = discord.Color.blurple()


class TBA(Cog):
    """Commands that talk to The Blue Alliance"""
    def __init__(self, bot):
        super().__init__(bot)
        tba_config = bot.config['tba']
        self.gmaps_key = bot.config['gmaps_key']
        self.session = aiotba.TBASession(tba_config['key'], self.bot.http._session)
        #self.parser = tbapi.TBAParser(tba_config['key'], cache=False)

    @group(invoke_without_command=True)
    async def tba(self, ctx, team_num: int):
        """
        Get FRC-related information from The Blue Alliance.
        If no subcommand is specified, the `team` subcommand is inferred, and the argument is taken as a team number.
        """
        await self.team.callback(self, ctx, team_num)

    tba.example_usage = """
    `{prefix}tba 5052` - show information on team 5052, the RoboLobos
    """

    @tba.command()
    @bot_has_permissions(embed_links=True)
    async def team(self, ctx, team_num: int):
        """Get information on an FRC team by number."""
        try:
            team_data = await self.session.team(team_num)
            e = discord.Embed(color=blurple,
                              title='FIRST® Robotics Competition Team {}'.format(team_num),
                              url='https://www.thebluealliance.com/team/{}'.format(team_num))
            e.set_thumbnail(url='https://frcavatars.herokuapp.com/get_image?team={}'.format(team_num))
            e.add_field(name='Name', value=team_data.nickname)
            e.add_field(name='Rookie Year', value=team_data.rookie_year)
            e.add_field(name='Location',
                        value='{0.city}, {0.state_prov} {0.postal_code}, {0.country}'.format(team_data))
            e.add_field(name='Website', value=team_data.website)
            e.add_field(name='Championship', value=team_data.home_championship[datetime.datetime.today().year])
            #e.add_field(name='TBA Link', value='https://www.thebluealliance.com/team/{}'.format(team_num))
            e.set_footer(text='Triggered by ' + ctx.author.display_name)
            await ctx.send(embed=e)
        except aiotba.http.AioTBAError:
            raise BadArgument("Couldn't find data for team {}".format(team_num))

    team.example_usage = """
    `{prefix}tba team 4131` - show information on team 4131, the Iron Patriots
    """

    @tba.command()
    @bot_has_permissions(embed_links=True)
    async def media(self, ctx, team_num: int, year: int=None):
        """Get media of a team for a given year. Defaults to current year."""
        if year is None:
            year = datetime.datetime.today().year
        try:
            team_media = await self.session.team_media(team_num, year)
            if not team_media:
                await ctx.send(f"Unfortunately, there doesn't seem to be any media for team {team_num} in {year}...")
                return

            pages = []
            base = f"FRC Team {team_num} {year} Media: "
            for media in team_media:

                if media.type == "youtube":
                    pages.append(f"**{base} YouTube** \nhttps://youtu.be/{media.foreign_key}")
                    continue
                else:
                    name, url, img_url = {
                        "cdphotothread": (
                            "Chief Delphi",
                            "https://www.chiefdelphi.com/media/photos/{media.foreign_key}",
                            "https://www.chiefdelphi.com/media/img/{media.details['image_partial']}"
                        ),
                        "imgur": (
                            "Imgur",
                            "https://imgur.com/{media.foreign_key}",
                            "https://i.imgur.com/{media.foreign_key}.png"
                        ),
                        "instagram-image": (
                           "instagram",
                            "https://www.instagram.com/p/{media.foreign_key}",
                            "https://www.instagram.com/p/{media.foreign_key}/media"
                        ),
                        "grabcad": (
                            "GrabCAD",
                            "https://grabcad.com/library/{media.foreign_key}",
                            "{media.details['model_image']}"
                        )
                    }.get(media.type, (None, None, None))
                    if name is None:
                        print("Whack media", media.__dict__, "unprocessed")
                        continue
                    page = discord.Embed(title=base + name, url=url.format(media=media))
                    page.set_image(url=img_url.format(media=media))
                    pages.append(page)

            await paginate(ctx, pages)

        except aiotba.http.AioTBAError:
            raise BadArgument("Couldn't find data for team {}".format(team_num))

    media.example_usage = """
    `{prefix}`tba media 971 2016` - show available media from team 971 Spartan Robotics in 2016
    """

    @tba.command()
    @bot_has_permissions(embed_links=True)
    async def awards(self, ctx, team_num: int, year: int=None):
        """Gets a list of awards the specified team has won during a year. """
        try:
            awards_data = await self.session.team_awards(team_num, year=year)
        except aiotba.http.AioTBAError:
            raise BadArgument("Couldn't find data for team {}".format(team_num))

        pages = []
        for year, awards in itertools.groupby(awards_data, lambda a: a.year):
            e = discord.Embed(title=f"Awards for FRC Team {team_num} in {year}:", color=blurple)
            for event_key, event_awards in itertools.groupby(list(awards), lambda a: a.event_key):
                e.add_field(name=event_key, value="\n".join(map(lambda a: a.name, event_awards)), inline=False)

            pages.append(e)
        if len(pages) > 1:
            await paginate(ctx, pages, start=-1)
        elif len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            await ctx.send(f"This team hasn't won any awards in {year}" if year is not None else "This team hasn't won any awards...yet.")

    media.example_usage = """
    `{prefix}`tba media 1114` - list all the awards team 1114 Simbotics has ever gotten.
    """

    @tba.command()
    async def raw(self, ctx, team_num: int):
        """
        Get raw TBA API output for a team.
        This command is really only useful for development.
        """
        try:
            team_data = await self.session.team(team_num)
            e = discord.Embed(color=blurple)
            e.set_author(name='FIRST® Robotics Competition Team {}'.format(team_num),
                         url='https://www.thebluealliance.com/team/{}'.format(team_num),
                         icon_url='https://frcavatars.herokuapp.com/get_image?team={}'.format(team_num))
            e.add_field(name='Raw Data', value=pformat(team_data.__dict__))
            e.set_footer(text='Triggered by ' + ctx.author.display_name)
            await ctx.send(embed=e)
        except aiotba.http.AioTBAError:
            raise BadArgument('Team {} does not exist.'.format(team_num))

    raw.example_usage = """
    `{prefix}tba raw 4150` - show raw information on team 4150, FRobotics
    """
    @command()
    @bot_has_permissions(embed_links=True)
    async def weather(self, ctx, team_program: str, team_num: int):
        """Finds the current weather for a given team."""
        class TeamData:
            pass

        if team_program.lower() == "frc":
            try:
                td = await self.session.team(team_num)
            except aiotba.http.AioTBAError:
                raise BadArgument('Team {} does not exist.'.format(team_num))
        elif team_program.lower() == "ftc":
            team_data_dict = await self.bot.cogs["TOA"].get_teamdata(team_num)
            if not team_data_dict:
                raise BadArgument('Team {} does not exist.'.format(team_num))
            td = TeamData()
            td.__dict__.update(team_data_dict['seasons'][0])
        else:
            raise BadArgument('`team_program` should be one of [`frc`, `ftc`]')

        e = discord.Embed(title=f"Current weather for {team_program.upper()} Team {team_num}:")
        e.set_image(url="https://wttr.in/" + urlquote(f"{td.city}+{td.state_prov}+{td.country}_0.png"))
        e.set_footer(text="Powered by wttr.in and sometimes TBA")
        await ctx.send(embed=e)


    weather.example_usage = """
    `{prefix}timezone frc 3572` - show the current weather for FRC team 3132, Thunder Down Under
    """

    @command()
    async def timezone(self, ctx, team_program: str, team_num: int):
        """
        Get the timezone of a team based on the team number.
        """
        class TeamData:
            pass

        if team_program.lower() == "frc":
            try:
                team_data = await self.session.team(team_num)
            except aiotba.http.AioTBAError:
                raise BadArgument('Team {} does not exist.'.format(team_num))
        elif team_program.lower() == "ftc":
            team_data_dict = await self.bot.cogs["TOA"].get_teamdata(team_num)
            if not team_data_dict:
                raise BadArgument('Team {} does not exist.'.format(team_num))
            team_data = TeamData()
            team_data.__dict__.update(team_data_dict['seasons'][0])
        else:
            raise BadArgument('`team_program` should be one of [`frc`, `ftc`]')


        location = '{0.city}, {0.state_prov} {0.country}'.format(team_data)
        gmaps = googlemaps.Client(key=self.gmaps_key)
        geolocator = Nominatim(user_agent="FIRST Dozer-compatible Discord Bot")
        geolocation = geolocator.geocode(location)

        if self.gmaps_key and not self.bot.config['tz_url']:
            timezone = gmaps.timezone(location="{}, {}".format(geolocation.latitude, geolocation.longitude),
                                      language="json")
            utc_offset = float(timezone["rawOffset"]) / 3600
            if timezone["dstOffset"] == 3600:
                utc_offset += 1
            tzname = timezone["timeZoneName"]
        else:
            async with async_timeout.timeout(5) as _, self.bot.http._session.get(urljoin(
                    self.bot.config['tz_url'], str(geolocation.latitude) + "/" + str(geolocation.longitude))) as r:
                r.raise_for_status()
                data = await r.json()
                utc_offset = data["utc_offset"]
                tzname = '`' + data["tz"] + '`'

        utc_timedelta = timedelta(hours=utc_offset)
        currentUTCTime = datetime.datetime.utcnow()
        currentTime = currentUTCTime + utc_timedelta
        current_hour = currentTime.hour
        current_hour_original = current_hour
        dayTime = "AM"
        if current_hour > 12:
            current_hour -= 12
            dayTime = "PM"
        elif current_hour == 12:
            dayTime = "PM"
        elif current_hour == 0:
            current_hour = 12
            dayTime = "AM"
        current_minute = currentTime.minute
        if current_minute < 10:
            current_minute = "0{}".format(current_minute)
        current_second = currentTime.second
        if current_second < 10:
            current_second = "0{}".format(current_second)
        await ctx.send(
            "Timezone: {0} UTC{1:+g} \nCurrent Time: {2}:{3}:{4} {5} ({6}:{3}:{4})".format(
                tzname, utc_offset, current_hour, current_minute, current_second, dayTime, current_hour_original))

    timezone.example_usage = """
    `{prefix}timezone frc 3572` - show the local time of FRC team 3572, Wavelength
    """


def setup(bot):
    """Adds the TBA cog to the bot"""
    bot.add_cog(TBA(bot))
