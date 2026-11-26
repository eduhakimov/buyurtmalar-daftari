"""Oynadagi amallar (regressiya): buyurtma qo'shish, to'lov, mijoz, eksport, hisob-faktura."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _win(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from PySide6.QtWidgets import QApplication
    from uzkit import app as appmod, i18n
    from uzkit.settings import Settings
    appmod.META = appmod.load_meta()
    appmod.SETTINGS = Settings(appmod.META["slug"])
    QApplication.instance() or QApplication([])
    i18n.set_language("uz")
    from buyurtmalar_daftari import window as W
    monkeypatch.setattr(W, "open_path", lambda p: None)
    return W, W.MainWindow()


def test_order_client_flow(tmp_path, monkeypatch):
    W, w = _win(tmp_path, monkeypatch)
    assert str(tmp_path) in w.db.path       # haqiqiy bazaga tegilmaydi
    c = w.clients
    c.new()
    c.name.setText("Test mijoz")
    c.tg.setText("t.me/test")
    c.save()
    assert w.db.clients()[0]["telegram"] == "@test"
    w.new_order(c.cid)
    e = w.orders.editor
    e.title.setText("Logotip")
    e.price.setValue(2_000_000)
    e.prepay.setValue(500_000)
    e.save()
    oid = e.oid
    assert w.db.order(oid)["client_id"] == c.cid
    w.db.add_payment(oid, 300_000)
    w.show_order(oid)
    assert w.db.order(oid)["debt"] == 1_200_000
    assert w.k_active.value.text() == "1"
    for i in range(w.orders.status.count()):
        w.orders.status.setCurrentIndex(i)
    w.orders.status.setCurrentIndex(0)
    for i in range(3):
        w.set_page(i)
    # eksportlar
    from buyurtmalar_daftari.export import export_excel, invoice_html, save_invoice_pdf
    x = export_excel(w.db, tmp_path / "a.xlsx", W.tr, W.status_name, W.type_name)
    assert x.stat().st_size > 3000
    o = w.db.order(oid)
    html = invoice_html(o, dict(w.db.client(c.cid)), w.db.payments(oid), w.designer(), W.tr, W.type_name)
    assert "Bahtiyorjon Hakimov" in html
    pdf = save_invoice_pdf(html, tmp_path / "i.pdf")
    assert pdf.read_bytes()[:4] == b"%PDF"
    w.on_theme_changed()
    w.close()
