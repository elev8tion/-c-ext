-- Supabase migration: add profiles table

CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT UNIQUE,
    avatar_url TEXT,
    bio TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE POLICY profiles_select ON profiles
    FOR SELECT
    USING (true);

CREATE POLICY profiles_update ON profiles
    FOR UPDATE
    USING (auth.uid() = id);
