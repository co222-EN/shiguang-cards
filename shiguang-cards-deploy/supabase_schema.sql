create table if not exists public.moment_records (
  id text primary key,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  title text not null,
  caption text not null default '',
  category text not null default 'daily',
  is_food boolean not null default false,
  calories_estimate integer,
  portion_guess text,
  confidence double precision not null default 0,
  mood_color text not null default '#f3a6a6',
  tags jsonb not null default '[]'::jsonb,
  objects jsonb not null default '[]'::jsonb,
  notes text not null default '',
  image_url text not null,
  thumbnail_url text not null,
  original_url text not null,
  ai_status text not null default 'pending',
  raw_analysis jsonb not null default '{}'::jsonb
);

create index if not exists moment_records_created_at_idx
  on public.moment_records (created_at desc);

create index if not exists moment_records_category_idx
  on public.moment_records (category);

