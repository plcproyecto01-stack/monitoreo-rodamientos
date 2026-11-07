-- Ejecutar una sola vez en Supabase: SQL Editor -> New query -> pegar -> Run
create table if not exists public.registros (
  id      bigint primary key,
  datos   jsonb not null,
  creado  timestamptz default now()
);
create table if not exists public.config (
  clave       text primary key,
  valor       jsonb,
  actualizado timestamptz default now()
);
-- Seguridad: sin políticas públicas. La aplicación entra con la clave secreta (solo en el servidor).
alter table public.registros enable row level security;
alter table public.config enable row level security;
