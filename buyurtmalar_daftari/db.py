"""SQLite ma'lumotlar bazasi: mijozlar, buyurtmalar, to'lovlar. Interfeyssiz, test qilinadi."""
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

STATUSES = ["yangi", "jarayonda", "tekshiruvda", "tugallangan", "bekor"]
ACTIVE = ("yangi", "jarayonda", "tekshiruvda")
STATUS_COLORS = {
    "yangi": "#2563eb",
    "jarayonda": "#d97706",
    "tekshiruvda": "#7c3aed",
    "tugallangan": "#15803d",
    "bekor": "#6b7280",
}
ORDER_TYPES = ["logo", "banner", "qadoq", "brendbuk", "poligrafiya", "smm", "veb", "illyustratsiya", "boshqa"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    telegram TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    type TEXT DEFAULT '',
    price INTEGER DEFAULT 0,
    prepayment INTEGER DEFAULT 0,
    deadline TEXT DEFAULT '',
    status TEXT DEFAULT 'yangi',
    folder TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created TEXT NOT NULL,
    completed TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    date TEXT NOT NULL,
    note TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_orders_client ON orders(client_id);
CREATE INDEX IF NOT EXISTS ix_pay_order ON payments(order_id);
"""


def money(v) -> str:
    """1500000 -> '1 500 000'"""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return "0"
    s = f"{abs(n):,}".replace(",", " ")
    return ("-" if n < 0 else "") + s


def parse_money(text: str) -> int:
    """'1 500 000', '1.500.000', '1,500,000.50', '2,5' -> butun so'm."""
    t = "".join(ch for ch in str(text) if ch.isdigit() or ch in ",.-")
    seps = [i for i, ch in enumerate(t) if ch in ",."]
    if seps:
        last = seps[-1]
        decimals = len(t) - last - 1
        if len(seps) > 1 and len({t[i] for i in seps}) == 1:
            last = -1                       # 1.500.000: hammasi minglik ajratgich
        elif len(seps) == 1 and decimals == 3:
            last = -1                       # 1.500 yoki 1,500: minglik
        t = "".join(ch for i, ch in enumerate(t) if ch not in ",." or i == last).replace(",", ".")
    if not t or t in "-.":
        return 0
    try:
        return int(round(float(t)))
    except ValueError:
        return 0


def today_iso() -> str:
    return date.today().isoformat()


@dataclass
class Stats:
    active: int = 0
    overdue: int = 0
    month_income: int = 0
    debt: int = 0


class DB:
    def __init__(self, path: str = ":memory:"):
        self.path = str(path)
        self.con = sqlite3.connect(self.path)
        try:
            self.con.row_factory = sqlite3.Row
            self.con.execute("PRAGMA foreign_keys = ON")
            self.con.executescript(SCHEMA)
            self.con.commit()
        except Exception:
            self.con.close()          # fayl band bo'lib qolmasin (zaxiraga ko'chirish uchun)
            raise

    def close(self):
        self.con.close()

    # ------------------------------------------------------------------ mijozlar
    def add_client(self, name: str, phone: str = "", telegram: str = "", notes: str = "") -> int:
        cur = self.con.execute("INSERT INTO clients(name, phone, telegram, notes, created) VALUES(?,?,?,?,?)",
                               (name.strip(), phone.strip(), normalize_telegram(telegram), notes, today_iso()))
        self.con.commit()
        return cur.lastrowid

    def update_client(self, cid: int, **kw):
        allowed = {"name", "phone", "telegram", "notes"}
        kw = {k: v for k, v in kw.items() if k in allowed}
        if "telegram" in kw:
            kw["telegram"] = normalize_telegram(kw["telegram"])
        if not kw:
            return
        sets = ", ".join(f"{k}=?" for k in kw)
        self.con.execute(f"UPDATE clients SET {sets} WHERE id=?", (*kw.values(), cid))
        self.con.commit()

    def delete_client(self, cid: int):
        self.con.execute("DELETE FROM clients WHERE id=?", (cid,))
        self.con.commit()

    def client(self, cid: int) -> Optional[sqlite3.Row]:
        return self.con.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()

    def clients(self, query: str = "") -> List[Dict]:
        q = f"%{query.strip().casefold()}%"
        rows = self.con.execute("""
            SELECT c.*,
                   (SELECT COUNT(*) FROM orders o WHERE o.client_id=c.id) AS n_orders,
                   (SELECT COALESCE(SUM(o.price),0) FROM orders o WHERE o.client_id=c.id AND o.status!='bekor') AS total
            FROM clients c ORDER BY c.name COLLATE NOCASE""").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if query.strip() and not any(q.strip("%") in str(d[k]).casefold() for k in ("name", "phone", "telegram")):
                continue
            d["debt"] = self.client_debt(d["id"])
            out.append(d)
        return out

    def client_debt(self, cid: int) -> int:
        return sum(o["debt"] for o in self.orders(client_id=cid))

    # ------------------------------------------------------------------ buyurtmalar
    def add_order(self, title: str, client_id: Optional[int] = None, type: str = "", price: int = 0,
                  prepayment: int = 0, deadline: str = "", status: str = "yangi", folder: str = "",
                  notes: str = "", created: Optional[str] = None) -> int:
        status = status if status in STATUSES else "yangi"
        created = created or today_iso()
        completed = created if status == "tugallangan" else ""
        cur = self.con.execute(
            "INSERT INTO orders(client_id,title,type,price,prepayment,deadline,status,folder,notes,created,completed)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (client_id, title.strip(), type, int(price), int(prepayment), deadline, status, folder, notes,
             created, completed))
        self.con.commit()
        return cur.lastrowid

    def update_order(self, oid: int, **kw):
        allowed = {"client_id", "title", "type", "price", "prepayment", "deadline", "status", "folder", "notes",
                   "created"}
        kw = {k: v for k, v in kw.items() if k in allowed}
        if "status" in kw:
            old = self.order(oid)
            if kw["status"] not in STATUSES:
                kw.pop("status")
            elif old and kw["status"] == "tugallangan" and old["status"] != "tugallangan":
                kw["completed"] = today_iso()
            elif kw["status"] != "tugallangan":
                kw["completed"] = ""
        if not kw:
            return
        sets = ", ".join(f"{k}=?" for k in kw)
        self.con.execute(f"UPDATE orders SET {sets} WHERE id=?", (*kw.values(), oid))
        self.con.commit()

    def delete_order(self, oid: int):
        self.con.execute("DELETE FROM orders WHERE id=?", (oid,))
        self.con.commit()

    def order(self, oid: int) -> Optional[Dict]:
        rows = self.orders(order_id=oid)
        return rows[0] if rows else None

    def orders(self, query: str = "", status: str = "", client_id: Optional[int] = None,
               order_id: Optional[int] = None, overdue_only: bool = False, on: Optional[date] = None) -> List[Dict]:
        on = on or date.today()
        sql = """SELECT o.*, COALESCE(c.name,'') AS client,
                        COALESCE((SELECT SUM(amount) FROM payments p WHERE p.order_id=o.id),0) AS paid_extra
                 FROM orders o LEFT JOIN clients c ON c.id=o.client_id WHERE 1=1"""
        args = []
        if status == "active":
            sql += " AND o.status IN ('yangi','jarayonda','tekshiruvda')"
        elif status:
            sql += " AND o.status=?"
            args.append(status)
        if client_id is not None:
            sql += " AND o.client_id=?"
            args.append(client_id)
        if order_id is not None:
            sql += " AND o.id=?"
            args.append(order_id)
        sql += " ORDER BY CASE WHEN o.status IN ('tugallangan','bekor') THEN 1 ELSE 0 END, " \
               "CASE WHEN o.deadline='' THEN '9999' ELSE o.deadline END, o.id DESC"
        out = []
        qq = query.strip().casefold()
        for r in self.con.execute(sql, args).fetchall():
            d = dict(r)
            d["paid"] = int(d["prepayment"] or 0) + int(d["paid_extra"] or 0)
            d["debt"] = 0 if d["status"] == "bekor" else max(0, int(d["price"] or 0) - d["paid"])
            d["overdue"] = is_overdue(d, on)
            if qq and not any(qq in str(d[k]).casefold() for k in ("title", "client", "type", "notes")):
                continue
            if overdue_only and not d["overdue"]:
                continue
            out.append(d)
        return out

    # ------------------------------------------------------------------ to'lovlar
    def add_payment(self, order_id: int, amount: int, on: Optional[str] = None, note: str = "") -> int:
        cur = self.con.execute("INSERT INTO payments(order_id, amount, date, note) VALUES(?,?,?,?)",
                               (order_id, int(amount), on or today_iso(), note))
        self.con.commit()
        return cur.lastrowid

    def delete_payment(self, pid: int):
        self.con.execute("DELETE FROM payments WHERE id=?", (pid,))
        self.con.commit()

    def payments(self, order_id: Optional[int] = None) -> List[Dict]:
        if order_id is None:
            rows = self.con.execute("SELECT p.*, o.title FROM payments p JOIN orders o ON o.id=p.order_id "
                                    "ORDER BY p.date DESC, p.id DESC").fetchall()
        else:
            rows = self.con.execute("SELECT * FROM payments WHERE order_id=? ORDER BY date, id",
                                    (order_id,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ hisobot
    def income_entries(self) -> List[tuple]:
        """(sana, summa) — oldindan to'lovlar (buyurtma sanasi bilan) va keyingi to'lovlar."""
        out = [(r["created"], r["prepayment"]) for r in
               self.con.execute("SELECT created, prepayment FROM orders WHERE prepayment>0 AND status!='bekor'")]
        out += [(r["date"], r["amount"]) for r in self.con.execute(
            "SELECT p.date, p.amount FROM payments p JOIN orders o ON o.id=p.order_id WHERE o.status!='bekor'")]
        return out

    def monthly_income(self, months: int = 12, until: Optional[date] = None) -> List[tuple]:
        """Oxirgi N oy: [('2026-01', summa), ...] eski oydan yangisiga."""
        until = until or date.today()
        keys = []
        y, m = until.year, until.month
        for _ in range(months):
            keys.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        keys.reverse()
        sums = {k: 0 for k in keys}
        for d, amt in self.income_entries():
            k = (d or "")[:7]
            if k in sums:
                sums[k] += int(amt or 0)
        return [(k, sums[k]) for k in keys]

    def income_by_type(self) -> List[tuple]:
        rows = self.con.execute("""SELECT type, COUNT(*) n, COALESCE(SUM(price),0) s FROM orders
                                   WHERE status!='bekor' GROUP BY type ORDER BY s DESC""").fetchall()
        return [(r["type"] or "-", r["n"], r["s"]) for r in rows]

    def stats(self, on: Optional[date] = None) -> Stats:
        on = on or date.today()
        orders = self.orders(on=on)
        st = Stats()
        st.active = sum(1 for o in orders if o["status"] in ACTIVE)
        st.overdue = sum(1 for o in orders if o["overdue"])
        st.debt = sum(o["debt"] for o in orders if o["status"] != "bekor")
        key = on.strftime("%Y-%m")
        st.month_income = sum(int(a or 0) for d, a in self.income_entries() if (d or "")[:7] == key)
        return st


def is_overdue(order: Dict, on: Optional[date] = None) -> bool:
    on = on or date.today()
    dl = order.get("deadline") or ""
    if not dl or order.get("status") not in ACTIVE:
        return False
    try:
        return datetime.strptime(dl, "%Y-%m-%d").date() < on
    except ValueError:
        return False


def normalize_telegram(t: str) -> str:
    t = (t or "").strip()
    for pre in ("https://t.me/", "http://t.me/", "t.me/"):
        if t.lower().startswith(pre):
            t = t[len(pre):]
    t = t.strip("/ ")
    if t and not t.startswith("@") and not t.startswith("+"):
        t = "@" + t
    return t


def fill_demo(db: DB, today: Optional[date] = None):
    """Skrinshot / namoyish uchun namunaviy ma'lumotlar (faqat xotiradagi bazaga)."""
    t = today or date.today()

    def d(days):
        return (t + timedelta(days=days)).isoformat()
    c1 = db.add_client("Asal Media", "+998 90 123 45 67", "asalmedia", "Reklama agentligi")
    c2 = db.add_client("Bahor Tea", "+998 93 555 12 34", "bahortea_uz", "Choy brendi, qadoqlar")
    c3 = db.add_client("Navro'z Ijod markazi", "+998 71 200 30 40", "", "")
    c4 = db.add_client("Dilshod Karimov", "+998 97 765 43 21", "dilshod_k", "Shaxsiy buyurtmachi")
    c5 = db.add_client("Toshkent Fit", "+998 99 888 77 66", "toshkentfit", "Sport zal")
    rows = [
        (c1, "Yangi yil aksiyasi bannerlari", "banner", 1_800_000, 900_000, d(3), "jarayonda", d(-6)),
        (c2, "Choy qadog'i: 3 ta ta'm", "qadoq", 6_500_000, 3_000_000, d(9), "jarayonda", d(-15)),
        (c3, "Festival afishasi", "poligrafiya", 1_200_000, 600_000, d(-2), "tekshiruvda", d(-20)),
        (c4, "Shaxsiy logotip", "logo", 2_000_000, 1_000_000, d(-5), "jarayonda", d(-25)),
        (c5, "Instagram postlari (12 ta)", "smm", 2_400_000, 0, d(12), "yangi", d(-1)),
        (c1, "Brendbuk", "brendbuk", 9_000_000, 4_500_000, d(-40), "tugallangan", d(-70)),
        (c2, "Logotip qayta dizayni", "logo", 3_500_000, 1_500_000, d(-80), "tugallangan", d(-110)),
        (c5, "Veb-sayt maketi", "veb", 5_000_000, 2_000_000, d(20), "yangi", d(-3)),
        (c3, "Bayram tabriknomasi", "poligrafiya", 700_000, 0, d(-30), "bekor", d(-45)),
        (c4, "Kitob muqovasi illyustratsiyasi", "illyustratsiya", 2_800_000, 1_400_000, d(-120), "tugallangan",
         d(-150)),
    ]
    ids = []
    for cid, title, typ, price, pre, dl, stt, created in rows:
        ids.append(db.add_order(title, cid, typ, price, pre, dl, stt, created=created))
    db.add_payment(ids[5], 4_500_000, d(-38), "Yakuniy to'lov")
    db.add_payment(ids[6], 2_000_000, d(-78), "Yakuniy to'lov")
    db.add_payment(ids[9], 1_400_000, d(-118), "Yakuniy to'lov")
    db.add_payment(ids[1], 1_000_000, d(-4), "Oraliq to'lov")
    db.add_payment(ids[0], 400_000, d(-1), "")
    # o'tgan oylar tarixi (grafik uchun)
    hist = [("Menyu dizayni", "poligrafiya", 1_500_000), ("Qadoq yorlig'i", "qadoq", 3_200_000),
            ("Logotip", "logo", 2_500_000), ("Banner to'plami", "banner", 1_900_000),
            ("Katalog", "poligrafiya", 4_100_000), ("SMM paket", "smm", 2_200_000),
            ("Ko'rgazma stendi", "banner", 3_600_000), ("Ikonkalar to'plami", "illyustratsiya", 1_700_000)]
    for i, (title, typ, price) in enumerate(hist):
        back = 35 + i * 38
        cid = (c1, c2, c3, c4, c5)[i % 5]
        oid = db.add_order(title, cid, typ, price, price // 2, d(-back + 10), "tugallangan", created=d(-back))
        db.add_payment(oid, price - price // 2, d(-back + 12), "Yakuniy to'lov")
