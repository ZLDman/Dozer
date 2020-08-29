-- fix the team_numbers number column
ALTER TABLE team_numbers ALTER COLUMN team_number TYPE TEXT;

-- redo the voicebinds table
ALTER TABLE voicebinds DROP COLUMN id;
ALTER TABLE voicebinds DROP CONSTRAINT voicebinds_pkey;
ALTER TABLE voicebinds ADD PRIMARY KEY (channel_id);

-- redo the roles tables
ALTER TABLE giveable_roles RENAME COLUMN id TO role_id;
ALTER TABLE giveable_roles DROP CONSTRAINT giveable_roles_guild_id_fkey;
ALTER TABLE giveable_roles ALTER COLUMN name DROP NOT NULL;
ALTER TABLE giveable_roles ALTER COLUMN norm_name DROP NOT NULL;
ALTER TABLE missing_roles ALTER COLUMN role_name DROP NOT NULL;
ALTER TABLE missing_roles DROP CONSTRAINT missing_roles_guild_id_fkey;
DROP TABLE guilds;

-- drop tables that need remaking
DROP TABLE afk_status;
DROP TABLE namegame_leaderboard;

-- moderation memeful
ALTER TABLE mutes RENAME COLUMN id TO member_id;
ALTER TABLE mutes RENAME COLUMN guild TO guild_id;
ALTER TABLE deafens RENAME COLUMN id TO member_id;
ALTER TABLE deafens RENAME COLUMN guild TO guild_id;

-- unify the guild config tables
CREATE TABLE guild_config AS SELECT guilds.id as guild_id, coalesce(modlogconfig.name, memberlogconfig.name, messagelogconfig.name) AS guild_name,
    modlogconfig.modlog_channel as mod_log_channel_id, 

    member_roles.member_role as member_role_id,

    new_members.channel_id as new_members_channel_id,
    new_members.role_id as new_members_role_id,
    new_members.message as new_members_message,

    memberlogconfig.memberlog_channel as member_log_channel_id,
    messagelogconfig.messagelog_channel as message_log_channel_id,
    guild_msg_links.role_id as links_role_id,
    welcome_channel.channel_id as welcome_channel_id

    FROM (
        SELECT id FROM modlogconfig UNION
        SELECT id FROM member_roles UNION
        SELECT guild_id AS id FROM new_members UNION
        SELECT id FROM memberlogconfig UNION 
        SELECT id FROM messagelogconfig UNION 
        SELECT guild_id AS id FROM guild_msg_links UNION
        SELECT id FROM welcome_channel
        ) AS guilds
    LEFT OUTER JOIN modlogconfig ON modlogconfig.id = guilds.id
    LEFT OUTER JOIN member_roles ON member_roles.id = guilds.id
    LEFT OUTER JOIN new_members ON new_members.guild_id = guilds.id
    LEFT OUTER JOIN memberlogconfig ON memberlogconfig.id = guilds.id
    LEFT OUTER JOIN messagelogconfig ON messagelogconfig.id = guilds.id
    LEFT OUTER JOIN guild_msg_links ON guild_msg_links.guild_id = guilds.id
    LEFT OUTER JOIN welcome_channel ON welcome_channel.id = guilds.id;

ALTER TABLE guild_config ADD PRIMARY KEY (guild_id);
