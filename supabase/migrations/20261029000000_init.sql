-- =====================================================================================================
-- Databased: initial schema for Supabase (PostgreSQL)
--
-- Layers (see the System Architecture slide):
--   public     accounts: profiles, businesses, memberships (read by the app through the Supabase API)
--   raw        every uploaded CSV row exactly as received, plus rejected rows
--   core       the data model from the ERD: customers, deposits, staff, registers, transactions,
--              line items, expenses
--   analytics  read-only views the dashboard queries (daily/monthly sales, item sales, P&L)
--
-- Every business-owned row carries business_id, and row-level security limits each signed-in user to the
-- businesses they belong to.
-- =====================================================================================================

create schema if not exists raw;
create schema if not exists core;
create schema if not exists analytics;


-- -----------------------------------------------------------------------------------------------------
-- Accounts
-- -----------------------------------------------------------------------------------------------------
create table public.profiles (
    id          uuid primary key references auth.users (id) on delete cascade,
    full_name   text,
    created_at  timestamptz not null default now()
);

create table public.businesses (
    business_id uuid primary key default gen_random_uuid(),
    name        text not null check (length(trim(name)) > 0),
    timezone    text not null default 'America/New_York',
    created_by  uuid references auth.users (id) on delete set null default auth.uid(),
    created_at  timestamptz not null default now()
);

create table public.business_members (
    business_id uuid not null references public.businesses (business_id) on delete cascade,
    user_id     uuid not null references auth.users (id) on delete cascade,
    role        text not null default 'owner' check (role in ('owner', 'manager', 'viewer')),
    created_at  timestamptz not null default now(),
    primary key (business_id, user_id)
);
create index on public.business_members (user_id);

-- Is the signed-in user a member of this business (optionally with one of these roles)?
-- SECURITY DEFINER so policies on business_members can call it without recursing into themselves.
create or replace function public.is_member(b uuid, roles text[] default null)
returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.business_members m
        where m.business_id = b
          and m.user_id = (select auth.uid())
          and (roles is null or m.role = any (roles))
    );
$$;

-- Whoever creates a business becomes its owner.
create or replace function public.add_creator_as_owner()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
    if new.created_by is not null then
        insert into public.business_members (business_id, user_id, role)
        values (new.business_id, new.created_by, 'owner')
        on conflict do nothing;
    end if;
    return new;
end;
$$;

create trigger businesses_add_owner
    after insert on public.businesses
    for each row execute function public.add_creator_as_owner();

-- On sign-up: create the profile, and the business if the sign-up form supplied a name.
create or replace function public.handle_new_user()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
    business_name text := nullif(trim(new.raw_user_meta_data ->> 'business_name'), '');
begin
    insert into public.profiles (id, full_name)
    values (new.id, nullif(trim(new.raw_user_meta_data ->> 'full_name'), ''));

    if business_name is not null then
        insert into public.businesses (name, created_by) values (business_name, new.id);
    end if;
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();


-- -----------------------------------------------------------------------------------------------------
-- Raw layer: uploads as received
-- -----------------------------------------------------------------------------------------------------
create table raw.upload_batches (
    batch_id        uuid primary key default gen_random_uuid(),
    business_id     uuid not null references public.businesses (business_id) on delete cascade,
    kind            text not null check (kind in ('transactions', 'items')),
    file_name       text not null,
    period_start    date,
    period_end      date,
    row_count       integer not null default 0,
    rejected_count  integer not null default 0,
    storage_path    text,                                  -- original file in Supabase Storage
    uploaded_by     uuid references auth.users (id) on delete set null default auth.uid(),
    uploaded_at     timestamptz not null default now()
);
create index on raw.upload_batches (business_id, kind, period_start);

create table raw.transaction_rows (
    batch_id    uuid not null references raw.upload_batches (batch_id) on delete cascade,
    row_number  integer not null,
    data        jsonb not null,
    primary key (batch_id, row_number)
);

create table raw.item_rows (
    batch_id    uuid not null references raw.upload_batches (batch_id) on delete cascade,
    row_number  integer not null,
    data        jsonb not null,
    primary key (batch_id, row_number)
);

-- "Rejected rows are surfaced, not silently dropped."
create table raw.rejected_rows (
    batch_id    uuid not null references raw.upload_batches (batch_id) on delete cascade,
    row_number  integer not null,
    reason      text not null,
    data        jsonb,
    primary key (batch_id, row_number)
);


