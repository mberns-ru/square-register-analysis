-- =====================================================================================================
-- Explicit table privileges. This project doesn't auto-grant new public tables to the API roles, so
-- signed-in users couldn't read their business. Grant exactly what the app needs; row-level security
-- still decides which rows each user sees.
-- =====================================================================================================

-- Accounts: users read and edit their own profile, read their businesses and team; owners manage them.
revoke all on public.profiles, public.businesses, public.business_members from anon, authenticated;
grant select, update                  on public.profiles         to authenticated;
grant select, insert, update, delete  on public.businesses       to authenticated;
grant select, insert, update, delete  on public.business_members to authenticated;

-- TRUNCATE ignores row-level security, so no API role gets it anywhere.
revoke truncate, references, trigger on all tables in schema raw, core from authenticated;

-- service_role (server-side jobs only, never in the app) gets full access to every layer.
grant usage on schema raw, core, analytics, private to service_role;
grant all on all tables in schema public, raw, core, analytics to service_role;
grant all on all sequences in schema core to service_role;
grant execute on all functions in schema private, core to service_role;
