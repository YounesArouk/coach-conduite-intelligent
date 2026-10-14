#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coach_can.py  (VERSION CORRIGEE ET DURCIE)
===========================================
Raspberry Pi - Reception trame CAN + Modele IA + Affichage

CORRECTIONS PAR RAPPORT A LA VERSION PRECEDENTE :
  [1] Chemin du .pkl robuste : trouve le modele dans le dossier du script,
      peu importe le repertoire courant (corrige le FileNotFoundError).
  [2] Verification de l'etat de l'interface CAN au demarrage : detecte
      DOWN et BUS-OFF, et tente de les corriger automatiquement.
  [3] Surveillance continue du BUS-OFF pendant l'ecoute : si le bus
      tombe, le script le signale et tente un redemarrage (au lieu de
      rester fige indefiniment, defaut majeur de l'ancienne version).
  [4] Reception non bloquante (timeout) : permet la surveillance + un
      Ctrl+C propre a tout moment.
  [5] Messages d'erreur explicites avec la commande exacte a lancer.

PREREQUIS :
    sudo apt install can-utils
    pip3 install python-can scikit-learn pandas joblib

ACTIVATION DU BUS CAN (avec recuperation auto du BUS-OFF) :
    sudo ip link set can0 down
    sudo ip link set can0 type can bitrate 500000 restart-ms 100
    sudo ip link set can0 up

LANCEMENT :
    python3 coach_can.py
"""
import os
import sys
import time
import subprocess

import can
import joblib
import pandas as pd

# =============================================================================
# 1. Chargement du modele IA  --  [1] chemin robuste
# =============================================================================
# Le .pkl est cherche DANS LE DOSSIER DU SCRIPT, pas dans le repertoire courant.
DOSSIER_SCRIPT = os.path.dirname(os.path.abspath(__file__))
PKL = os.path.join(DOSSIER_SCRIPT, "modele_coach_conduite.pkl")

if not os.path.exists(PKL):
    print(f"ERREUR : modele introuvable.\n   Attendu ici : {PKL}")
    print("Copiez 'modele_coach_conduite.pkl' a cote de ce script.")
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
CAN_ID     = 0x100
CANAL      = "can0"          # mettre "vcan0" pour un test sans materiel
BITRATE    = 500000          # doit etre identique cote Arduino
TYPES      = {0: "ECO", 1: "NORMAL", 2: "AGRESSIF"}

# Plages d'encodage : DOIVENT etre identiques a celles de l'Arduino
PLAGES = [
    ("vitesse",            0,  180),
    ("acceleration",      -8,    5),
    ("freinage",           0,  100),
    ("regime_moteur",    700, 6500),
    ("niveau_carburant",   0,  100),
    ("temp_moteur",       70,  115),
    ("angle_volant",    -180,  180),
    ("conso_instant",      0,   25),
]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def score_vers_type(s):
    return 0 if s >= 70 else (1 if s >= 45 else 2)


# =============================================================================
# 3. Etat de l'interface CAN  --  [2] et [3]
# =============================================================================
def etat_interface(canal):
    """Renvoie un texte d'etat de l'interface CAN ('UP', 'DOWN', 'BUS-OFF'...).

    Lit la sortie de 'ip -details link show'. Renvoie 'INCONNU' si la
    commande echoue (ex : interface virtuelle vcan0).
    """
    try:
        sortie = subprocess.run(
            ["ip", "-details", "link", "show", canal],
            capture_output=True, text=True, timeout=3
        ).stdout
    except Exception:
        return "INCONNU"

    if "BUS-OFF" in sortie:
        return "BUS-OFF"
    if "state UP" in sortie:
        return "UP"
    if "state DOWN" in sortie:
        return "DOWN"
    return "INCONNU"


def relancer_interface(canal):
    """Tente de redemarrer l'interface CAN (down -> up avec restart-ms).

    Necessite les droits sudo. Renvoie True si la commande s'execute.
    """
    cmds = [
        ["sudo", "ip", "link", "set", canal, "down"],
        ["sudo", "ip", "link", "set", canal, "type", "can",
         "bitrate", str(BITRATE), "restart-ms", "100"],
        ["sudo", "ip", "link", "set", canal, "up"],
    ]
    try:
        for c in cmds:
            subprocess.run(c, check=True, timeout=5,
                           capture_output=True)
        return True
    except Exception as e:
        print(f"   Echec du redemarrage automatique : {e}")
        return False


def verifier_can_au_demarrage(canal):
    """Verifie l'etat de l'interface avant de commencer l'ecoute.

    Corrige automatiquement les etats DOWN et BUS-OFF si possible.
    """
    if canal.startswith("vcan"):
        return   # interface virtuelle : pas de verification materielle

    etat = etat_interface(canal)
    print(f"  Etat de l'interface '{canal}' : {etat}")

    if etat in ("DOWN", "BUS-OFF", "INCONNU"):
        print(f"  Interface non operationnelle -> tentative de redemarrage...")
        if relancer_interface(canal):
            time.sleep(0.5)
            etat = etat_interface(canal)
            print(f"  Nouvel etat : {etat}")

    if etat == "BUS-OFF":
        print("\n  ATTENTION : interface toujours en BUS-OFF.")
        print("  Cause probable : quartz du MCP2515 mal declare.")
        print("  Verifiez 'oscillator=' dans /boot/firmware/config.txt")
        print("  et l'inscription du quartz (8.000 -> 8000000).")


# =============================================================================
# 4. Decodage de la trame CAN
# =============================================================================
def decoder_trame(data):
    """Convertit les 8 octets CAN en dictionnaire de parametres reels."""
    donnees = {}
    for i, (nom, mini, maxi) in enumerate(PLAGES):
        valeur = mini + (data[i] / 255.0) * (maxi - mini)
        if nom in ("regime_moteur", "angle_volant"):
            donnees[nom] = int(round(valeur))
        else:
            donnees[nom] = round(valeur, 2)
    return donnees


# =============================================================================
# 5. Coach IA
# =============================================================================
def generer_conseil(d, type_code):
    if type_code == 0:
        return "Conduite economique et sure. Continuez ainsi !"
    problemes = []
    if d["freinage"] > 55:
        problemes.append((d["freinage"],
            "Anticipez davantage pour freiner en douceur."))
    if abs(d["acceleration"]) > 3.0:
        problemes.append((abs(d["acceleration"]) * 20,
            "Accelerez plus progressivement, evitez les a-coups."))
    if d["regime_moteur"] > 4000:
        problemes.append((d["regime_moteur"] / 60,
            "Passez les rapports plus tot pour baisser le regime."))
    if d["vitesse"] > 110:
        problemes.append((d["vitesse"],
            "Reduisez votre vitesse."))
    if d["conso_instant"] > 16:
        problemes.append((d["conso_instant"] * 6,
            "Consommation elevee : conduite plus souple."))
    if not problemes:
        return "Conduite correcte, quelques ajustements possibles."
    problemes.sort(reverse=True)
    base = problemes[0][1]
    return ("Conduite agressive. " + base) if type_code == 2 else base


def evaluer(donnees):
    X = pd.DataFrame([donnees])[FEATURES]
    score = clamp(float(MODEL.predict(X)[0]), 0, 100)
    type_code = score_vers_type(score)
    return score, type_code, generer_conseil(donnees, type_code)


# =============================================================================
# 6. Programme principal
# =============================================================================
def main():
    print("=" * 56)
    print("  COACH DE CONDUITE - Reception CAN (version durcie)")
    print("=" * 56)

    # [2] Verification de l'etat du bus AVANT d'ouvrir le socket
    verifier_can_au_demarrage(CANAL)

    # Ouverture du bus
    try:
        bus = can.interface.Bus(channel=CANAL, interface="socketcan")
    except Exception as e:
        print(f"\nERREUR : impossible d'ouvrir le bus CAN '{CANAL}'.")
        print(f"   {e}")
        print("\nCommandes a lancer :")
        print("   sudo ip link set can0 down")
        print("   sudo ip link set can0 type can bitrate 500000 "
              "restart-ms 100")
        print("   sudo ip link set can0 up")
        return

    print(f"\n  Ecoute du bus '{CANAL}' (ID 0x{CAN_ID:X})...")
    print("  Ctrl+C pour arreter.\n")

    compteur          = 0
    derniere_verif    = time.time()
    derniere_reception = time.time()

    try:
        while True:
            # [4] Reception NON bloquante : timeout 1 s
            msg = bus.recv(timeout=1.0)

            # --- Surveillance periodique du bus (toutes les 5 s) ---
            maintenant = time.time()
            if maintenant - derniere_verif > 5.0:
                derniere_verif = maintenant
                etat = etat_interface(CANAL)
                if etat == "BUS-OFF":
                    # [3] Le bus est tombe pendant l'ecoute
                    print("\n  !!! BUS-OFF detecte pendant l'ecoute !!!")
                    print("  Tentative de redemarrage du bus...")
                    if relancer_interface(CANAL):
                        print("  Bus redemarre. Reprise de l'ecoute.\n")
                    else:
                        print("  Echec. Verifiez quartz/cablage.\n")
                elif (msg is None and
                      maintenant - derniere_reception > 10.0):
                    # Aucune trame depuis 10 s : avertissement
                    print("  (aucune trame recue depuis 10 s - "
                          "verifiez l'Arduino et le cablage CAN)")
                    derniere_reception = maintenant

            if msg is None:
                continue   # timeout : on reboucle pour la surveillance

            derniere_reception = time.time()

            # On ne traite que notre trame
            if msg.arbitration_id != CAN_ID or len(msg.data) < 8:
                continue

            compteur += 1
            donnees = decoder_trame(msg.data)
            score, type_code, conseil = evaluer(donnees)

            print("=" * 56)
            print(f"  Trame #{compteur:04d}")
            print(f"  Vitesse {donnees['vitesse']} km/h  |  "
                  f"Frein {donnees['freinage']} %  |  "
                  f"Regime {donnees['regime_moteur']} tr/min")
            print(f"  Conso {donnees['conso_instant']} L/100  |  "
                  f"Carburant {donnees['niveau_carburant']} %")
            print("  " + "-" * 52)
            print(f"  SCORE   : {score:.1f} / 100")
            print(f"  TYPE    : {TYPES[type_code]} ({type_code})")
            print(f"  CONSEIL : {conseil}")
            print("=" * 56 + "\n")

    except KeyboardInterrupt:
        print(f"\nArret. {compteur} trames traitees.")
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