-- -----------------------------------------------------------------------------------------------------
-- Core layer: the ERD
-- Square IDs are kept as text natural keys, scoped by business_id.
-- -----------------------------------------------------------------------------------------------------
create table core.customers (
    business_id   uuid not null references public.businesses (business_id) on delete cascade,
    customer_id   text not null,
    display_name  text,
    primary key (business_id, customer_id)
);

create table core.deposits (
    business_id   uuid not null references public.businesses (business_id) on delete cascade,
    deposit_id    text not null,
    deposit_date  date,
    amount        numeric(12, 2),
    primary key (business_id, deposit_id)
);

create table core.staff (
    business_id   uuid not null references public.businesses (business_id) on delete cascade,
    staff_id      text not null,             -- Square Staff ID, or the staff name when the export has none
    staff_name    text,
    primary key (business_id, staff_id)
);

create table core.registers (
    business_id   uuid not null references public.businesses (business_id) on delete cascade,
    register_id   text not null,             -- Square device name
    device_name   text,
    primary key (business_id, register_id)
);

create table core.transactions (
    business_id          uuid not null references public.businesses (business_id) on delete cascade,
    transaction_id       text not null,      -- unique per row in Square exports
    payment_id           text,               -- shared between a payment and its refunds
    event_type           text not null check (event_type in ('Payment', 'Refund')),
    status               text not null default 'Complete' check (status in ('Complete', 'Voided')),
    sold_at              timestamptz not null,
    gross_sales          numeric(12, 2) not null default 0,
    discounts            numeric(12, 2) not null default 0,
    service_charges      numeric(12, 2) not null default 0,
    net_sales            numeric(12, 2) not null default 0,
    gift_card_sales      numeric(12, 2) not null default 0,
    tax                  numeric(12, 2) not null default 0,
    tip                  numeric(12, 2) not null default 0,
    partial_refunds      numeric(12, 2) not null default 0,
    total_collected      numeric(12, 2) not null default 0,
    fees                 numeric(12, 2) not null default 0,
    net_total            numeric(12, 2) not null default 0,
    card_amount          numeric(12, 2) not null default 0,
    cash_amount          numeric(12, 2) not null default 0,
    gift_card_amount     numeric(12, 2) not null default 0,
    other_tender_amount  numeric(12, 2) not null default 0,
    source               text,
    channel              text,
    location             text,
    dining_option        text,
    refund_reason        text,
    -- Payments expose their payment_id as payment_key so refunds can reference it.
    payment_key          text generated always as (case when event_type = 'Payment' then payment_id end) stored,
    refunded_payment_id  text,               -- set on refunds whose original payment has been loaded
    customer_id          text,
    deposit_id           text,
    staff_id             text,
    register_id          text,
    batch_id             uuid references raw.upload_batches (batch_id) on delete set null,
    primary key (business_id, transaction_id),
    unique (business_id, payment_key),
    check (event_type = 'Refund' or refunded_payment_id is null),
    foreign key (business_id, refunded_payment_id) references core.transactions (business_id, payment_key)
        on delete set null (refunded_payment_id),
    foreign key (business_id, customer_id) references core.customers (business_id, customer_id)
        on delete set null (customer_id),
    foreign key (business_id, deposit_id) references core.deposits (business_id, deposit_id)
        on delete set null (deposit_id),
    foreign key (business_id, staff_id) references core.staff (business_id, staff_id)
        on delete set null (staff_id),
    foreign key (business_id, register_id) references core.registers (business_id, register_id)
        on delete set null (register_id)
);
create index on core.transactions (business_id, sold_at);
create index on core.transactions (business_id, payment_id);

create table core.line_items (
    line_item_id      bigint generated always as identity primary key,
    business_id       uuid not null,
    transaction_id    text not null,
    sold_at           timestamptz not null,
    event_type        text not null default 'Payment' check (event_type in ('Payment', 'Refund')),
    item_name         text not null,
    category          text,
    price_point       text,
    quantity          numeric(10, 3) not null default 0,
    gross_sales       numeric(12, 2) not null default 0,
    discounts         numeric(12, 2) not null default 0,
    net_sales         numeric(12, 2) not null default 0,
    tax               numeric(12, 2) not null default 0,
    unit_price        numeric(12, 2) generated always as
                          (case when quantity <> 0 then round(gross_sales / quantity, 2) end) stored,
    modifiers_applied text,
    dining_option     text,
    batch_id          uuid references raw.upload_batches (batch_id) on delete set null,
    foreign key (business_id, transaction_id) references core.transactions (business_id, transaction_id)
        on delete cascade
);
create index on core.line_items (business_id, sold_at);
create index on core.line_items (business_id, transaction_id);
create index on core.line_items (business_id, item_name);

