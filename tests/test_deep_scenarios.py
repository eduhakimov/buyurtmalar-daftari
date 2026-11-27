"""Chuqur ssenariylar: to'lovlar, holatlar, eksport xatolari, buzilgan baza va sozlamalar."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from PySide6.QtWidgets import QApplication
    from uzkit import app as appmod, i18n
    from uzkit.settings import Settings
    appmod.META = appmod.load_meta()
    appmod.SETTINGS = Settings(appmod.META["slug"])
    QApplication.instance() or QApplication([])
    i18n.set_language("uz")
    from buyurtmalar_daftari import window as W
    msgs = []
    monkeypatch.setattr(W, "error", lambda *a: msgs.append(("error", a[1])))
    monkeypatch.setattr(W, "warn", lambda *a: msgs.append(("warn", a[1])))
    monkeypatch.setattr(W, "open_path", lambda p: msgs.append(("open", p)))
    monkeypatch.setattr(W, "ask", lambda *a: True)
    out = tmp_path / "Ҳисоб 'fakturalar'"
    out.mkdir()
    return W, msgs, out


def test_parse_money_separators():
    from buyurtmalar_daftari import db as D
    assert D.parse_money("1.500.000") == 1_500_000
    assert D.parse_money("1,500,000") == 1_500_000
    assert D.parse_money("1.500.000,50") == 1_500_000
    assert D.parse_money("2,5") == 2
    assert D.parse_money("1 500") == 1500
    assert D.parse_money("abc") == 0


def test_payment_and_status_flow(env, monkeypatch):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QInputDialog
    W, msgs, out = env
    w = W.MainWindow()
    c = w.clients
    c.new()
    c.name.setText("Ўзбек ʻMijozʼ")
    c.tg.setText("https://t.me/abc/")
    c.save()
    assert w.db.client(c.cid)["telegram"] == "@abc"
    e = w.orders.editor
    w.new_order(c.cid)
    e.title.setText("Kech qolgan")
    e.price.setValue(1_000_000)
    e.deadline.setDate(QDate.currentDate().addDays(-3))
    e.save()
    oid = e.oid
    assert w.db.order(oid)["overdue"]
    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(lambda *a, **k: (250_000, True)))
    e.add_payment()
    assert w.db.order(oid)["debt"] == 750_000
    e.pays.selectRow(0)
    e.delete_payment()
    assert w.db.order(oid)["debt"] == 1_000_000
    e.status.setCurrentIndex(e.status.findData("tugallangan"))
    e.save()
    o = w.db.order(oid)
    assert o["completed"] and not o["overdue"]
    e.status.setCurrentIndex(e.status.findData("bekor"))
    e.save()
    assert w.db.order(oid)["debt"] == 0
    c.load(c.cid)
    c.delete()                                   # buyurtma qoladi, mijozsiz
    assert w.db.order(oid)["client_id"] is None
    w.close()


def test_export_to_readonly_reports_error(env, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    W, msgs, out = env
    w = W.MainWindow()
    oid = w.db.add_order("Logo <b>&</b>", None, "logo", 1_000_000)
    w.show_order(oid)
    for name in ("ro.pdf", "ro.xlsx"):
        ro = out / name
        ro.write_bytes(b"x")
        os.chmod(ro, 0o444)
        monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(ro), "")))
        try:
            if name.endswith(".pdf"):
                w.orders.editor.invoice()
            else:
                w.export_excel()
        finally:
            os.chmod(ro, 0o666)
        assert msgs[-1][0] == "error" and name in msgs[-1][1]
        assert ro.read_bytes() == b"x"
    good = out / "hisob ў.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(good), "")))
    w.orders.editor.invoice()
    assert good.read_bytes()[:4] == b"%PDF"
    w.close()


def test_corrupt_db_is_backed_up(env):
    from uzkit.paths import data_dir
    W, msgs, out = env
    d = data_dir("buyurtmalar-daftari")
    (d / "buyurtmalar.db").write_bytes(b"garbage" * 100)
    w = W.MainWindow()
    assert w.db.path.endswith("buyurtmalar.db")
    assert list(d.glob("buyurtmalar.broken-*.db"))
    assert msgs and msgs[-1][0] == "error"
    w.db.add_client("Yangi")
    w.close()


def test_designer_setting_not_string(env, monkeypatch):
    from uzkit import AUTHOR
    W, msgs, out = env
    w = W.MainWindow()
    w.settings.set("designer", 5)
    assert w.designer() == AUTHOR
    w.close()
