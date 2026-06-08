import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from config import Config


class Database:
    def __init__(self):
        self.database_url = Config.DATABASE_URL
        self._init_db()

    def _conn(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _init_db(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGINT PRIMARY KEY,
                        username TEXT,
                        subscription_active_until TIMESTAMP,
                        subscription_status TEXT DEFAULT 'inactive',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS invoices (
                        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(id),
                        coin TEXT NOT NULL,

                        -- Legacy field kept so older deployments/tables do not break.
                        -- New code stores GBP in amount_gbp.
                        amount_usd NUMERIC(10, 2) NOT NULL,

                        amount_gbp NUMERIC(10, 2),
                        unique_adjustment_gbp NUMERIC(10, 2) DEFAULT 0,
                        fiat_currency TEXT DEFAULT 'GBP',

                        crypto_amount TEXT NOT NULL,
                        wallet_address TEXT NOT NULL,
                        description TEXT,
                        status TEXT DEFAULT 'pending',
                        tx_hash TEXT,
                        invite_sent BOOLEAN DEFAULT FALSE,
                        invite_link TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        paid_at TIMESTAMP
                    );
                """)

                # Safe migrations for already-created Railway Postgres tables.
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_active_until TIMESTAMP;")
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'inactive';")

                cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS amount_gbp NUMERIC(10, 2);")
                cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS unique_adjustment_gbp NUMERIC(10, 2) DEFAULT 0;")
                cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS fiat_currency TEXT DEFAULT 'GBP';")
                cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS tx_hash TEXT;")
                cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS invite_sent BOOLEAN DEFAULT FALSE;")
                cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS invite_link TEXT;")

                # Backfill old rows so UI can read amount_gbp.
                cur.execute("""
                    UPDATE invoices
                    SET amount_gbp = amount_usd
                    WHERE amount_gbp IS NULL;
                """)

                conn.commit()

    # ── Users ─────────────────────────────────────────────────────────────────
    def upsert_user(self, user_id: int, username: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (id, username)
                    VALUES (%s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET username = EXCLUDED.username
                """, (user_id, username))
                conn.commit()

    def activate_subscription(self, user_id: int, days: int) -> datetime | None:
        """
        Extends the user's subscription.
        If they are already active, add days to the current expiry.
        If expired/inactive, start from now.
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET subscription_active_until =
                        CASE
                            WHEN subscription_active_until IS NOT NULL
                                 AND subscription_active_until > CURRENT_TIMESTAMP
                            THEN subscription_active_until + (%s || ' days')::interval
                            ELSE CURRENT_TIMESTAMP + (%s || ' days')::interval
                        END,
                        subscription_status = 'active'
                    WHERE id = %s
                    RETURNING subscription_active_until
                """, (days, days, user_id))

                row = cur.fetchone()
                conn.commit()
                return row["subscription_active_until"] if row else None

    def get_user(self, user_id: int) -> dict | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                return cur.fetchone()

    # ── Invoice uniqueness ────────────────────────────────────────────────────
    def amount_used_today(self, coin: str, amount_gbp: float) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1
                    FROM invoices
                    WHERE coin = %s
                      AND amount_gbp = %s
                      AND fiat_currency = 'GBP'
                      AND DATE(created_at) = CURRENT_DATE
                      AND status IN ('pending', 'paid')
                    LIMIT 1
                """, (coin, amount_gbp))
                return cur.fetchone() is not None

    # ── Invoices ──────────────────────────────────────────────────────────────
    def create_invoice(
        self,
        user_id: int,
        coin: str,
        amount_gbp: float,
        unique_adjustment_gbp: float,
        crypto_amount: str,
        wallet_address: str,
        description: str,
    ) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO invoices
                    (
                        user_id,
                        coin,
                        amount_usd,
                        amount_gbp,
                        unique_adjustment_gbp,
                        fiat_currency,
                        crypto_amount,
                        wallet_address,
                        description
                    )
                    VALUES (%s, %s, %s, %s, %s, 'GBP', %s, %s, %s)
                    RETURNING id
                """, (
                    user_id,
                    coin,
                    amount_gbp,  # legacy compatibility only
                    amount_gbp,
                    unique_adjustment_gbp,
                    crypto_amount,
                    wallet_address,
                    description
                ))
                invoice_id = cur.fetchone()["id"]
                conn.commit()
                return invoice_id

    def get_invoice(self, invoice_id: int) -> dict | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM invoices WHERE id = %s", (invoice_id,))
                return cur.fetchone()

    def get_user_invoices(self, user_id: int, limit: int = 10) -> list[dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT *
                    FROM invoices
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
                return cur.fetchall()

    def get_pending_invoices(self, limit: int = 25) -> list[dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT *
                    FROM invoices
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT %s
                """, (limit,))
                return cur.fetchall()

    def tx_hash_exists(self, tx_hash: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1
                    FROM invoices
                    WHERE tx_hash = %s
                    LIMIT 1
                """, (tx_hash,))
                return cur.fetchone() is not None

    def update_invoice_status(self, invoice_id: int, status: str, tx_hash: str | None = None):
        paid_at = datetime.utcnow() if status == "paid" else None
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE invoices
                    SET status = %s,
                        paid_at = %s,
                        tx_hash = COALESCE(%s, tx_hash)
                    WHERE id = %s
                """, (status, paid_at, tx_hash, invoice_id))
                conn.commit()

    def mark_invite_sent(self, invoice_id: int, invite_link: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE invoices
                    SET invite_sent = TRUE,
                        invite_link = %s
                    WHERE id = %s
                """, (invite_link, invoice_id))
                conn.commit()

    def user_has_paid_invoice(self, user_id: int) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1
                    FROM invoices
                    WHERE user_id = %s
                      AND status = 'paid'
                    LIMIT 1
                """, (user_id,))
                return cur.fetchone() is not None