-- Not linked to a transaction; allocated to days by date and frequency.
create table core.expenses (
    expense_id     uuid primary key default gen_random_uuid(),
    business_id    uuid not null references public.businesses (business_id) on delete cascade,
    incurred_on    date not null,
    ends_on        date,
    frequency      text not null default 'One-time'
                       check (frequency in ('One-time', 'Weekly', 'Monthly', 'Yearly')),
    category       text not null default 'Other',
    vendor         text,
    description    text,
    amount         numeric(12, 2) not null check (amount >= 0),
    status         text not null default 'Estimated'
                       check (status in ('Estimated', 'Confirmed', 'Document-backed')),
    document_path  text,                     -- receipt or invoice in Supabase Storage
    created_by     uuid references auth.users (id) on delete set null default auth.uid(),
    created_at     timestamptz not null default now(),
    check (ends_on is null or ends_on >= incurred_on),
    check (status <> 'Document-backed' or document_path is not null)
);
create index on core.expenses (business_id, incurred_on);

-- AI analyst question log ("Each question is recorded.")
create table core.analyst_questions (
    question_id  bigint generated always as identity primary key,
    business_id  uuid not null references public.businesses (business_id) on delete cascade,
    asked_by     uuid references auth.users (id) on delete set null default auth.uid(),
    asked_at     timestamptz not null default now(),
    question     text not null,
    answer       text,
    calls        jsonb not null default '[]'::jsonb,
    date_range   text,
    engine       text
);
create index on core.analyst_questions (business_id, asked_at desc);

-- Link refunds to their original payments once both are loaded (uploads can arrive in any order).
create or replace function core.link_refunds(b uuid)
returns integer
language sql set search_path = ''
as $$
    with linked as (
        update core.transactions r
        set refunded_payment_id = r.payment_id
        from core.transactions p
        where r.business_id = b and p.business_id = b
          and r.event_type = 'Refund' and r.refunded_payment_id is null
          and p.payment_key = r.payment_id
        returning 1
    )
    select count(*)::integer from linked;
$$;


