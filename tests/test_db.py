import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buyurtmalar_daftari import db as D


def test_money():
    assert D.money(1500000) == "1 500 000"
    assert D.money(0) == "0"
    assert D.money(-2500) == "-2 500"
    assert D.parse_money("1 500 000 so'm") == 1500000


def test_telegram_normalize():
    assert D.normalize_telegram("https://t.me/abc") == "@abc"
    assert D.normalize_telegram("abc") == "@abc"
    assert D.normalize_telegram("@abc") == "@abc"
    assert D.normalize_telegram("") == ""


def test_orders_debt_and_overdue():
    db = D.DB()
    c = db.add_client("Ali", "+998", "ali")
    o1 = db.add_order("Logo", c, "logo", 1_000_000, 300_000, "2026-01-10", "jarayonda", created="2026-01-01")
    db.add_payment(o1, 200_000, "2026-01-05")
    o = db.order(o1)
    assert o["paid"] == 500_000 and o["debt"] == 500_000
    assert o["overdue"] is True or D.is_overdue(o, date(2026, 2, 1))
    assert not D.is_overdue(o, date(2026, 1, 9))
    db.update_order(o1, status="tugallangan")
    assert db.order(o1)["completed"] and not D.is_overdue(db.order(o1), date(2026, 2, 1))
    o2 = db.add_order("Banner", c, "banner", 500_000, 0, "", "bekor")
    assert db.order(o2)["debt"] == 0


def test_stats_and_monthly():
    db = D.DB()
    c = db.add_client("Vali")
    on = date(2026, 5, 20)
    a = db.add_order("A", c, "logo", 1_000_000, 400_000, "2026-05-01", "jarayonda", created="2026-05-02")
    db.add_payment(a, 100_000, "2026-05-10")
    db.add_order("B", c, "banner", 300_000, 0, "2026-06-01", "yangi", created="2026-04-01")
    db.add_order("C", c, "banner", 900_000, 900_000, "", "bekor", created="2026-05-03")
    st = db.stats(on)
    assert st.active == 2 and st.overdue == 1
    assert st.month_income == 500_000
    assert st.debt == 500_000 + 300_000
    months = dict(db.monthly_income(12, until=on))
    assert months["2026-05"] == 500_000 and len(months) == 12


def test_filters_and_delete_client():
    db = D.DB()
    c = db.add_client("Asal Media")
    db.add_order("Afisha", c, "poligrafiya", 100, 0, "2000-01-01", "yangi")
    db.add_order("Logo", None, "logo", 100, 0, "", "tugallangan")
    assert len(db.orders("afisha")) == 1
    assert len(db.orders(status="active")) == 1
    assert len(db.orders(overdue_only=True)) == 1
    assert len(db.orders("asal")) == 1
    db.delete_client(c)
    assert db.orders("afisha")[0]["client_id"] is None


def test_demo_and_file_db(tmp_path):
    db = D.DB(tmp_path / "x.db")
    D.fill_demo(db)
    assert len(db.orders()) >= 10 and len(db.clients()) == 5
    db.close()
    db2 = D.DB(tmp_path / "x.db")
    assert len(db2.orders()) >= 10
