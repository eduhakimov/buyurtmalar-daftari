"""Excel eksport va hisob-faktura (PDF)."""
import html
from datetime import date
from pathlib import Path
from typing import Callable, Dict

from .db import DB, money


def export_excel(db: DB, path, t: Callable[[str], str], status_name: Callable[[str], str],
                 type_name: Callable[[str], str]) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="9A3412")
    red = PatternFill("solid", fgColor="FDE2E2")
    money_fmt = '#,##0'

    def sheet(ws, headers, rows, money_cols=(), widths=None, red_rows=()):
        ws.append(headers)
        for c in ws[1]:
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(vertical="center")
        for i, r in enumerate(rows):
            ws.append(r)
            if i in red_rows:
                for c in ws[ws.max_row]:
                    c.fill = red
        for col in money_cols:
            for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                for c in row:
                    c.number_format = money_fmt
        for i, h in enumerate(headers, 1):
            w = (widths or {}).get(i) or max(10, min(48, max(len(str(h)), *(len(str(r[i - 1])) for r in rows))
                                                       if rows else len(str(h))) + 2)
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"

    orders = db.orders()
    ws = wb.active
    ws.title = t("orders")[:31]
    sheet(ws, ["#", t("client"), t("title"), t("type"), t("price"), t("prepayment"), t("paid"), t("debt"),
               t("deadline"), t("status"), t("created"), t("folder")],
          [[o["id"], o["client"], o["title"], type_name(o["type"]), o["price"], o["prepayment"], o["paid"],
            o["debt"], o["deadline"], status_name(o["status"]), o["created"], o["folder"]] for o in orders],
          money_cols=(5, 6, 7, 8), red_rows=[i for i, o in enumerate(orders) if o["overdue"]])
    clients = db.clients()
    sheet(wb.create_sheet(t("clients")[:31]),
          [t("name"), t("phone"), "Telegram", t("orders"), t("total"), t("debt"), t("notes")],
          [[c["name"], c["phone"], c["telegram"], c["n_orders"], c["total"], c["debt"], c["notes"]]
           for c in clients], money_cols=(5, 6))
    pays = db.payments()
    sheet(wb.create_sheet(t("payments")[:31]), [t("date"), t("title"), t("amount"), t("notes")],
          [[p["date"], p["title"], p["amount"], p["note"]] for p in pays], money_cols=(3,))
    months = db.monthly_income(12)
    sheet(wb.create_sheet(t("income")[:31]), [t("month"), t("amount")], [[m, v] for m, v in months],
          money_cols=(2,))
    p = Path(path)
    wb.save(p)
    return p


def invoice_html(order: Dict, client: Dict, payments, designer: str, t: Callable[[str], str],
                 type_name: Callable[[str], str], accent: str = "#c2410c", on: date = None) -> str:
    on = on or date.today()
    e = html.escape
    rows = ""
    if order.get("prepayment"):
        rows += f"<tr><td>{e(order['created'])}</td><td>{e(t('prepayment'))}</td>" \
                f"<td class='r'>{money(order['prepayment'])}</td></tr>"
    for p in payments:
        rows += f"<tr><td>{e(p['date'])}</td><td>{e(p.get('note') or t('payment'))}</td>" \
                f"<td class='r'>{money(p['amount'])}</td></tr>"
    if not rows:
        rows = f"<tr><td colspan='3' class='m'>{e(t('no_payments'))}</td></tr>"
    contact = " · ".join(x for x in (client.get("phone", ""), client.get("telegram", "")) if x) if client else ""
    return f"""
<html><head><style>
body {{ font-family: 'Segoe UI', Arial; font-size: 10pt; color: #1f1a17; }}
h1 {{ font-size: 20pt; color: {accent}; margin: 0; }}
.m {{ color: #6b625c; }}
table {{ border-collapse: collapse; width: 100%; }}
th {{ text-align: left; background: #f3ede8; padding: 6px; border-bottom: 1px solid #d9cfc7; }}
td {{ padding: 6px; border-bottom: 1px solid #ece5df; }}
.r {{ text-align: right; }}
.big {{ font-size: 13pt; font-weight: bold; }}
</style></head><body>
<table width='100%' cellspacing='0' cellpadding='0'><tr>
<td><h1>{e(t('invoice'))} № {order['id']}</h1><span class='m'>{e(t('date'))}: {on.isoformat()}</span></td>
<td class='r'><b>{e(t('designer'))}</b><br>{e(designer)}</td>
</tr></table>
<br>
<table width='100%' cellspacing='0' cellpadding='0'>
<tr><td class='m' width='30%'>{e(t('client'))}</td><td><b>{e(order.get('client') or '-')}</b>
{('<br><span class=m>' + e(contact) + '</span>') if contact else ''}</td></tr>
<tr><td class='m'>{e(t('title'))}</td><td>{e(order['title'])}</td></tr>
<tr><td class='m'>{e(t('type'))}</td><td>{e(type_name(order['type']))}</td></tr>
<tr><td class='m'>{e(t('deadline'))}</td><td>{e(order.get('deadline') or '-')}</td></tr>
</table>
<br>
<table width='100%' cellspacing='0' cellpadding='0'>
<tr><th>{e(t('date'))}</th><th>{e(t('payments'))}</th><th class='r'>{e(t('amount'))}, {e(t('currency'))}</th></tr>
{rows}
</table>
<br>
<table width='100%' cellspacing='0' cellpadding='0'>
<tr><td class='r m'>{e(t('price'))}:</td><td class='r' width='28%'>{money(order['price'])} {e(t('currency'))}</td></tr>
<tr><td class='r m'>{e(t('paid'))}:</td><td class='r'>{money(order['paid'])} {e(t('currency'))}</td></tr>
<tr><td class='r big'>{e(t('to_pay'))}:</td><td class='r big'>{money(order['debt'])} {e(t('currency'))}</td></tr>
</table>
<br><br>
<p class='m'>{e(t('invoice_footer'))}</p>
<p>{e(t('designer'))}: ______________ {e(designer)}</p>
</body></html>"""


def save_invoice_pdf(html_text: str, path) -> Path:
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
    from PySide6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(18, 18, 18, 18),
                                      QPageLayout.Millimeter))
    doc = QTextDocument()
    doc.setHtml(html_text)
    doc.setPageSize(QSizeF(printer.pageRect(QPrinter.Point).size()))
    doc.print_(printer)
    return Path(path)
