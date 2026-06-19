#!/usr/bin/env python3
"""
Kaffeekasse - Verwaltung einer Büro-Kaffeekasse.

Datenmodell (alles transaktionsbasiert):
- Es wird KEIN Saldo gespeichert, sondern nur Ereignisse (Transaktionen).
  Der Saldo einer Person = Summe aller Transaktionsbeträge.
- Drei Transaktionstypen:
    "consumption" : Striche aus der Liste  -> negativ (Person schuldet Geld)
    "payment"     : eingegangene Zahlung    -> positiv
    "purchase"    : Kaffeekauf für die Kasse -> positiv (Gutschrift)
- Geld wird intern IMMER in Cent (Integer) gerechnet, niemals als float.
  So entstehen keine Rundungsfehler. Erst bei der Anzeige wird in Euro
  umgerechnet.
- Der Kaffeepreis ist veränderbar. Bei einer Strichlisten-Abrechnung wird
  der zu diesem Zeitpunkt gültige Preis im Eintrag EINGEFROREN
  (Feld "unit_price_cents"). Spätere Preisänderungen wirken nur in die
  Zukunft.
- Eine Strichlisten-Abrechnung erzeugt für jede beteiligte Person einen
  Eintrag, alle mit derselben "batch_id" und demselben Datum. So lässt sich
  eine Abrechnung als Ganzes wiedererkennen und rückgängig machen.

Daten liegen in einer einzigen JSON-Datei neben dem Skript (kaffeekasse.json).
Menschenlesbar, leicht zu sichern, im Notfall mit dem Editor reparierbar.
"""

import json
import os
import shutil
import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "kaffeekasse.json")
DEFAULT_PRICE_CENTS = 40  # 0,40 € Startpreis, jederzeit in der GUI änderbar


# ---------------------------------------------------------------------------
# Hilfsfunktionen für Geldbeträge (alles in Cent)
# ---------------------------------------------------------------------------

def cents_to_str(cents: int) -> str:
    """123 -> '1,23 €', -320 -> '-3,20 €'."""
    sign = "-" if cents < 0 else ""
    a = abs(cents)
    return f"{sign}{a // 100},{a % 100:02d} €"


def euro_str_to_cents(text: str) -> int:
    """'1,23' oder '1.23' oder '5' -> Cent als int. Wirft ValueError."""
    text = text.strip().replace("€", "").replace(" ", "").replace(",", ".")
    if not text:
        raise ValueError("leer")
    value = round(float(text) * 100)
    return int(value)


def today_str() -> str:
    return dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# Datenhaltung
# ---------------------------------------------------------------------------

class Store:
    """Kapselt das Laden/Speichern und alle Operationen auf den Daten."""

    def __init__(self, path: str):
        self.path = path
        self.data = {
            "price_per_coffee_cents": DEFAULT_PRICE_CENTS,
            "next_person_id": 1,
            "next_batch_id": 1,
            "persons": {},  # id(str) -> {"name": str, "transactions": [...]}
        }
        self.load()

    # --- Laden / Speichern -------------------------------------------------

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            # Sanfte Migration fehlender Felder
            self.data.setdefault("price_per_coffee_cents", DEFAULT_PRICE_CENTS)
            self.data.setdefault("next_person_id", 1)
            self.data.setdefault("next_batch_id", 1)
            self.data.setdefault("persons", {})

    def save(self):
        # Vor dem Überschreiben eine Sicherungskopie anlegen.
        if os.path.exists(self.path):
            shutil.copy2(self.path, self.path + ".bak")
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)  # atomar

    # --- Preis -------------------------------------------------------------

    @property
    def price_cents(self) -> int:
        return self.data["price_per_coffee_cents"]

    def set_price(self, cents: int):
        self.data["price_per_coffee_cents"] = cents
        self.save()

    # --- Personen ----------------------------------------------------------

    def add_person(self, name: str) -> str:
        pid = str(self.data["next_person_id"])
        self.data["next_person_id"] += 1
        self.data["persons"][pid] = {"name": name, "transactions": []}
        self.save()
        return pid

    def persons_sorted(self):
        """Liste von (pid, person-dict), alphabetisch nach Name."""
        return sorted(self.data["persons"].items(),
                      key=lambda kv: kv[1]["name"].lower())

    def balance_cents(self, pid: str) -> int:
        return sum(t["amount_cents"]
                   for t in self.data["persons"][pid]["transactions"])

    # --- Transaktionen -----------------------------------------------------

    def add_payment(self, pid: str, amount_cents: int, note: str = ""):
        self.data["persons"][pid]["transactions"].append({
            "date": today_str(), "type": "payment",
            "amount_cents": abs(amount_cents), "note": note,
        })
        self.save()

    def add_purchase(self, pid: str, amount_cents: int, note: str = ""):
        self.data["persons"][pid]["transactions"].append({
            "date": today_str(), "type": "purchase",
            "amount_cents": abs(amount_cents), "note": note,
        })
        self.save()

    def add_consumption_batch(self, counts: dict):
        """counts: {pid: anzahl}. Legt eine Abrechnung mit gemeinsamer
        batch_id an. Nur Personen mit count > 0 bekommen einen Eintrag.
        Der aktuelle Preis wird je Eintrag eingefroren."""
        batch_id = f"{today_str()}-{self.data['next_batch_id']}"
        self.data["next_batch_id"] += 1
        price = self.price_cents
        date = today_str()
        any_entry = False
        for pid, count in counts.items():
            if count <= 0:
                continue
            any_entry = True
            self.data["persons"][pid]["transactions"].append({
                "date": date, "type": "consumption",
                "count": count, "unit_price_cents": price,
                "amount_cents": -count * price,
                "batch_id": batch_id, "note": "",
            })
        if any_entry:
            self.save()
        return batch_id if any_entry else None

    def add_payback(self, pid: str, amount_cents: int, note: str = ""):
        self.data["persons"][pid]["transactions"].append({
            "date": today_str(), "type": "payback",
            "amount_cents": -abs(amount_cents), "note": note,})
        self.save()
# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.title("Kaffeekasse")
        #self.geometry("860x520")
        self.minsize(720, 420)
        self.selected_pid = None

        self._build_top_bar()
        self._build_main_panes()
        self._build_bottom_bar()
        self.refresh_person_list()

    # --- Aufbau ------------------------------------------------------------

    def _build_top_bar(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="Kaffeekasse", font=("TkDefaultFont", 14, "bold")
                  ).pack(side="left")
        self.price_label = ttk.Label(bar, text="")
        self.price_label.pack(side="left", padx=20)
        ttk.Button(bar, text="Preis ändern", command=self.on_change_price
                   ).pack(side="left")
        self._update_price_label()

    def _build_main_panes(self):
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=4)

        # Links: Personenliste mit Saldo
        left = ttk.Frame(panes)
        cols = ("name", "saldo")
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                 selectmode="browse")
        self.tree.heading("name", text="Person")
        self.tree.heading("saldo", text="Saldo")
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("saldo", width=90, anchor="e")
        self.tree.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("negativ", foreground="#b00020")
        self.tree.tag_configure("positiv", foreground="#0a7d22")
        self.tree.bind("<<TreeviewSelect>>", self.on_select_person)
        panes.add(left, weight=1)

        # Rechts: History der gewählten Person
        right = ttk.Frame(panes)
        self.detail_label = ttk.Label(
            right, text="Keine Person ausgewählt",
            font=("TkDefaultFont", 11, "bold"))
        self.detail_label.pack(anchor="w", pady=(0, 4))

        hcols = ("date", "type", "detail", "amount")
        self.hist = ttk.Treeview(right, columns=hcols, show="headings")
        for c, txt, w, anc in (("date", "Datum", 90, "w"),
                               ("type", "Art", 90, "w"),
                               ("detail", "Details", 160, "w"),
                               ("amount", "Betrag", 90, "e")):
            self.hist.heading(c, text=txt)
            self.hist.column(c, width=w, anchor=anc)
        self.hist.pack(fill="both", expand=True, side="left")
        hsb = ttk.Scrollbar(right, orient="vertical", command=self.hist.yview)
        hsb.pack(side="right", fill="y")
        self.hist.configure(yscrollcommand=hsb.set)

        # Aktionen für die gewählte Person
        actions = ttk.Frame(right, padding=(0, 6))
        actions.pack(fill="x", side="bottom")
        ttk.Button(actions, text="+ Zahlung", command=self.on_add_payment
                   ).pack(side="top", fill="x")
        ttk.Button(actions, text="+ Kaffeekauf", command=self.on_add_purchase
                   ).pack(side="top", fill="x",  pady=2)
        ttk.Button(actions, text="+ Auszahlung", command=self.on_add_payback
                   ).pack(side="top", fill="x", pady=2)
        panes.add(right, weight=2)

    def _build_bottom_bar(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Strichliste eintragen …",
                   command=self.on_enter_tally).pack(side="left")
        ttk.Button(bar, text="Person hinzufügen",
                   command=self.on_add_person).pack(side="left", padx=8)
        self.total_label = ttk.Label(bar, text="")
        self.total_label.pack(side="right")

    # --- Anzeige aktualisieren --------------------------------------------

    def _update_price_label(self):
        self.price_label.config(
            text=f"Preis pro Kaffee: {cents_to_str(self.store.price_cents)}")

    def refresh_person_list(self):
        self.tree.delete(*self.tree.get_children())
        total = 0
        for pid, person in self.store.persons_sorted():
            bal = self.store.balance_cents(pid)
            total += bal
            tag = "negativ" if bal < 0 else ("positiv" if bal > 0 else "")
            self.tree.insert("", "end", iid=pid,
                             values=(person["name"], cents_to_str(bal)),
                             tags=(tag,))
        self.total_label.config(
            text=f"Kassenstand (Summe aller Salden): {cents_to_str(total)}")
        # Auswahl/History erhalten, wenn möglich
        if self.selected_pid and self.selected_pid in self.store.data["persons"]:
            self.tree.selection_set(self.selected_pid)
            self.refresh_history()
        else:
            self.selected_pid = None
            self.detail_label.config(text="Keine Person ausgewählt")
            self.hist.delete(*self.hist.get_children())

    def refresh_history(self):
        self.hist.delete(*self.hist.get_children())
        if not self.selected_pid:
            return
        person = self.store.data["persons"][self.selected_pid]
        self.detail_label.config(
            text=f"History: {person['name']}   "
                 f"(Saldo {cents_to_str(self.store.balance_cents(self.selected_pid))})")
        type_names = {"consumption": "Striche", "payment": "Zahlung",
                      "purchase": "Kaffeekauf", "payback": "Auszahlung"}
        # neueste zuerst
        for t in sorted(person["transactions"],
                        key=lambda x: x["date"], reverse=True):
            if t["type"] == "consumption":
                detail = (f"{t['count']}× {cents_to_str(t['unit_price_cents'])}")
            else:
                detail = t.get("note", "")
            self.hist.insert("", "end", values=(
                t["date"], type_names.get(t["type"], t["type"]),
                detail, cents_to_str(t["amount_cents"])))

    # --- Event-Handler -----------------------------------------------------

    def on_select_person(self, _event=None):
        sel = self.tree.selection()
        self.selected_pid = sel[0] if sel else None
        self.refresh_history()

    def on_change_price(self):
        cur = self.store.price_cents
        ans = simpledialog.askstring(
            "Preis ändern",
            f"Neuer Preis pro Kaffee in € (aktuell {cents_to_str(cur)}).\n"
            "Bereits eingetragene Striche behalten ihren alten Preis.",
            initialvalue=f"{cur // 100},{cur % 100:02d}", parent=self)
        if ans is None:
            return
        try:
            cents = euro_str_to_cents(ans)
            if cents <= 0:
                raise ValueError("muss > 0 sein")
        except ValueError:
            messagebox.showerror("Ungültig", "Bitte einen gültigen "
                                 "Betrag eingeben, z. B. 0,45", parent=self)
            return
        self.store.set_price(cents)
        self._update_price_label()

    def on_add_person(self):
        name = simpledialog.askstring("Person hinzufügen",
                                      "Name:", parent=self)
        if name and name.strip():
            pid = self.store.add_person(name.strip())
            self.selected_pid = pid
            self.refresh_person_list()

    def _require_selection(self) -> bool:
        if not self.selected_pid:
            messagebox.showinfo("Hinweis",
                                "Bitte links zuerst eine Person auswählen.",
                                parent=self)
            return False
        return True

    def on_add_payment(self):
        if not self._require_selection():
            return
        self._amount_dialog("Zahlung erfassen", "Eingegangener Betrag in €:",
                            self.store.add_payment)

    def on_add_purchase(self):
        if not self._require_selection():
            return
        self._amount_dialog("Kaffeekauf erfassen",
                            "Ausgegebener Betrag in € (Gutschrift):",
                            self.store.add_purchase)

    def on_add_payback(self):
        if not self._require_selection():
            return
        self._amount_dialog("Auszahlung erfassen", "Ausgezahlter Betrag in €:", self.store.add_payback)

    def _amount_dialog(self, title, prompt, store_method):
        dlg = AmountDialog(self, title, prompt)
        if dlg.result is None:
            return
        amount_cents, note = dlg.result
        store_method(self.selected_pid, amount_cents, note)
        self.refresh_person_list()

    def on_enter_tally(self):
        persons = self.store.persons_sorted()
        if not persons:
            messagebox.showinfo("Hinweis", "Es sind noch keine Personen "
                                "angelegt.", parent=self)
            return
        dlg = TallyDialog(self, persons, self.store.price_cents)
        if dlg.result is None:
            return
        batch = self.store.add_consumption_batch(dlg.result)
        if batch is None:
            messagebox.showinfo("Nichts eingetragen",
                                "Alle Felder waren 0.", parent=self)
        self.refresh_person_list()


