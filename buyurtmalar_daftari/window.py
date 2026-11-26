"""Asosiy oyna: ko'rsatkichlar, buyurtmalar jadvali + tahrir paneli, mijozlar, daromad grafigi."""
import os
import sys
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QDate, QLocale, QModelIndex, QRect, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QSplitter, QStackedWidget, QStyle, QStyledItemDelegate, QTabBar,
                               QTableView, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from uzkit import AUTHOR, app as appmod
from uzkit.i18n import register, tr
from uzkit.paths import data_dir, documents_dir
from uzkit.widgets import ask, danger_button, error, open_path, primary_button, warn
from uzkit.window import BaseMainWindow

from . import db as D
from .export import export_excel, invoice_html, save_invoice_pdf
from .icons import icon
from .strings import STRINGS

register(STRINGS)

SCREENSHOT = "--screenshot" in sys.argv
NO_DATE = QDate(2000, 1, 1)
UZ_LOCALE = QLocale("uz_Latn_UZ")


def accent() -> str:
    return appmod.META.get("accent", "#c2410c")


def status_name(s: str) -> str:
    return tr("st_" + s) if s in D.STATUSES else s


def type_name(t: str) -> str:
    return tr("ty_" + t) if t in D.ORDER_TYPES else (t or "-")


def money_text(v) -> str:
    return f"{D.money(v)} {tr('currency')}"


def money_box() -> QDoubleSpinBox:
    b = QDoubleSpinBox()
    b.setLocale(UZ_LOCALE)
    b.setDecimals(0)
    b.setRange(0, 1e12)
    b.setSingleStep(50_000)
    b.setGroupSeparatorShown(True)
    b.setSuffix(" " + tr("currency"))
    b.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return b


def date_box(optional=True) -> QDateEdit:
    d = QDateEdit()
    d.setCalendarPopup(True)
    d.setDisplayFormat("dd.MM.yyyy")
    if optional:
        d.setMinimumDate(NO_DATE)
        d.setSpecialValueText("-")
    d.setDate(QDate.currentDate())
    return d


def qdate_to_iso(d: QDate) -> str:
    return "" if d == NO_DATE else d.toString("yyyy-MM-dd")


def iso_to_qdate(s: str) -> QDate:
    q = QDate.fromString(s or "", "yyyy-MM-dd")
    return q if q.isValid() else NO_DATE


def deadline_text(o) -> str:
    dl = o.get("deadline") or ""
    if not dl:
        return "-"
    try:
        dd = datetime.strptime(dl, "%Y-%m-%d").date()
    except ValueError:
        return dl
    shown = dd.strftime("%d.%m.%y")
    if o["status"] not in D.ACTIVE:
        return shown
    n = (dd - date.today()).days
    if n < 0:
        return f"{shown}  ·  {tr('overdue_days', n=-n)}"
    if n == 0:
        return f"{shown}  ·  {tr('today')}"
    if n <= 7:
        return f"{shown}  ·  {tr('days_left', n=n)}"
    return shown


def clear_scroll(widget) -> "QScrollArea":
    sc = QScrollArea()
    sc.setObjectName("ClearScroll")
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setStyleSheet("QScrollArea#ClearScroll { background: transparent; border: none; }")
    sc.viewport().setAutoFillBackground(False)
    sc.setWidget(widget)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    widget.setAutoFillBackground(False)
    return sc


def icon_button(name: str, text: str = "", tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setProperty("icon_name", name)
    b.setIcon(icon(name, size=16))
    if tip:
        b.setToolTip(tip)
    return b


# =========================================================================== ko'rsatkichlar
class Kpi(QFrame):
    def __init__(self, title: str, alert=False):
        super().__init__()
        self.setObjectName("Kpi")
        self.alert = alert
        l = QVBoxLayout(self)
        l.setContentsMargins(14, 7, 14, 8)
        l.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("KpiTitle")
        self.value = QLabel("0")
        self.value.setObjectName("KpiValue")
        l.addWidget(t)
        l.addWidget(self.value)

    def set_value(self, text: str, hot=False):
        self.value.setText(text)
        self.value.setProperty("hot", "true" if hot else "false")
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)