-- -----------------------------------------------------------------------------------------------------
-- Analytics layer (views run with the caller's permissions, so row-level security still applies)
-- -----------------------------------------------------------------------------------------------------
create view analytics.daily_sales with (security_invoker = true) as
select
    t.business_id,
    (t.sold_at at time zone b.timezone)::date                                          as day,
    count(*) filter (where t.event_type = 'Payment')                                   as transactions,
    coalesce(sum(t.gross_sales) filter (where t.event_type = 'Payment'), 0)            as gross_sales,
    sum(t.net_sales)                                                                   as net_sales,  -- refunds netted
    coalesce(-sum(t.net_sales) filter (where t.event_type = 'Refund'), 0)              as refunds,
    sum(t.tip)                                                                         as tips,
    sum(t.tax)                                                                         as tax,
    -sum(t.fees)                                                                       as processing_fees,
    round(sum(t.net_sales) filter (where t.event_type = 'Payment')
          / nullif(count(*) filter (where t.event_type = 'Payment'), 0), 2)            as avg_ticket
from core.transactions t
join public.businesses b using (business_id)
where t.status = 'Complete'
group by t.business_id, (t.sold_at at time zone b.timezone)::date;

create view analytics.monthly_sales with (security_invoker = true) as
select business_id,
       date_trunc('month', day)::date as month,
       sum(transactions)    as transactions,
       sum(gross_sales)     as gross_sales,
       sum(net_sales)       as net_sales,
       sum(refunds)         as refunds,
       sum(tips)            as tips,
       sum(processing_fees) as processing_fees
from analytics.daily_sales
group by business_id, date_trunc('month', day);

create view analytics.item_sales_monthly with (security_invoker = true) as
select li.business_id,
       date_trunc('month', li.sold_at at time zone b.timezone)::date as month,
       li.category,
       li.item_name,
       sum(li.quantity)  as units,
       sum(li.net_sales) as net_sales
from core.line_items li
join public.businesses b using (business_id)
group by li.business_id, 2, li.category, li.item_name;

-- Spread recurring expenses evenly across days (one-time costs land on their date).
create view analytics.expense_daily with (security_invoker = true) as
select e.business_id,
       e.expense_id,
       e.category,
       d::date as day,
       case e.frequency
           when 'One-time' then e.amount
           when 'Weekly'   then e.amount / 7
           when 'Monthly'  then e.amount * 12 / 365
           when 'Yearly'   then e.amount / 365
       end as amount
from core.expenses e
cross join lateral generate_series(
    e.incurred_on,
    case when e.frequency = 'One-time' then e.incurred_on
         else coalesce(e.ends_on, greatest(e.incurred_on, current_date)) end,
    interval '1 day') as d;

create view analytics.monthly_pnl with (security_invoker = true) as
with exp as (
    select business_id, date_trunc('month', day)::date as month, sum(amount) as operating_expenses
    from analytics.expense_daily group by 1, 2
)
select coalesce(s.business_id, x.business_id)                    as business_id,
       coalesce(s.month, x.month)                                as month,
       coalesce(s.net_sales, 0)                                  as net_sales,
       coalesce(s.processing_fees, 0)                            as processing_fees,
       round(coalesce(x.operating_expenses, 0), 2)               as operating_expenses,
       round(coalesce(s.net_sales, 0) - coalesce(s.processing_fees, 0)
             - coalesce(x.operating_expenses, 0), 2)             as profit
from analytics.monthly_sales s
full join exp x on x.business_id = s.business_id and x.month = s.month;


-- -----------------------------------------------------------------------------------------------------
-- Row-level security
-- -----------------------------------------------------------------------------------------------------
alter table public.profiles          enable row level security;
alter table public.businesses        enable row level security;
alter table public.business_members  enable row level security;

create policy "read own profile"   on public.profiles for select to authenticated using (id = (select auth.uid()));
create policy "update own profile" on public.profiles for update to authenticated
    using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy "members read business"  on public.businesses for select to authenticated
    using (public.is_member(business_id) or created_by = (select auth.uid()));
create policy "anyone signed in creates a business" on public.businesses for insert to authenticated
    with check (created_by = (select auth.uid()));
create policy "owners update business" on public.businesses for update to authenticated
    using (public.is_member(business_id, array['owner']));
create policy "owners delete business" on public.businesses for delete to authenticated
    using (public.is_member(business_id, array['owner']));

create policy "members see their team" on public.business_members for select to authenticated
    using (public.is_member(business_id));
create policy "owners manage team"     on public.business_members for all to authenticated
    using (public.is_member(business_id, array['owner']))
    with check (public.is_member(business_id, array['owner']));

-- Same pattern for every business-owned table: members read, owners and managers write.
do $$
declare
    t text;
begin
    foreach t in array array[
        'raw.upload_batches',
        'core.customers', 'core.deposits', 'core.staff', 'core.registers',
        'core.transactions', 'core.line_items', 'core.expenses', 'core.analyst_questions'
    ] loop
        execute format('alter table %s enable row level security', t);
        execute format('create policy "members read" on %s for select to authenticated
                        using (public.is_member(business_id))', t);
        execute format('create policy "editors write" on %s for all to authenticated
                        using (public.is_member(business_id, array[''owner'', ''manager'']))
                        with check (public.is_member(business_id, array[''owner'', ''manager'']))', t);
    end loop;
end $$;

-- Viewers can still log their own analyst questions.
create policy "members log questions" on core.analyst_questions for insert to authenticated
    with check (public.is_member(business_id) and asked_by = (select auth.uid()));

-- Raw row tables are scoped through their batch.
do $$
declare
    t text;
begin
    foreach t in array array['raw.transaction_rows', 'raw.item_rows', 'raw.rejected_rows'] loop
        execute format('alter table %s enable row level security', t);
        execute format('create policy "members read" on %s for select to authenticated using (exists (
                            select 1 from raw.upload_batches u
                            where u.batch_id = %s.batch_id and public.is_member(u.business_id)))', t, t);
        execute format('create policy "editors write" on %s for all to authenticated using (exists (
                            select 1 from raw.upload_batches u
                            where u.batch_id = %s.batch_id
                              and public.is_member(u.business_id, array[''owner'', ''manager''])))', t, t);
    end loop;
end $$;


-- -----------------------------------------------------------------------------------------------------
-- Privileges: signed-in users only (row-level security does the per-business filtering)
-- -----------------------------------------------------------------------------------------------------
grant usage on schema raw, core, analytics to authenticated;
grant select, insert, update, delete on all tables in schema raw, core to authenticated;
grant select on all tables in schema analytics to authenticated;
grant usage on all sequences in schema core to authenticated;
-- Functions: only signed-in users may call the helpers; trigger functions are never called directly.
revoke execute on function public.is_member(uuid, text[]), core.link_refunds(uuid),
    public.handle_new_user(), public.add_creator_as_owner() from public, anon, authenticated;
grant execute on function public.is_member(uuid, text[]), core.link_refunds(uuid) to authenticated;
revoke all on all tables in schema raw, core, analytics from anon;
revoke all on public.profiles, public.businesses, public.business_members from anon;