class AmountDialog(tk.Toplevel):
    """Dialog für Betrag + optionale Notiz."""

    def __init__(self, parent, title, prompt):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=prompt).grid(row=0, column=0, columnspan=2,
                                         sticky="w")
        self.amount_var = tk.StringVar()
        e = ttk.Entry(frm, textvariable=self.amount_var, width=14)
        e.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 8))
        ttk.Label(frm, text="Notiz (optional):").grid(row=2, column=0,
                                                      columnspan=2, sticky="w")
        self.note_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.note_var, width=32).grid(
            row=3, column=0, columnspan=2, sticky="we", pady=(4, 10))
        ttk.Button(frm, text="OK", command=self._ok).grid(row=4, column=0,
                                                          sticky="e")
        ttk.Button(frm, text="Abbrechen", command=self.destroy).grid(
            row=4, column=1, sticky="w", padx=6)
        e.focus_set()
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_window()

    def _ok(self):
        try:
            cents = euro_str_to_cents(self.amount_var.get())
            if cents <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ungültig", "Bitte einen gültigen Betrag "
                                 "eingeben, z. B. 5,00", parent=self)
            return
        self.result = (cents, self.note_var.get().strip())
        self.destroy()


class TallyDialog(tk.Toplevel):
    """Sammelmaske: eine Zeile pro Person, Eingabefeld für die Anzahl.
    Tab springt zum nächsten Feld; leere Felder zählen als 0."""

    def __init__(self, parent, persons, price_cents):
        super().__init__(parent)
        self.result = None
        self.persons = persons
        self.title("Strichliste eintragen")
        self.transient(parent)
        self.geometry("380x460")
        self.entries = {}

        head = ttk.Frame(self, padding=(12, 10))
        head.pack(fill="x")
        ttk.Label(head, text=f"Anzahl Kaffees pro Person "
                  f"(Preis {cents_to_str(price_cents)}):",
                  wraplength=340).pack(anchor="w")

        # Scrollbarer Bereich für ~20+ Personen
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=12)
        canvas = tk.Canvas(container, highlightthickness=0)
        sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        first = None
        for i, (pid, person) in enumerate(persons):
            ttk.Label(inner, text=person["name"]).grid(
                row=i, column=0, sticky="w", pady=2, padx=(0, 8))
            var = tk.StringVar()
            ent = ttk.Entry(inner, textvariable=var, width=6, justify="right")
            ent.grid(row=i, column=1, sticky="e", pady=2)
            self.entries[pid] = var
            if first is None:
                first = ent
        inner.columnconfigure(0, weight=1)

        btns = ttk.Frame(self, padding=12)
        btns.pack(fill="x")
        ttk.Button(btns, text="Eintragen", command=self._ok).pack(side="right")
        ttk.Button(btns, text="Abbrechen", command=self.destroy
                   ).pack(side="right", padx=6)
        if first:
            first.focus_set()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_window()

    def _ok(self):
        counts = {}
        for pid, var in self.entries.items():
            txt = var.get().strip()
            if not txt:
                continue
            try:
                n = int(txt)
                if n < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Ungültig",
                    f"Ungültige Anzahl bei einer Person: '{txt}'. "
                    "Bitte nur ganze Zahlen ≥ 0.", parent=self)
                return
            counts[pid] = n
        self.result = counts
        self.destroy()


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def main():
    store = Store(DATA_FILE)
    app = App(store)
    app.mainloop()


if __name__ == "__main__":
    main()