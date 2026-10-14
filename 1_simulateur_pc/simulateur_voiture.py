#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simulateur de Voiture (PC) -> envoi SERIE vers Arduino
=======================================================
Genere les 8 parametres de conduite et les transmet a l'Arduino
via le port USB/serie. L'Arduino construit ensuite la trame CAN.

ARCHITECTURE :
  [CE SCRIPT] --USB/Serie--> [Arduino] --CAN--> [Raspberry Pi + IA]

Format envoye a l'Arduino (une ligne par mesure) :
  vitesse,acceleration,freinage,regime,carburant,temp,volant,conso\\n

Prerequis :
    pip3 install pyserial

Lancement :
    python3 simulateur_voiture.py                      (auto-detection du port)
    python3 simulateur_voiture.py COM3                 (Windows)
    python3 simulateur_voiture.py /dev/ttyUSB0         (Linux)
    python3 simulateur_voiture.py /dev/ttyUSB0 Sportive
"""
import sys
import time
import random

import serial
import serial.tools.list_ports

# =============================================================================
# 1. Parametres de connexion serie
# =============================================================================
BAUDRATE   = 115200       # doit correspondre au Serial.begin() de l'Arduino
INTERVALLE = 0.8          # secondes entre deux mesures envoyees

# Profils de conduite (intensite 0=souple ... 1=sportif)
PROFILS = {
    "Souple":   0.15,
    "Normale":  0.50,
    "Sportive": 0.88,
}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# =============================================================================
# 2. Modele physique de la voiture (genere les parametres)
# =============================================================================
class Voiture:
    def __init__(self, intensite=0.50):
        self.profil = intensite
        self.reset()

    def reset(self):
        self.vitesse          = 0.0
        self.acceleration     = 0.0
        self.freinage         = 0.0
        self.regime_moteur    = 800.0
        self.niveau_carburant = round(random.uniform(40, 100), 1)
        self.temp_moteur      = 75.0
        self.angle_volant     = 0.0
        self.conso_instant    = 0.0

    def step(self):
        p = self.profil
        vitesse_cible = 45 + p * 95

        action = random.choices(
            ["accelerer", "maintenir", "freiner"],
            weights=[0.45 + 0.2 * p, 0.35, 0.20 + 0.2 * (1 - p)]
        )[0]

        if action == "accelerer":
            self.acceleration = clamp(random.gauss(1.2 + p * 3.2, 0.8),
                                      -8, 5)
            self.freinage     = clamp(random.gauss(5, 4), 0, 100)
            gain              = (8 + p * 18) * (1.0 if self.vitesse
                                                < vitesse_cible else 0.3)
            self.vitesse      = clamp(self.vitesse + gain, 0, 180)
        elif action == "freiner":
            self.acceleration = clamp(random.gauss(-1.2 - p * 3.2, 0.8),
                                      -8, 5)
            self.freinage     = clamp(random.gauss(30 + p * 50, 12), 0, 100)
            self.vitesse      = clamp(self.vitesse - (6 + p * 16), 0, 180)
        else:  # maintenir
            self.acceleration = clamp(random.gauss(0, 0.6 + p * 0.8), -8, 5)
            self.freinage     = clamp(random.gauss(8, 5), 0, 100)
            self.vitesse      = clamp(
                self.vitesse + (vitesse_cible - self.vitesse) * 0.25
                + random.gauss(0, 3), 0, 180)

        self.regime_moteur = clamp(
            900 + self.vitesse * (22 + p * 18) + random.gauss(0, 150),
            700, 6500)

        cible_temp = 82 + p * 16 + self.regime_moteur / 600.0
        self.temp_moteur = clamp(
            self.temp_moteur + (cible_temp - self.temp_moteur) * 0.25,
            70, 115)

        if random.random() < 0.35:
            self.angle_volant = clamp(random.gauss(0, 30 + p * 70),
                                      -180, 180)
        else:
            self.angle_volant *= 0.5

        self.conso_instant = clamp(
            3 + self.vitesse * 0.06 + self.regime_moteur * 0.0016
            + abs(self.acceleration) * 1.4 + random.gauss(0, 1),
            0, 25)

        self.niveau_carburant = clamp(
            self.niveau_carburant - self.conso_instant * 0.012, 0, 100)

    def ligne_serie(self):
        """Formate les 8 parametres en une ligne CSV pour l'Arduino."""
        return "{:.1f},{:.2f},{:.1f},{:d},{:.1f},{:.1f},{:d},{:.2f}".format(
            self.vitesse,
            self.acceleration,
            self.freinage,
            int(self.regime_moteur),
            self.niveau_carburant,
            self.temp_moteur,
            int(self.angle_volant),
            self.conso_instant,
        )


# =============================================================================
# 3. Detection automatique du port Arduino
# =============================================================================
def detecter_port():
    """Cherche un port serie ressemblant a un Arduino."""
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "").lower()
        if "arduino" in desc or "ch340" in desc or "usb" in desc:
            return p.device
    if ports:
        return ports[0].device   # a defaut, le premier port trouve
    return None


# =============================================================================
# 4. Programme principal
# =============================================================================
def main():
    # --- Arguments : port serie + profil ---
    port   = None
    profil = "Normale"
    for arg in sys.argv[1:]:
        if arg in PROFILS:
            profil = arg
        else:
            port = arg

    if port is None:
        port = detecter_port()
        if port is None:
            print("ERREUR : aucun port serie detecte.")
            print("Branchez l'Arduino, ou precisez le port :")
            print("   python3 simulateur_voiture.py /dev/ttyUSB0")
            return
        print(f"Port detecte automatiquement : {port}")

    # --- Connexion serie ---
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=1)
    except serial.SerialException as e:
        print(f"ERREUR : impossible d'ouvrir {port}\n   {e}")
        return

    time.sleep(2)   # laisse l'Arduino redemarrer apres ouverture du port
    print("=" * 60)
    print(f"  SIMULATEUR VOITURE -> ARDUINO  (port {port})")
    print(f"  Profil de conduite : {profil}")
    print("=" * 60)
    print("  Envoi des trames... Ctrl+C pour arreter.\n")

    voiture = Voiture(PROFILS[profil])
    compteur = 0

    try:
        while True:
            voiture.step()
            ligne = voiture.ligne_serie()

            # Envoi a l'Arduino (le \n marque la fin de trame)
            ser.write((ligne + "\n").encode("ascii"))
            compteur += 1

            # Affichage local de ce qui est envoye
            print(f"#{compteur:04d} -> {ligne}")

            # Lecture de l'accuse de reception de l'Arduino (optionnel)
            if ser.in_waiting:
                reponse = ser.readline().decode("ascii", "ignore").strip()
                if reponse:
                    print(f"        Arduino : {reponse}")

            time.sleep(INTERVALLE)

    except KeyboardInterrupt:
        print(f"\nArret. {compteur} trames envoyees.")
    finally:
        ser.close()
        print("Port serie ferme.")


if __name__ == "__main__":
    main()
