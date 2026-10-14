# Coach de Conduite - Projet embarque IA + CAN

Systeme d'evaluation de la conduite : un simulateur genere des
parametres de conduite, transmis par bus CAN a un Raspberry Pi
qui les analyse avec un modele d'intelligence artificielle et
affiche un score, un type de conduite et un conseil.

## Architecture

    [PC simulateur] --USB/Serie--> [Arduino + MCP2515]
         |                                |
    simulateur_voiture.py          arduino_can_tx.ino
         |                                |
         genere 8 parametres        encode + emet trame CAN
                                          |
                                       Bus CAN
                                          |
                              [MCP2515 + Raspberry Pi]
                                          |
                                  coach_gui_can.py
                                  decode + IA + affichage

## Structure des dossiers

    coach_conduite/
    |
    +-- README.md
    |
    +-- 1_simulateur_pc/          COTE PC
    |   +-- simulateur_voiture.py     genere params, envoi serie
    |   +-- requirements.txt          pyserial
    |
    +-- 2_arduino/                COTE ARDUINO
    |   +-- arduino_can_tx/
    |       +-- arduino_can_tx.ino    recoit serie, emet trame CAN
    |
    +-- 3_raspberry/              COTE RASPBERRY PI
    |   +-- coach_gui_can.py          PRINCIPAL : CAN + IA + interface
    |   +-- coach_can.py              secours : version console
    |   +-- coach_gui.py              secours : saisie manuelle
    |   +-- diag_can.sh               diagnostic CAN automatise
    |   +-- modele_coach_conduite.pkl modele IA entraine
    |   +-- requirements.txt          python-can, scikit-learn==1.6.1...
    |
    +-- 4_entrainement/           ENTRAINEMENT DU MODELE
    |   +-- train.csv                 500 lignes
    |   +-- test.csv                  60 lignes
    |
    +-- docs/                     DOCUMENTATION TECHNIQUE
        +-- cablage_mcp2515.md        schema de cablage
        +-- format_trame_can.md       encodage des 8 octets
        +-- procedure_can.md          config + depannage CAN

## Installation

### Cote PC (simulateur)

    cd 1_simulateur_pc
    pip install -r requirements.txt
    python simulateur_voiture.py COM10        # adapter le port

### Cote Arduino

Ouvrir 2_arduino/arduino_can_tx/arduino_can_tx.ino dans l'IDE
Arduino. Installer la bibliotheque "mcp_can" de coryjfowler.
IMPORTANT : verifier la ligne #define QUARTZ_MCP (MCP_8MHZ ou
MCP_16MHZ selon le quartz du module). Televerser.

### Cote Raspberry Pi

    sudo apt install -y can-utils python3-tk python3-pip
    cd 3_raspberry
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

## Lancement

1. Activer le bus CAN sur le Raspberry :

       sudo ip link set can0 down
       sudo ip link set can0 type can bitrate 500000 restart-ms 100
       sudo ip link set can0 up

2. Lancer l'interface (Raspberry) :

       cd 3_raspberry
       source venv/bin/activate
       python3 coach_gui_can.py

3. Lancer le simulateur (PC) :

       python simulateur_voiture.py COM10

## Utilisation de l'interface

- Le tableau de bord affiche les 8 parametres en temps reel.
- Chaque trame recue est accumulee dans un tampon.
- Bouton EVALUER : le modele IA calcule un score global sur
  toutes les trames accumulees depuis le dernier clic, affiche
  score + type + conseil, puis vide le tampon.
- Bouton RESET : vide le tampon sans evaluer.

## Depannage

Voir docs/procedure_can.md pour le detail. Resume :

- "Connection timed out"   -> probleme materiel (broche INT,
                              alimentation, quartz). Voir doc.
- "Network is down"        -> bus non active : refaire l'etape 1.
- "Device or resource busy"-> faire 'down' puis 'up'.
- etat "BUS-OFF"           -> quartz mal declare.

Diagnostic automatise :

    cd 3_raspberry
    chmod +x diag_can.sh
    ./diag_can.sh

## Notes importantes

- Le modele a ete entraine avec scikit-learn 1.6.1. Le fichier
  requirements.txt epingle cette version pour eviter des
  predictions erronees (InconsistentVersionWarning).
- modele_coach_conduite.pkl doit toujours rester dans le meme
  dossier que coach_gui_can.py.
