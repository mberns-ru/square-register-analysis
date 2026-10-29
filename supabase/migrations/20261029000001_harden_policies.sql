-- =====================================================================================================
-- Follow-up to init, from Supabase's security and performance advisors:
--   1. Move the SECURITY DEFINER helper out of the API-exposed public schema (it was callable via RPC).
--   2. Split "editors write" FOR ALL policies into insert/update/delete so reads are checked by one
--      policy instead of two.
--   3. Index every foreign key.
-- =====================================================================================================

-- 1. Private helper schema (not exposed through the Data API). Policies reference functions by OID, so
--    existing policies keep working after the move.
create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;
alter function public.is_member(uuid, text[]) set schema private;


-- 2. One policy per action
do $$
declare
    t text;
    member_scope text;
begin
    foreach t in array array[
        'raw.upload_batches',
        'core.customers', 'core.deposits', 'core.staff', 'core.registers',
        'core.transactions', 'core.line_items', 'core.expenses', 'core.analyst_questions'
    ] loop
        execute format('drop policy "editors write" on %s', t);
        if t <> 'core.analyst_questions' then
            execute format('create policy "editors insert" on %s for insert to authenticated
                            with check (private.is_member(business_id, array[''owner'', ''manager'']))', t);
        end if;
        execute format('create policy "editors update" on %s for update to authenticated
                        using (private.is_member(business_id, array[''owner'', ''manager'']))
                        with check (private.is_member(business_id, array[''owner'', ''manager'']))', t);
        execute format('create policy "editors delete" on %s for delete to authenticated
                        using (private.is_member(business_id, array[''owner'', ''manager'']))', t);
    end loop;

    foreach t in array array['raw.transaction_rows', 'raw.item_rows', 'raw.rejected_rows'] loop
        member_scope := format('exists (select 1 from raw.upload_batches u where u.batch_id = %s.batch_id
                                and private.is_member(u.business_id, array[''owner'', ''manager'']))', t);
        execute format('drop policy "editors write" on %s', t);
        execute format('create policy "editors insert" on %s for insert to authenticated with check (%s)',
                       t, member_scope);
        execute format('create policy "editors update" on %s for update to authenticated using (%s) with check (%s)',
                       t, member_scope, member_scope);
        execute format('create policy "editors delete" on %s for delete to authenticated using (%s)',
                       t, member_scope);
    end loop;
end $$;

-- Owners manage the team (reads are covered by "members see their team").
drop policy "owners manage team" on public.business_members;
create policy "owners add members" on public.business_members for insert to authenticated
    with check (private.is_member(business_id, array['owner']));
create policy "owners change roles" on public.business_members for update to authenticated
    using (private.is_member(business_id, array['owner']))
    with check (private.is_member(business_id, array['owner']));
create policy "owners remove members" on public.business_members for delete to authenticated
    using (private.is_member(business_id, array['owner']));


-- 3. Foreign-key indexes
create index on public.businesses (created_by);
create index on raw.upload_batches (uploaded_by);
create index on core.transactions (batch_id);
create index on core.transactions (business_id, customer_id);
create index on core.transactions (business_id, deposit_id);
create index on core.transactions (business_id, staff_id);
create index on core.transactions (business_id, register_id);
create index on core.transactions (business_id, refunded_payment_id);
create index on core.line_items (batch_id);
create index on core.expenses (created_by);
create index on core.analyst_questions (asked_by);
