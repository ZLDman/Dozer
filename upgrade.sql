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