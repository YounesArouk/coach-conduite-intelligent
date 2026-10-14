#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coach_gui_can.py  --  Interface CAN avec EVALUATION DE SEGMENT
===============================================================
L'interface affiche les trames CAN en continu ET accumule chaque
trame dans un tampon. Au clic sur "EVALUER", le module IA calcule
UN score global a partir de toutes les trames accumulees depuis le
dernier clic, puis le tampon est vide. L'accumulation reprend
aussitot. Un bouton "RESET" vide le tampon manuellement.

PRINCIPE DE FONCTIONNEMENT :
  1. Le thread CAN recoit les trames en continu.
  2. Chaque trame est affichee (tableau de bord) ET ajoutee au tampon.
  3. Clic "EVALUER" -> l'IA evalue chaque trame du tampon, fait la
     moyenne des scores -> 1 seul score global. Le tampon se vide.
  4. L'affichage des trames continue ; un nouveau clic evalue le
     nouveau segment (depuis le clic precedent).
  5. "RESET" vide le tampon et efface le resultat sans evaluer.

PREREQUIS :
    sudo apt install can-utils python3-tk
    pip3 install python-can scikit-learn pandas joblib

ACTIVER LE BUS :
    sudo ip link set can0 down
    sudo ip link set can0 type can bitrate 500000 restart-ms 100
    sudo ip link set can0 up

LANCEMENT :
    python3 coach_gui_can.py
