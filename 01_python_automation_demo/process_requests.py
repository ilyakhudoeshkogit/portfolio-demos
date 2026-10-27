#!/usr/bin/env python3
"""Учебное демо: обработка заявок на закупку из CSV.

Что делает:
  1. читает заявки из CSV;
  2. проверяет каждую (обязательные поля, e-mail, дата, количество, цена, дубли);
  3. раскладывает по статусам:
       ОТКЛОНЕНА       - есть ошибки в данных;
       ДУБЛЬ           - такая же заявка уже была выше в файле;
       АВТООДОБРЕНА    - сумма не больше порога;
       НА_СОГЛАСОВАНИЕ - сумма больше порога, нужен руководитель;
  4. пишет итоговые CSV по статусам в папку out/;
  5. формирует сводку и "уведомления".

Режим DRY-RUN: никакие письма и сообщения не отправляются, программа только
печатает, что было бы отправлено. Реальной отправки в коде нет вообще.
Только стандартная библиотека Python 3.8+.
"""
import argparse
import csv
import re
import sys
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

REQUIRED = ["id", "date", "department", "requester", "email", "item", "qty", "unit_price"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STATUSES = ["АВТООДОБРЕНА", "НА_СОГЛАСОВАНИЕ", "ДУБЛЬ", "ОТКЛОНЕНА"]
FILE_NAMES = {"АВТООДОБРЕНА": "approved", "НА_СОГЛАСОВАНИЕ": "needs_approval",
              "ДУБЛЬ": "duplicates", "ОТКЛОНЕНА": "rejected"}
DEFAULT_THRESHOLD = 500.0  # BYN, порог автоодобрения (условный)


def validate(row):
    """Возвращает список текстовых ошибок для одной заявки (пустой список = всё хорошо)."""
    errors = []
    for field in REQUIRED:
        if not (row.get(field) or "").strip():
            errors.append("пустое поле «%s»" % field)
    email = (row.get("email") or "").strip()
    if email and not EMAIL_RE.match(email):
        errors.append("некорректный e-mail")
    date = (row.get("date") or "").strip()
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            errors.append("дата не в формате ГГГГ-ММ-ДД")
    qty = (row.get("qty") or "").strip()
    if qty:
        if not qty.isdigit() or int(qty) <= 0:
            errors.append("количество должно быть целым числом больше 0")
    price = (row.get("unit_price") or "").strip()
    if price:
        try:
            if float(price) <= 0:
                errors.append("цена должна быть больше 0")
        except ValueError:
            errors.append("цена не число")
    return errors


def classify(rows, threshold):
    """Раскладывает заявки по статусам. Возвращает список словарей с добавленными полями."""
    seen = set()
    result = []
    for row in rows:
        row = dict(row)
        errors = validate(row)
        key = (row.get("department", "").strip(), row.get("requester", "").strip(),
               row.get("item", "").strip(), row.get("qty", "").strip())
        row["amount"] = ""
        row["reason"] = ""
        if errors:
            row["status"] = "ОТКЛОНЕНА"
            row["reason"] = "; ".join(errors)
        else:
            amount = int(row["qty"]) * float(row["unit_price"])
            row["amount"] = "%.2f" % amount
            if key in seen:
                row["status"] = "ДУБЛЬ"
                row["reason"] = "такая же заявка (отдел, автор, позиция, количество) уже есть"
            elif amount > threshold:
                row["status"] = "НА_СОГЛАСОВАНИЕ"
                row["reason"] = "сумма %.2f больше порога %.2f" % (amount, threshold)
            else:
                row["status"] = "АВТООДОБРЕНА"
                row["reason"] = "сумма %.2f в пределах порога" % amount
            seen.add(key)
        result.append(row)
    return result


def build_summary(items, threshold):
    counts = Counter(i["status"] for i in items)
    lines = ["СВОДКА ПО ЗАЯВКАМ (порог автоодобрения: %.2f BYN)" % threshold,
             "Всего заявок: %d" % len(items)]
    for st in STATUSES:
        lines.append("  %-16s %d" % (st, counts.get(st, 0)))
    ok_sum = sum(float(i["amount"]) for i in items if i["status"] == "АВТООДОБРЕНА")
    wait_sum = sum(float(i["amount"]) for i in items if i["status"] == "НА_СОГЛАСОВАНИЕ")
    lines.append("Сумма автоодобренных: %.2f BYN" % ok_sum)
    lines.append("Сумма на согласовании: %.2f BYN" % wait_sum)
    urgent = [i for i in items if i["status"] == "НА_СОГЛАСОВАНИЕ" and i.get("priority") == "high"]
    if urgent:
        lines.append("Срочные на согласовании: " + ", ".join(i["id"] for i in urgent))
    return "\n".join(lines)


def notify(kind, to, text, dry_run=True):
    """Заглушка уведомления. В демо только печатает; настоящей отправки нет."""
    print("[DRY-RUN] %s -> %s: %s" % (kind, to, text))


def write_outputs(items, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(items[0].keys()) if items else []
    groups = OrderedDict((s, []) for s in STATUSES)
    for i in items:
        groups[i["status"]].append(i)
    written = []
    for status, rows in groups.items():
        path = out_dir / ("%s.csv" % FILE_NAMES[status])
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        written.append((path, len(rows)))
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description="Демо: обработка заявок из CSV (dry-run)")
    ap.add_argument("csv_file", help="путь к CSV с заявками")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="порог автоодобрения, по умолчанию %.0f" % DEFAULT_THRESHOLD)
    ap.add_argument("--out", default="out", help="папка для результатов (по умолчанию out)")
    args = ap.parse_args(argv)

    with open(args.csv_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    items = classify(rows, args.threshold)

    print("Режим: DRY-RUN (ничего не отправляется)\n")
    for i in items:
        print("#%s %-16s %s" % (i["id"], i["status"], i["reason"]))
    print()
    print(build_summary(items, args.threshold))
    print()
    for i in items:
        if i["status"] == "ОТКЛОНЕНА":
            addr = i.get("email") or ""
            if not EMAIL_RE.match(addr.strip()):
                addr = "manager@example.com (у автора нет корректного e-mail)"
            notify("e-mail автору", addr,
                   "Заявка #%s отклонена: %s" % (i["id"], i["reason"]))
        elif i["status"] == "НА_СОГЛАСОВАНИЕ":
            notify("сообщение руководителю", "manager@example.com",
                   "Заявка #%s (%s, %s BYN) ждёт согласования" % (i["id"], i["item"], i["amount"]))
    notify("сводка", "team@example.com", "итоги обработки приложены выше")
    print()
    for path, n in write_outputs(items, Path(args.out)):
        print("Записано: %s (%d строк)" % (path, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