# =========================================================================== jadval modeli
class OrdersModel(QAbstractTableModel):
    COLS = ["#", "client", "title", "type", "price", "debt", "deadline", "status"]

    def __init__(self):
        super().__init__()
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, p=QModelIndex()):
        return 0 if p.isValid() else len(self.rows)

    def columnCount(self, p=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            c = self.COLS[s]
            return c if c == "#" else tr(c)
        if o == Qt.Horizontal and role == Qt.TextAlignmentRole and self.COLS[s] in ("price", "debt"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None
        o = self.rows[idx.row()]
        c = self.COLS[idx.column()]
        if role == Qt.UserRole:
            return o
        if role == Qt.DisplayRole:
            return {"#": str(o["id"]), "client": o["client"] or tr("no_client"), "title": o["title"],
                    "type": type_name(o["type"]), "price": D.money(o["price"]),
                    "debt": D.money(o["debt"]) if o["debt"] else "-", "deadline": deadline_text(o),
                    "status": status_name(o["status"])}[c]
        if role == Qt.ToolTipRole and c in ("title", "client", "deadline", "type"):
            return {"title": o["title"], "client": o["client"], "deadline": deadline_text(o),
                    "type": type_name(o["type"])}[c]
        if role == Qt.TextAlignmentRole and c in ("price", "debt", "#"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if c == "deadline" and o["overdue"]:
                return QColor("#dc2626")
            if o["status"] in ("tugallangan", "bekor") and c != "status":
                return QColor("#8a817b")
        if role == Qt.BackgroundRole and o["overdue"]:
            return QColor(220, 38, 38, 24)
        if role == Qt.FontRole and c == "deadline" and o["overdue"]:
            f = QFont()
            f.setBold(True)
            return f
        return None


class StatusDelegate(QStyledItemDelegate):
    """Holat ustuni: rangli "pill" nishon."""

    def paint(self, p, opt, idx):
        o = idx.data(Qt.UserRole)
        self.initStyleOption(opt, idx)
        opt.text = ""
        opt.widget.style().drawControl(QStyle.CE_ItemViewItem, opt, p, opt.widget)
        col = QColor(D.STATUS_COLORS.get(o["status"], "#666"))
        txt = status_name(o["status"])
        f = QFont(opt.font)
        f.setPointSizeF(8.5)
        f.setBold(True)
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(txt) + 22
        r = QRectF(opt.rect.left() + 6, opt.rect.center().y() - 10, w, 20)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(col)
        bg.setAlpha(36)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 10, 10)
        p.setBrush(col)
        p.drawEllipse(r.left() + 7, r.center().y() - 3, 6, 6)
        p.setFont(f)
        p.setPen(col)
        p.drawText(r.adjusted(16, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, txt)
        p.restore()


# =========================================================================== buyurtma tahriri
class OrderEditor(QFrame):
    saved = Signal(int)
    deleted = Signal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.oid = None
        self.setObjectName("SidePanel")
        self.setMinimumWidth(345)
        self.setMaximumWidth(430)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget()
        outer.addWidget(clear_scroll(body), 1)
        l = QVBoxLayout(body)
        l.setContentsMargins(16, 14, 16, 8)
        l.setSpacing(8)
        top = QHBoxLayout()
        self.head = QLabel(tr("new_order"))
        self.head.setObjectName("PanelHeading")
        top.addWidget(self.head, 1)
        self.badge = QLabel()
        self.badge.setObjectName("IdBadge")
        top.addWidget(self.badge)
        l.addLayout(top)

        form = QFormLayout()
        form.setVerticalSpacing(7)
        form.setHorizontalSpacing(10)
        self.title = QLineEdit()
        self.client = QComboBox()
        self.type = QComboBox()
        for t in D.ORDER_TYPES:
            self.type.addItem(type_name(t), t)
        self.price = money_box()
        self.prepay = money_box()
        self.deadline = date_box()
        self.status = QComboBox()
        for s in D.STATUSES:
            self.status.addItem(status_name(s), s)
        frow = QHBoxLayout()
        frow.setSpacing(4)
        self.folder = QLineEdit()
        self.folder.setPlaceholderText(tr("choose_folder"))
        self.b_folder = QToolButton()
        self.b_folder.setText("...")
        self.b_open = QToolButton()
        self.b_open.setProperty("icon_name", "folder")
        self.b_open.setToolTip(tr("open_folder_btn"))
        frow.addWidget(self.folder, 1)
        frow.addWidget(self.b_folder)
        frow.addWidget(self.b_open)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(48)
        form.addRow(tr("title"), self.title)
        form.addRow(tr("client"), self.client)
        form.addRow(tr("type"), self.type)
        form.addRow(tr("price"), self.price)
        form.addRow(tr("prepayment"), self.prepay)
        form.addRow(tr("deadline"), self.deadline)
        form.addRow(tr("status"), self.status)
        form.addRow(tr("folder"), frow)
        form.addRow(tr("notes"), self.notes)
        l.addLayout(form)

        ph = QHBoxLayout()
        pt = QLabel(tr("payments"))
        pt.setObjectName("SectionTitle")
        ph.addWidget(pt)
        ph.addStretch(1)
        self.b_pay = icon_button("plus", tr("add_payment"))
        self.b_pay_del = QToolButton()
        self.b_pay_del.setProperty("icon_name", "trash")
        self.b_pay_del.setToolTip(tr("delete_payment"))
        ph.addWidget(self.b_pay)
        ph.addWidget(self.b_pay_del)
        l.addLayout(ph)
        self.pays = QTableWidget(0, 3)
        self.pays.setHorizontalHeaderLabels([tr("date"), tr("amount"), tr("notes")])
        self.pays.verticalHeader().setVisible(False)
        self.pays.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.pays.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pays.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pays.setMinimumHeight(96)
        l.addWidget(self.pays, 1)
        self.summary = QLabel()
        self.summary.setObjectName("Summary")
        self.summary.setWordWrap(True)
        l.addWidget(self.summary)

        br = QHBoxLayout()
        self.b_del = icon_button("trash", "", tr("delete_order"))
        self.b_inv = icon_button("file", tr("invoice_pdf"))
        self.b_save = primary_button(tr("save"))
        br.addWidget(self.b_del)
        br.addWidget(self.b_inv)
        br.addStretch(1)
        br.addWidget(self.b_save)
        br.setContentsMargins(16, 6, 16, 14)
        outer.addLayout(br)

        self.b_save.clicked.connect(self.save)
        self.b_del.clicked.connect(self.delete)
        self.b_inv.clicked.connect(self.invoice)
        self.b_pay.clicked.connect(self.add_payment)
        self.b_pay_del.clicked.connect(self.delete_payment)
        self.b_folder.clicked.connect(self._pick_folder)
        self.b_open.clicked.connect(self._open_folder)
        for w in (self.price, self.prepay):
            w.valueChanged.connect(self._update_summary)
        self.new()

    def fill_clients(self):
        cur = self.client.currentData()
        self.client.blockSignals(True)
        self.client.clear()
        self.client.addItem(tr("no_client"), None)
        for c in self.win.db.clients():
            self.client.addItem(c["name"], c["id"])
        i = self.client.findData(cur)
        self.client.setCurrentIndex(max(0, i))
        self.client.blockSignals(False)

    def new(self, client_id=None):
        self.oid = None
        self.fill_clients()
        self.head.setText(tr("new_order"))
        self.badge.setText("")
        self.title.clear()
        self.client.setCurrentIndex(max(0, self.client.findData(client_id)))
        self.type.setCurrentIndex(0)
        self.price.setValue(0)
        self.prepay.setValue(0)
        self.deadline.setDate(QDate.currentDate().addDays(7))
        self.status.setCurrentIndex(0)
        self.folder.clear()
        self.notes.clear()
        self.pays.setRowCount(0)
        for b in (self.b_del, self.b_inv, self.b_pay, self.b_pay_del):
            b.setEnabled(False)
        self._update_summary()

    def load(self, oid):
        o = self.win.db.order(oid)
        if not o:
            self.new()
            return
        self.oid = oid
        self.fill_clients()
        self.head.setText(o["title"])
        self.badge.setText(f"#{o['id']}")
        self.title.setText(o["title"])
        self.client.setCurrentIndex(max(0, self.client.findData(o["client_id"])))
        ti = self.type.findData(o["type"])
        if ti < 0 and o["type"]:
            self.type.addItem(o["type"], o["type"])
            ti = self.type.count() - 1
        self.type.setCurrentIndex(max(0, ti))
        self.price.setValue(o["price"])
        self.prepay.setValue(o["prepayment"])
        self.deadline.setDate(iso_to_qdate(o["deadline"]))
        self.status.setCurrentIndex(max(0, self.status.findData(o["status"])))
        self.folder.setText(o["folder"])
        self.notes.setPlainText(o["notes"])
        pays = self.win.db.payments(oid)
        self.pays.setRowCount(len(pays))
        for i, p in enumerate(pays):
            a = QTableWidgetItem(p["date"])
            a.setData(Qt.UserRole, p["id"])
            self.pays.setItem(i, 0, a)
            m = QTableWidgetItem(D.money(p["amount"]))
            m.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.pays.setItem(i, 1, m)
            self.pays.setItem(i, 2, QTableWidgetItem(p["note"]))
        self.pays.resizeColumnToContents(0)
        self.pays.resizeColumnToContents(1)
        for b in (self.b_del, self.b_inv, self.b_pay, self.b_pay_del):
            b.setEnabled(True)
        self._update_summary()

    def _update_summary(self, *_):
        price = int(self.price.value())
        extra = sum(p["amount"] for p in self.win.db.payments(self.oid)) if self.oid else 0
        paid = int(self.prepay.value()) + extra
        debt = max(0, price - paid)
        self.summary.setText(f"{tr('paid')}: <b>{money_text(paid)}</b>&nbsp;&nbsp;&nbsp;"
                             f"{tr('debt')}: <b style='color:{'#dc2626' if debt else 'inherit'}'>"
                             f"{money_text(debt)}</b>")

    def values(self):
        return dict(title=self.title.text().strip(), client_id=self.client.currentData(),
                    type=self.type.currentData() or "", price=int(self.price.value()),
                    prepayment=int(self.prepay.value()), deadline=qdate_to_iso(self.deadline.date()),
                    status=self.status.currentData(), folder=self.folder.text().strip(),
                    notes=self.notes.toPlainText().strip())

    def save(self):
        v = self.values()
        if not v["title"]:
            warn(self, tr("need_title"))
            self.title.setFocus()
            return
        if self.oid is None:
            self.oid = self.win.db.add_order(**v)
        else:
            self.win.db.update_order(self.oid, **v)
        self.win.status(tr("saved"))
        self.saved.emit(self.oid)

    def delete(self):
        if self.oid is None:
            return
        if ask(self, tr("confirm_delete_order", t=self.title.text())):
            self.win.db.delete_order(self.oid)
            self.new()
            self.deleted.emit()

    def add_payment(self):
        if self.oid is None:
            return
        o = self.win.db.order(self.oid)
        default = max(0, o["debt"]) if o else 0
        val, ok = QInputDialog.getInt(self, tr("add_payment"), tr("pay_amount_q"), int(min(default, 2_000_000_000)),
                                      0, 2_000_000_000, 50_000)
        if ok and val > 0:
            self.win.db.add_payment(self.oid, val)
            self.saved.emit(self.oid)

    def delete_payment(self):
        r = self.pays.currentRow()
        if r < 0:
            return
        pid = self.pays.item(r, 0).data(Qt.UserRole)
        self.win.db.delete_payment(pid)
        self.saved.emit(self.oid)

    def _pick_folder(self):
        p = QFileDialog.getExistingDirectory(self, tr("choose_folder"), self.folder.text() or str(Path.home()))
        if p:
            self.folder.setText(os.path.normpath(p))

    def _open_folder(self):
        p = self.folder.text().strip()
        if p and os.path.isdir(p):
            open_path(p)
        elif p:
            warn(self, tr("folder_missing", p=p))

    def invoice(self):
        if self.oid is None:
            return
        o = self.win.db.order(self.oid)
        c = dict(self.win.db.client(o["client_id"])) if o["client_id"] else {}
        name = f"{tr('invoice')}-{o['id']}.pdf".replace(" ", "-")
        p, _ = QFileDialog.getSaveFileName(self, tr("invoice_pdf"), str(documents_dir() / name), "PDF (*.pdf)")
        if not p:
            return
        try:
            html = invoice_html(o, c, self.win.db.payments(self.oid), self.win.designer(), tr, type_name, accent())
            save_invoice_pdf(html, p)
        except Exception as ex:
            from uzkit.app import log_exception
            log_exception(ex)
            error(self, str(ex))
            return
        self.win.status(tr("exported", p=p), 8000)
        open_path(p)


# =========================================================================== buyurtmalar ko'rinishi
class OrdersView(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_orders"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", size=16), QLineEdit.LeadingPosition).setObjectName("SearchAction")
        self.status = QComboBox()
        self.status.addItem(tr("st_all"), "")
        self.status.addItem(tr("st_active"), "active")
        self.status.addItem(tr("st_overdue"), "overdue")
        for s in D.STATUSES:
            self.status.addItem(status_name(s), s)
        self.client = QComboBox()
        self.client.setMinimumWidth(170)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.status)
        bar.addWidget(self.client)
        lay.addLayout(bar)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)
        self.model = OrdersModel()
        self.table = QTableView()
        self.table.setObjectName("Ledger")
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(7, StatusDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setHighlightSections(False)
        for col, w in ((0, 40), (1, 112), (3, 84), (4, 82), (5, 78), (6, 178), (7, 110)):
            self.table.setColumnWidth(col, w)
        self.table.setColumnHidden(0, True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        ll.addWidget(self.table, 1)
        self.empty = QLabel(tr("empty_orders"))
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        ll.addWidget(self.empty, 1)
        self.count = QLabel()
        self.count.setObjectName("Muted")
        ll.addWidget(self.count)
        split.addWidget(left)
        self.editor = OrderEditor(win)
        split.addWidget(self.editor)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([790, 345])
        lay.addWidget(split, 1)

        self.search.textChanged.connect(self.refresh)
        self.status.currentIndexChanged.connect(self.refresh)
        self.client.currentIndexChanged.connect(self.refresh)
        self.table.selectionModel().currentRowChanged.connect(self._row_changed)
        self.editor.saved.connect(self._after_save)
        self.editor.deleted.connect(self.win.refresh_all)

    def fill_clients(self):
        cur = self.client.currentData()
        self.client.blockSignals(True)
        self.client.clear()
        self.client.addItem(tr("all_clients"), None)
        for c in self.win.db.clients():
            self.client.addItem(c["name"], c["id"])
        self.client.setCurrentIndex(max(0, self.client.findData(cur)))
        self.client.blockSignals(False)

    def refresh(self, *_, select=None):
        st = self.status.currentData()
        rows = self.win.db.orders(self.search.text(), "" if st == "overdue" else st, self.client.currentData(),
                                  overdue_only=(st == "overdue"))
        keep = select if select is not None else (self.editor.oid if self.editor.oid else None)
        self.model.set_rows(rows)
        self.count.setText(tr("orders_n", n=len(rows)))
        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        if keep is not None:
            for i, o in enumerate(rows):
                if o["id"] == keep:
                    self.table.selectRow(i)
                    break

    def _row_changed(self, cur, _prev):
        if cur.isValid():
            self.editor.load(self.model.rows[cur.row()]["id"])

    def _after_save(self, oid):
        self.win.refresh_all()
        self.refresh(select=oid)
        self.editor.load(oid)


# =========================================================================== mijozlar
class ClientsView(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.cid = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_clients"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", size=16), QLineEdit.LeadingPosition).setObjectName("SearchAction")
        ll.addWidget(self.search)
        self.table = QTableWidget(0, 6)
        self.table.setObjectName("Ledger")
        self.table.setHorizontalHeaderLabels([tr("name"), tr("phone"), "Telegram", tr("orders"), tr("total"),
                                              tr("debt")])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c, w in ((1, 150), (2, 120), (3, 80), (4, 120), (5, 110)):
            self.table.setColumnWidth(c, w)
        ll.addWidget(self.table, 1)
        split.addWidget(left)

        side = QFrame()
        side.setObjectName("SidePanel")
        side.setMinimumWidth(320)
        side.setMaximumWidth(420)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(8)
        hrow = QHBoxLayout()
        self.head = QLabel(tr("new_client"))
        self.head.setObjectName("PanelHeading")
        hrow.addWidget(self.head, 1)
        self.b_new = icon_button("plus", tr("new_client"))
        hrow.addWidget(self.b_new)
        sl.addLayout(hrow)
        form = QFormLayout()
        form.setVerticalSpacing(7)
        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("+998 90 123 45 67")
        trow = QHBoxLayout()
        self.tg = QLineEdit()
        self.tg.setPlaceholderText("@username")
        self.b_tg = QToolButton()
        self.b_tg.setText(tr("open_telegram"))
        trow.addWidget(self.tg, 1)
        trow.addWidget(self.b_tg)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(60)
        form.addRow(tr("name"), self.name)
        form.addRow(tr("phone"), self.phone)
        form.addRow("Telegram", trow)
        form.addRow(tr("notes"), self.notes)
        sl.addLayout(form)
        t = QLabel(tr("client_orders"))
        t.setObjectName("SectionTitle")
        sl.addWidget(t)
        self.orders = QTableWidget(0, 3)
        self.orders.setHorizontalHeaderLabels([tr("title"), tr("price"), tr("status")])
        self.orders.verticalHeader().setVisible(False)
        self.orders.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.orders.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.orders.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        sl.addWidget(self.orders, 1)
        br = QHBoxLayout()
        self.b_del = icon_button("trash", "", tr("delete_client"))
        self.b_order = icon_button("plus", tr("new_order"))
        self.b_save = primary_button(tr("save"))
        br.addWidget(self.b_del)
        br.addWidget(self.b_order)
        br.addStretch(1)
        br.addWidget(self.b_save)
        sl.addLayout(br)
        split.addWidget(side)
        split.setStretchFactor(0, 1)
        split.setSizes([760, 360])
        lay.addWidget(split)

        self.search.textChanged.connect(self.refresh)
        self.table.currentCellChanged.connect(lambda r, *_: self._select_row(r))
        self.b_save.clicked.connect(self.save)
        self.b_new.clicked.connect(self.new)
        self.b_del.clicked.connect(self.delete)
        self.b_tg.clicked.connect(self._open_tg)
        self.b_order.clicked.connect(lambda: self.win.new_order(self.cid))
        self.orders.cellDoubleClicked.connect(self._open_order)
        self.new()

    def refresh(self, *_):
        rows = self.win.db.clients(self.search.text())
        keep = self.cid
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        sel = -1
        for i, c in enumerate(rows):
            vals = [c["name"], c["phone"], c["telegram"], str(c["n_orders"]), D.money(c["total"]),
                    D.money(c["debt"]) if c["debt"] else "-"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j >= 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 5 and c["debt"]:
                    it.setForeground(QColor("#dc2626"))
                it.setData(Qt.UserRole, c["id"])
                self.table.setItem(i, j, it)
            if c["id"] == keep:
                sel = i
        self.table.blockSignals(False)
        if sel >= 0:
            self.table.selectRow(sel)

    def _select_row(self, r):
        if r < 0 or self.table.item(r, 0) is None:
            return
        self.load(self.table.item(r, 0).data(Qt.UserRole))

    def new(self):
        self.cid = None
        self.head.setText(tr("new_client"))
        for w in (self.name, self.phone, self.tg):
            w.clear()
        self.notes.clear()
        self.orders.setRowCount(0)
        self.b_del.setEnabled(False)
        self.b_order.setEnabled(False)
        self.table.clearSelection()

    def load(self, cid):
        c = self.win.db.client(cid)
        if not c:
            return self.new()
        self.cid = cid
        self.head.setText(c["name"])
        self.name.setText(c["name"])
        self.phone.setText(c["phone"])
        self.tg.setText(c["telegram"])
        self.notes.setPlainText(c["notes"])
        orders = self.win.db.orders(client_id=cid)
        self.orders.setRowCount(len(orders))
        for i, o in enumerate(orders):
            a = QTableWidgetItem(o["title"])
            a.setData(Qt.UserRole, o["id"])
            self.orders.setItem(i, 0, a)
            m = QTableWidgetItem(D.money(o["price"]))
            m.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.orders.setItem(i, 1, m)
            s = QTableWidgetItem(status_name(o["status"]))
            s.setForeground(QColor(D.STATUS_COLORS.get(o["status"], "#666")))
            self.orders.setItem(i, 2, s)
        self.b_del.setEnabled(True)
        self.b_order.setEnabled(True)

    def save(self):
        name = self.name.text().strip()
        if not name:
            warn(self, tr("need_name"))
            return
        if self.cid is None:
            self.cid = self.win.db.add_client(name, self.phone.text(), self.tg.text(), self.notes.toPlainText())
        else:
            self.win.db.update_client(self.cid, name=name, phone=self.phone.text().strip(), telegram=self.tg.text(),
                                      notes=self.notes.toPlainText())
        self.win.status(tr("saved"))
        self.win.refresh_all()
        self.load(self.cid)

    def delete(self):
        if self.cid is None:
            return
        if ask(self, tr("confirm_delete_client", n=self.name.text())):
            self.win.db.delete_client(self.cid)
            self.new()
            self.win.refresh_all()

    def _open_tg(self):
        t = D.normalize_telegram(self.tg.text())
        if t.startswith("@"):
            QDesktopServices.openUrl(QUrl(f"https://t.me/{t[1:]}"))

    def _open_order(self, r, _c):
        it = self.orders.item(r, 0)
        if it:
            self.win.show_order(it.data(Qt.UserRole))


# =========================================================================== daromad
class IncomeChart(QWidget):
    """Oylik tushum ustunli diagrammasi (QPainter)."""

    def __init__(self):
        super().__init__()
        self.data = []
        self.hover = -1
        self.setMinimumHeight(240)
        self.setMouseTracking(True)

    def set_data(self, data):
        self.data = data
        self.update()

    def _bars(self):
        n = len(self.data)
        if not n:
            return []
        left, right, top, bottom = 64, 16, 30, 34
        w = self.width() - left - right
        h = self.height() - top - bottom
        step = w / n
        bw = min(46, step * 0.62)
        mx = max(v for _, v in self.data) or 1
        out = []
        for i, (k, v) in enumerate(self.data):
            bh = h * v / mx
            x = left + i * step + (step - bw) / 2
            out.append(QRectF(x, top + h - bh, bw, bh))
        return out

    def mouseMoveEvent(self, e):
        old = self.hover
        self.hover = -1
        n = len(self.data)
        if n:
            step = (self.width() - 80) / n
            i = int((e.position().x() - 64) // step)
            if 0 <= i < n:
                self.hover = i
        if old != self.hover:
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        text = pal.color(QPalette.Text)
        muted = pal.color(QPalette.PlaceholderText)
        grid = QColor(muted)
        grid.setAlpha(50)
        left, top, bottom = 64, 30, 34
        h = self.height() - top - bottom
        mx = max([v for _, v in self.data] or [1]) or 1
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        for k in range(5):
            y = top + h - h * k / 4
            p.setPen(QPen(grid, 1, Qt.DashLine if k else Qt.SolidLine))
            p.drawLine(left, int(y), self.width() - 16, int(y))
            p.setPen(muted)
            val = mx * k / 4
            lab = f"{val / 1e6:.1f}M" if mx >= 1e6 else D.money(val)
            p.drawText(QRect(0, int(y) - 9, left - 8, 18), Qt.AlignRight | Qt.AlignVCenter, lab)
        acc = QColor(accent())
        bars = self._bars()
        n = len(bars)
        for i, (r, (k, v)) in enumerate(zip(bars, self.data)):
            c = QColor(acc)
            if i != n - 1:
                c.setAlpha(150 if i != self.hover else 230)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(0, 0, 0, 3), 3, 3)
            mname = QDate.fromString(k + "-01", "yyyy-MM-dd")
            lab = mname.toString("MM.yy")
            p.setPen(muted if i != n - 1 else text)
            p.drawText(QRectF(r.center().x() - 30, top + h + 6, 60, 18), Qt.AlignCenter, lab)
            if i == self.hover or (self.hover < 0 and i == n - 1):
                p.setPen(text)
                bf = QFont(f)
                bf.setBold(True)
                p.setFont(bf)
                p.drawText(QRectF(r.center().x() - 70, r.top() - 22, 140, 18), Qt.AlignCenter, D.money(v))
                p.setFont(f)
        p.end()


class ReportView(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        chart_box = QFrame()
        chart_box.setObjectName("SidePanel")
        cl = QVBoxLayout(chart_box)
        cl.setContentsMargins(16, 14, 16, 14)
        t = QLabel(tr("chart_title"))
        t.setObjectName("PanelHeading")
        cl.addWidget(t)
        self.chart = IncomeChart()
        cl.addWidget(self.chart, 1)
        tot = QHBoxLayout()
        self.k_year = Kpi(tr("year_total"))
        self.k_avg = Kpi(tr("avg_month"))
        tot.addWidget(self.k_year)
        tot.addWidget(self.k_avg)
        cl.addLayout(tot)
        lay.addWidget(chart_box, 3)

        side = QFrame()
        side.setObjectName("SidePanel")
        side.setMinimumWidth(300)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 14, 16, 14)
        t2 = QLabel(tr("by_type"))
        t2.setObjectName("PanelHeading")
        sl.addWidget(t2)
        self.types = QTableWidget(0, 3)
        self.types.setHorizontalHeaderLabels([tr("type"), tr("count"), tr("amount")])
        self.types.verticalHeader().setVisible(False)
        self.types.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.types.setShowGrid(False)
        self.types.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        sl.addWidget(self.types, 1)
        self.b_excel = primary_button(tr("export_excel"))
        self.b_excel.setProperty("icon_name", "sheet")
        sl.addWidget(self.b_excel)
        lay.addWidget(side, 2)
        self.b_excel.clicked.connect(win.export_excel)

    def refresh(self):
        data = self.win.db.monthly_income(12)
        self.chart.set_data(data)
        total = sum(v for _, v in data)
        self.k_year.set_value(money_text(total))
        self.k_avg.set_value(money_text(total / 12))
        rows = self.win.db.income_by_type()
        self.types.setRowCount(len(rows))
        for i, (t, n, s) in enumerate(rows):
            self.types.setItem(i, 0, QTableWidgetItem(type_name(t)))
            for j, v in ((1, str(n)), (2, D.money(s))):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.types.setItem(i, j, it)


# =========================================================================== oyna
class MainWindow(BaseMainWindow):
    def __init__(self):
        super().__init__()
        if SCREENSHOT:
            self.db = D.DB(":memory:")
            D.fill_demo(self.db)
        else:
            try:
                self.db = D.DB(data_dir(appmod.META["slug"]) / "buyurtmalar.db")
            except Exception as ex:
                error(None, tr("db_error", e=ex))
                self.db = D.DB(":memory:")

        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 12, 18, 12)
        v.setSpacing(12)
        top = QHBoxLayout()
        self._nav = QTabBar()
        self._nav.setObjectName("ViewTabs")
        self._nav.setDrawBase(False)
        self._nav.setExpanding(False)
        for k in ("view_orders", "view_clients", "view_report"):
            self._nav.addTab(tr(k))
        top.addWidget(self._nav)
        top.addStretch(1)
        self.b_excel = icon_button("sheet", tr("export_excel"))
        self.b_new = primary_button(tr("new_order"))
        self.b_new.setProperty("icon_name", "plus")
        top.addWidget(self.b_excel)
        top.addWidget(self.b_new)
        v.addLayout(top)

        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        self.k_active = Kpi(tr("kpi_active"))
        self.k_overdue = Kpi(tr("kpi_overdue"))
        self.k_month = Kpi(tr("kpi_month"))
        self.k_debt = Kpi(tr("kpi_debt"))
        for k in (self.k_active, self.k_overdue, self.k_month, self.k_debt):
            kpis.addWidget(k)
        v.addLayout(kpis)

        self.stack = QStackedWidget()
        self.orders = OrdersView(self)
        self.clients = ClientsView(self)
        self.report = ReportView(self)
        for w in (self.orders, self.clients, self.report):
            self.stack.addWidget(w)
        v.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._nav.currentChanged.connect(self._switch)
        self.b_new.clicked.connect(lambda: self.new_order(None))
        self.b_excel.clicked.connect(self.export_excel)
        self.k_overdue.mousePressEvent = lambda e: self._show_overdue()

        a = QAction(tr("export_excel"), self)
        a.triggered.connect(self.export_excel)
        self.menu_file.insertAction(self.menu_file.actions()[0], a)
        a2 = QAction(tr("designer_menu"), self)
        a2.triggered.connect(self._set_designer)
        self.menu_settings.addAction(a2)
        self.menu_file.insertSeparator(self.menu_file.actions()[1])

        self.refresh_all()
        self.apply_icons()
        if SCREENSHOT and self.orders.model.rows:
            self.orders.table.selectRow(1)
            self.clients.table.selectRow(1)

    # ------------------------------------------------------------------
    def set_page(self, i):
        if 0 <= i < self._nav.count():
            self._nav.setCurrentIndex(i)

    def _switch(self, i):
        self.stack.setCurrentIndex(i)
        if i == 2:
            self.report.refresh()

    def refresh_all(self):
        st = self.db.stats()
        self.k_active.set_value(str(st.active))
        self.k_overdue.set_value(str(st.overdue), hot=st.overdue > 0)
        self.k_month.set_value(money_text(st.month_income))
        self.k_debt.set_value(money_text(st.debt), hot=False)
        self.orders.fill_clients()
        self.orders.refresh()
        self.orders.editor.fill_clients()
        self.clients.refresh()
        if self.stack.currentIndex() == 2:
            self.report.refresh()

    def new_order(self, client_id=None):
        self.set_page(0)
        self.orders.table.clearSelection()
        self.orders.editor.new(client_id)
        self.orders.editor.title.setFocus()

    def show_order(self, oid):
        self.set_page(0)
        self.orders.status.setCurrentIndex(0)
        self.orders.client.setCurrentIndex(0)
        self.orders.search.clear()
        self.orders.refresh(select=oid)
        self.orders.editor.load(oid)

    def _show_overdue(self):
        self.set_page(0)
        self.orders.status.setCurrentIndex(self.orders.status.findData("overdue"))

    def designer(self) -> str:
        return self.settings.get("designer", AUTHOR) if self.settings else AUTHOR

    def _set_designer(self):
        name, ok = QInputDialog.getText(self, tr("designer_menu"), tr("designer_name"), text=self.designer())
        if ok and name.strip():
            self.settings.set("designer", name.strip())

    def export_excel(self):
        name = f"buyurtmalar-{date.today().isoformat()}.xlsx"
        p, _ = QFileDialog.getSaveFileName(self, tr("export_excel"), str(documents_dir() / name), "Excel (*.xlsx)")
        if not p:
            return
        try:
            export_excel(self.db, p, tr, status_name, type_name)
        except Exception as ex:
            from uzkit.app import log_exception
            log_exception(ex)
            error(self, str(ex))
            return
        self.status(tr("exported", p=p), 8000)

    def apply_icons(self):
        for b in self.findChildren(QPushButton) + self.findChildren(QToolButton):
            n = b.property("icon_name")
            if n:
                white = b.objectName() == "Primary"
                b.setIcon(icon(n, "#ffffff" if white else None, 16))
        for le in (self.orders.search, self.clients.search):
            for act in le.actions():
                if act.objectName() == "SearchAction":
                    act.setIcon(icon("search", size=16))

    def on_theme_changed(self):
        self.apply_icons()
        self.report.chart.update()

    def closeEvent(self, e):
        try:
            self.db.close()
        except Exception:
            pass
        super().closeEvent(e)