"""
import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import can
import joblib
import pandas as pd

# =============================================================================
# 1. Chargement du modele IA  (chemin robuste)
# =============================================================================
DOSSIER_SCRIPT = os.path.dirname(os.path.abspath(__file__))
PKL = os.path.join(DOSSIER_SCRIPT, "modele_coach_conduite.pkl")

if not os.path.exists(PKL):
    print("ERREUR : modele introuvable.\n   Attendu ici : " + PKL)
    sys.exit(1)

_paquet = joblib.load(PKL)
if isinstance(_paquet, dict):
    MODEL    = _paquet["model"]
    FEATURES = _paquet["features"]
else:
    MODEL    = _paquet
    FEATURES = ["vitesse", "acceleration", "freinage", "regime_moteur",
                "niveau_carburant", "temp_moteur", "angle_volant",
                "conso_instant"]

# =============================================================================
# 2. Constantes
# =============================================================================
CAN_ID  = 0x100
CANAL   = "can0"          # "vcan0" pour un test sans materiel
BITRATE = 500000

TYPES = {
    0: ("ECO",      "#22c55e"),
    1: ("NORMAL",   "#eab308"),
    2: ("AGRESSIF", "#ef4444"),
}

# (cle, libelle, unite, mini, maxi)
CHAMPS = [
    ("vitesse",          "Vitesse",          "km/h",      0,  180),
    ("acceleration",     "Acceleration",     "m/s2",     -8,    5),
    ("freinage",         "Freinage",         "%",         0,  100),
    ("regime_moteur",    "Regime moteur",    "tr/min",  700, 6500),
    ("niveau_carburant", "Niveau carburant", "%",         0,  100),
    ("temp_moteur",      "Temp. moteur",     "degC",     70,  115),
    ("angle_volant",     "Angle volant",     "deg",    -180,  180),
    ("conso_instant",    "Conso instant.",   "L/100km",   0,   25),
]

file_trames   = queue.Queue()
arret_demande = threading.Event()


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def score_vers_type(s):
    return 0 if s >= 70 else (1 if s >= 45 else 2)


# =============================================================================
# 3. Decodage + IA
# =============================================================================
def decoder_trame(data):
    """Convertit les 8 octets CAN en dictionnaire de parametres reels."""
    donnees = {}
    for i, (cle, lib, unite, mini, maxi) in enumerate(CHAMPS):
        valeur = mini + (data[i] / 255.0) * (maxi - mini)
        if cle in ("regime_moteur", "angle_volant"):
            donnees[cle] = int(round(valeur))
        else:
            donnees[cle] = round(valeur, 2)
    return donnees


def score_d_une_trame(donnees):
    """Renvoie le score IA (0-100) pour une trame."""
    X = pd.DataFrame([donnees])[FEATURES]
    return clamp(float(MODEL.predict(X)[0]), 0, 100)


def generer_conseil(moyennes, type_code):
    """Conseil base sur les valeurs MOYENNES du segment."""
    if type_code == 0:
        return "Conduite economique et sure sur ce segment. Continuez ainsi !"
    problemes = []
    if moyennes["freinage"] > 50:
        problemes.append((moyennes["freinage"],
            "Anticipez davantage pour freiner en douceur."))
    if abs(moyennes["acceleration"]) > 2.5:
        problemes.append((abs(moyennes["acceleration"]) * 20,
            "Accelerez plus progressivement, evitez les a-coups."))
    if moyennes["regime_moteur"] > 3800:
        problemes.append((moyennes["regime_moteur"] / 60,
            "Passez les rapports plus tot pour baisser le regime."))
    if moyennes["vitesse"] > 105:
        problemes.append((moyennes["vitesse"],
            "Reduisez votre vitesse moyenne."))
    if moyennes["conso_instant"] > 15:
        problemes.append((moyennes["conso_instant"] * 6,
            "Consommation elevee : conduite plus souple."))
    if not problemes:
        return "Conduite correcte sur ce segment, ajustements possibles."
    problemes.sort(reverse=True)
    base = problemes[0][1]
    return ("Conduite agressive. " + base) if type_code == 2 else base


def evaluer_segment(tampon):
    """Evalue une LISTE de trames accumulees.

    Methode : score IA de chaque trame, puis moyenne des scores
    -> un seul score global pour le segment.
    Renvoie (score_global, type_code, conseil, moyennes, nb_trames).
    """
    nb = len(tampon)
    scores = [score_d_une_trame(t) for t in tampon]
    score_global = sum(scores) / nb

    # Moyennes des parametres (pour le conseil)
    moyennes = {}
    for cle, lib, unite, mini, maxi in CHAMPS:
        moyennes[cle] = sum(t[cle] for t in tampon) / nb

    type_code = score_vers_type(score_global)
    conseil   = generer_conseil(moyennes, type_code)
    return score_global, type_code, conseil, moyennes, nb


# =============================================================================
# 4. Thread d'ecoute du bus CAN
# =============================================================================
def thread_can():
    """Ecoute le CAN en continu et pousse chaque trame dans la file.

    Version durcie : si l'interface est DOWN ou tombe en cours de
    route ('Network is down'), le thread ne plante pas. Il signale
    l'erreur a l'interface et reessaie toutes les 3 secondes.
    """
    import time

    while not arret_demande.is_set():
        bus = None
        try:
            bus = can.interface.Bus(channel=CANAL, interface="socketcan")
            file_trames.put(("info",
                             "Bus '" + CANAL + "' connecte - reception..."))

            # Boucle de reception
            while not arret_demande.is_set():
                msg = bus.recv(timeout=1.0)
                if msg is None:
                    continue
                if msg.arbitration_id != CAN_ID or len(msg.data) < 8:
                    continue
                file_trames.put(("trame", decoder_trame(msg.data)))

        except Exception as e:
            # Network is down, bus inaccessible, etc.
            file_trames.put(("erreur",
                "Bus CAN indisponible : " + str(e)
                + "  -> activez can0 (voir README). Nouvel essai dans 3 s."))
        finally:
            if bus is not None:
                try:
                    bus.shutdown()
                except Exception:
                    pass

        # Avant de reessayer, attendre 3 s (sans bloquer l'arret)
        for _ in range(30):
            if arret_demande.is_set():
                break
            time.sleep(0.1)


# =============================================================================
# 5. Interface graphique
# =============================================================================
class CoachApp:
    def __init__(self, root):
        self.root = root
        self.tampon = []          # trames accumulees depuis le dernier EVALUER
        self.total_recu = 0       # compteur total de trames recues

        root.title("Coach de Conduite - Evaluation de segment")
        root.configure(bg="#1e293b")
        root.geometry("580x780")

        tk.Label(root, text="COACH DE CONDUITE",
                 font=("Helvetica", 20, "bold"),
                 fg="white", bg="#1e293b").pack(pady=(14, 2))
        self.lbl_etat = tk.Label(root, text="Connexion au bus CAN...",
                                 font=("Helvetica", 9),
                                 fg="#94a3b8", bg="#1e293b")
        self.lbl_etat.pack(pady=(0, 8))

        # --- Tableau de bord (valeurs instantanees, continu) ---
        tk.Label(root, text="Valeurs en direct",
                 font=("Helvetica", 10, "bold"),
                 fg="#cbd5e1", bg="#1e293b").pack()
        dash = tk.Frame(root, bg="#0f172a")
        dash.pack(padx=20, pady=6, fill="x")
        self.labels_param = {}
        for i, (cle, lib, unite, mini, maxi) in enumerate(CHAMPS):
            r, c = divmod(i, 2)
            cell = tk.Frame(dash, bg="#0f172a")
            cell.grid(row=r, column=c, sticky="w", padx=16, pady=5)
            tk.Label(cell, text=lib, font=("Helvetica", 9),
                     fg="#94a3b8", bg="#0f172a").pack(anchor="w")
            lbl = tk.Label(cell, text="-- " + unite,
                           font=("Helvetica", 13, "bold"),
                           fg="white", bg="#0f172a")
            lbl.pack(anchor="w")
            self.labels_param[cle] = (lbl, unite)

        # --- Compteur d'accumulation ---
        self.lbl_accum = tk.Label(root,
                                  text="Trames accumulees : 0",
                                  font=("Helvetica", 10, "bold"),
                                  fg="#38bdf8", bg="#1e293b")
        self.lbl_accum.pack(pady=(8, 4))

        # --- Boutons ---
        cadre_btn = tk.Frame(root, bg="#1e293b")
        cadre_btn.pack(pady=8)
        self.btn_eval = tk.Button(cadre_btn, text="EVALUER LA CONDUITE",
                                  font=("Helvetica", 12, "bold"),
                                  bg="#3b82f6", fg="white", relief="flat",
                                  padx=18, pady=10, command=self.evaluer)
        self.btn_eval.pack(side="left", padx=6)
        tk.Button(cadre_btn, text="RESET",
                  font=("Helvetica", 12, "bold"),
                  bg="#64748b", fg="white", relief="flat",
                  padx=18, pady=10, command=self.reset
                  ).pack(side="left", padx=6)

        # --- Zone resultat ---
        self.cadre = tk.Frame(root, bg="#0f172a")
        self.cadre.pack(padx=20, pady=8, fill="both", expand=True)
        self.lbl_score = tk.Label(self.cadre, text="Score : --",
                                  font=("Helvetica", 24, "bold"),
                                  fg="white", bg="#0f172a")
        self.lbl_score.pack(pady=(16, 4))
        self.lbl_type = tk.Label(self.cadre, text="Type : --",
                                 font=("Helvetica", 16, "bold"),
                                 fg="#94a3b8", bg="#0f172a")
        self.lbl_type.pack(pady=4)
        self.lbl_conseil = tk.Label(self.cadre, text="",
                                    font=("Helvetica", 11), fg="#cbd5e1",
                                    bg="#0f172a", wraplength=480,
                                    justify="center")
        self.lbl_conseil.pack(pady=(8, 6), padx=16)
        self.lbl_detail = tk.Label(self.cadre, text="",
                                   font=("Helvetica", 9, "italic"),
                                   fg="#64748b", bg="#0f172a")
        self.lbl_detail.pack(pady=(2, 14))

        self.root.after(100, self.scruter_file)

    # -------------------------------------------------------------------------
    def scruter_file(self):
        """Vide la file CAN : affiche chaque trame ET l'accumule."""
        try:
            while True:
                type_msg, contenu = file_trames.get_nowait()
                if type_msg == "info":
                    self.lbl_etat.config(text=contenu, fg="#22c55e")
                elif type_msg == "erreur":
                    self.lbl_etat.config(text=contenu, fg="#ef4444")
                elif type_msg == "trame":
                    self.nouvelle_trame(contenu)
        except queue.Empty:
            pass
        self.root.after(100, self.scruter_file)

    # -------------------------------------------------------------------------
    def nouvelle_trame(self, donnees):
        """Affiche une trame (continu) et l'ajoute au tampon."""
        # Affichage instantane
        for cle, (lbl, unite) in self.labels_param.items():
            lbl.config(text=str(donnees[cle]) + " " + unite)
        # Accumulation
        self.tampon.append(donnees)
        self.total_recu += 1
        self.lbl_accum.config(
            text="Trames accumulees : " + str(len(self.tampon))
            + "   (total recu : " + str(self.total_recu) + ")")

    # -------------------------------------------------------------------------
    def evaluer(self):
        """Evalue le segment : moyenne des scores du tampon, puis vide-le."""
        if not self.tampon:
            messagebox.showinfo("Aucune donnee",
                "Aucune trame accumulee depuis le dernier clic.\n"
                "Attendez que des trames CAN arrivent.")
            return

        score, type_code, conseil, moyennes, nb = evaluer_segment(
            self.tampon)
        type_nom, couleur = TYPES[type_code]

        self.lbl_score.config(text="Score : {:.1f} / 100".format(score))
        self.lbl_type.config(
            text="Type : {} ({})".format(type_nom, type_code), fg=couleur)
        self.lbl_conseil.config(text="Conseil : " + conseil)
        self.lbl_detail.config(
            text="Segment de {} trames  |  vitesse moy. {:.0f} km/h"
                 .format(nb, moyennes["vitesse"]))
        self.cadre.config(highlightbackground=couleur, highlightthickness=2)

        # Le tampon se vide : le prochain clic evaluera le segment suivant
        self.tampon = []
        self.lbl_accum.config(
            text="Trames accumulees : 0   (total recu : "
            + str(self.total_recu) + ")")

    # -------------------------------------------------------------------------
    def reset(self):
        """Vide le tampon et efface le resultat, sans evaluer."""
        self.tampon = []
        self.lbl_accum.config(
            text="Trames accumulees : 0   (total recu : "
            + str(self.total_recu) + ")")
        self.lbl_score.config(text="Score : --", fg="white")
        self.lbl_type.config(text="Type : --", fg="#94a3b8")
        self.lbl_conseil.config(text="")
        self.lbl_detail.config(text="Tampon remis a zero.")
        self.cadre.config(highlightthickness=0)


# =============================================================================
# 6. Point d'entree
# =============================================================================
def main():
    t = threading.Thread(target=thread_can, daemon=True)
    t.start()

    root = tk.Tk()
    app = CoachApp(root)

    def on_close():
        arret_demande.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
