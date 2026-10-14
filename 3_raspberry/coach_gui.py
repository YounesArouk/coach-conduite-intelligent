#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach de Conduite - Interface Tkinter pour Raspberry Pi
========================================================
Affiche : Score de conduite (0-100) | Type (Eco/Normal/Agressif) | Conseil

Prerequis sur le Raspberry :
    sudo apt-get install python3-tk
    pip3 install scikit-learn pandas joblib

Le fichier 'modele_coach_conduite.pkl' doit etre dans le meme dossier.
Lancement :
    python3 coach_gui.py
"""
import os
import tkinter as tk
from tkinter import messagebox

import pandas as pd
import joblib

# =============================================================================
# 1. Chargement du modele
# =============================================================================
PKL = "modele_coach_conduite.pkl"

if not os.path.exists(PKL):
    raise FileNotFoundError(
        "Modele introuvable : " + PKL + "\n"
        "Placez le fichier .pkl dans le meme dossier que ce script."
    )

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
# 2. Champs de saisie : (cle, libelle, unite, valeur par defaut)
# =============================================================================
CHAMPS = [
    ("vitesse",          "Vitesse",          "km/h",     80.0),
    ("acceleration",     "Acceleration",     "m/s2",      1.5),
    ("freinage",         "Freinage",         "%",        30.0),
    ("regime_moteur",    "Regime moteur",    "tr/min", 2500.0),
    ("niveau_carburant", "Niveau carburant", "%",        60.0),
    ("temp_moteur",      "Temp. moteur",     "degC",     90.0),
    ("angle_volant",     "Angle volant",     "deg",       0.0),
    ("conso_instant",    "Conso instant.",   "L/100km",  10.0),
]

# Couleurs par type de conduite
TYPES = {
    0: ("ECO",      "#22c55e"),   # vert
    1: ("NORMAL",   "#eab308"),   # jaune
    2: ("AGRESSIF", "#ef4444"),   # rouge
}

# =============================================================================
# 3. Logique : score -> type -> conseil
# =============================================================================
def score_vers_type(score):
    if score >= 70:
        return 0
    elif score >= 45:
        return 1
    return 2


def generer_conseil(donnees, type_code):
    if type_code == 0:
        return ("Excellente conduite ! Vous economisez du carburant "
                "et roulez en securite. Continuez ainsi.")

    problemes = []
    if donnees["freinage"] > 55:
        problemes.append((donnees["freinage"],
            "Anticipez davantage la route pour freiner en douceur."))
    if abs(donnees["acceleration"]) > 3.0:
        problemes.append((abs(donnees["acceleration"]) * 20,
            "Accelerez plus progressivement, evitez les a-coups."))
    if donnees["regime_moteur"] > 4000:
        problemes.append((donnees["regime_moteur"] / 60,
            "Passez les rapports plus tot pour baisser le regime moteur."))
    if donnees["vitesse"] > 110:
        problemes.append((donnees["vitesse"],
            "Reduisez votre vitesse : meilleure securite et consommation."))
    if donnees["conso_instant"] > 16:
        problemes.append((donnees["conso_instant"] * 6,
            "Consommation elevee : adoptez une conduite plus souple."))
    if abs(donnees["angle_volant"]) > 120:
        problemes.append((abs(donnees["angle_volant"]),
            "Braquages brusques detectes : tournez plus doucement."))

    if not problemes:
        return "Conduite correcte. Quelques petits ajustements sont possibles."

    problemes.sort(reverse=True)
    conseil = problemes[0][1]
    if type_code == 2:
        return "Conduite agressive. " + conseil
    return conseil


# =============================================================================
# 4. Interface graphique
# =============================================================================
class CoachApp:
    def __init__(self, root):
        self.root = root
        root.title("Coach de Conduite - Raspberry Pi")
        root.configure(bg="#1e293b")
        root.geometry("520x640")

        # --- Titre ---
        tk.Label(root, text="COACH DE CONDUITE",
                 font=("Helvetica", 18, "bold"),
                 fg="white", bg="#1e293b").pack(pady=(16, 4))
        tk.Label(root, text="Saisissez les parametres puis cliquez sur Evaluer",
                 font=("Helvetica", 9), fg="#94a3b8",
                 bg="#1e293b").pack(pady=(0, 12))

        # --- Zone de saisie ---
        form = tk.Frame(root, bg="#1e293b")
        form.pack(padx=20, fill="x")

        self.entrees = {}
        for i, (cle, libelle, unite, defaut) in enumerate(CHAMPS):
            tk.Label(form, text=libelle, font=("Helvetica", 10),
                     fg="white", bg="#1e293b", anchor="w", width=16
                     ).grid(row=i, column=0, sticky="w", pady=3)
            e = tk.Entry(form, font=("Helvetica", 10), width=12,
                         justify="center")
            e.insert(0, str(defaut))
            e.grid(row=i, column=1, pady=3, padx=6)
            tk.Label(form, text=unite, font=("Helvetica", 9),
                     fg="#94a3b8", bg="#1e293b", anchor="w", width=8
                     ).grid(row=i, column=2, sticky="w")
            self.entrees[cle] = e

        # --- Bouton Evaluer ---
        tk.Button(root, text="EVALUER LA CONDUITE",
                  font=("Helvetica", 12, "bold"),
                  bg="#3b82f6", fg="white", activebackground="#2563eb",
                  relief="flat", padx=20, pady=10,
                  command=self.evaluer).pack(pady=16)

        # --- Zone resultat ---
        self.cadre_res = tk.Frame(root, bg="#0f172a", relief="flat", bd=0)
        self.cadre_res.pack(padx=20, pady=4, fill="both", expand=True)

        self.lbl_score = tk.Label(self.cadre_res, text="Score : --",
                                  font=("Helvetica", 22, "bold"),
                                  fg="white", bg="#0f172a")
        self.lbl_score.pack(pady=(16, 4))

        self.lbl_type = tk.Label(self.cadre_res, text="Type : --",
                                 font=("Helvetica", 16, "bold"),
                                 fg="#94a3b8", bg="#0f172a")
        self.lbl_type.pack(pady=4)

        self.lbl_conseil = tk.Label(self.cadre_res, text="",
                                    font=("Helvetica", 10),
                                    fg="#cbd5e1", bg="#0f172a",
                                    wraplength=440, justify="center")
        self.lbl_conseil.pack(pady=(8, 16), padx=16)

    # -------------------------------------------------------------------------
    def evaluer(self):
        # Lecture et validation des champs
        donnees = {}
        try:
            for cle, libelle, _, _ in CHAMPS:
                donnees[cle] = float(self.entrees[cle].get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Erreur de saisie",
                "Veuillez entrer des valeurs numeriques valides.")
            return

        # Prediction du score
        X = pd.DataFrame([donnees])[FEATURES]
        score = float(MODEL.predict(X)[0])
        score = max(0.0, min(100.0, score))

        type_code = score_vers_type(score)
        type_nom, couleur = TYPES[type_code]
        conseil = generer_conseil(donnees, type_code)

        # Affichage
        self.lbl_score.config(text="Score : {:.1f} / 100".format(score))
        self.lbl_type.config(
            text="Type : {} ({})".format(type_nom, type_code),
            fg=couleur)
        self.lbl_conseil.config(text="Conseil : " + conseil)
        self.cadre_res.config(highlightbackground=couleur,
                              highlightthickness=2)


# =============================================================================
# 5. Point d'entree
# =============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = CoachApp(root)
    root.mainloop()
