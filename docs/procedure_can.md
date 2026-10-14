# Procedure CAN : configuration, activation, depannage

## 1. Configuration du Raspberry Pi (une seule fois)

Editer la configuration :

    sudo nano /boot/firmware/config.txt

Ajouter a la fin (oscillator = VRAIE valeur du quartz du module) :

    dtparam=spi=on
    dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25

Puis redemarrer :

    sudo reboot

## 2. Activation du bus CAN (a chaque demarrage)

    sudo ip link set can0 down
    sudo ip link set can0 type can bitrate 500000 restart-ms 100
    sudo ip link set can0 up

Verifier :

    ip -details link show can0      # doit afficher "state UP"

## 3. Activation automatique au demarrage (recommande)

Creer le service :

    sudo nano /etc/systemd/system/can0.service

Contenu :

    [Unit]
    Description=Activation interface CAN can0
    After=multi-user.target

    [Service]
    Type=oneshot
    ExecStart=/sbin/ip link set can0 up type can bitrate 500000 restart-ms 100
    RemainAfterExit=yes

    [Install]
    WantedBy=multi-user.target

Activer :

    sudo systemctl enable can0.service
    sudo systemctl start can0.service

## 4. DEPANNAGE

### 4.1 "RTNETLINK answers: Connection timed out" au 'ip link ... up'

Symptome : la puce est vue au boot (dmesg : "MCP2515 successfully
initialized") mais l'activation echoue.

C'est un probleme MATERIEL (pilote <-> puce). Causes par ordre :

  CAUSE 1 - Broche INT non connectee
     Le fil INT du MCP2515 doit aller sur GPIO25 (Pin 22).
     C'est la cause la plus frequente. L'init au boot reussit
     sans INT, mais l'activation a besoin de l'interruption.

  CAUSE 2 - Alimentation 3.3V au lieu de 5V
     VCC du MCP2515 doit etre sur 5V (Pin 2 ou 4).

  CAUSE 3 - Quartz mal declare
     'oscillator=' dans config.txt doit correspondre au quartz
     physique reel (8.000 -> 8000000, 16.000 -> 16000000).

  CAUSE 4 - Bus sans terminaison / sans 2e noeud
     En mode normal, le controleur doit se synchroniser. Sans
     resistances 120 ohms ni 2e noeud actif, il n'y arrive pas.

Diagnostic : apres l'echec, lancer

    dmesg | tail -15

et lire le message precis du pilote mcp251x.

### 4.2 "Network is down"

L'interface n'est pas activee. Refaire l'etape 2.

### 4.3 "Device or resource busy"

L'interface est UP mais bloquee (souvent BUS-OFF). Toujours
faire 'down' puis 'up' :

    sudo ip link set can0 down
    sudo ip link set can0 type can bitrate 500000 restart-ms 100
    sudo ip link set can0 up

### 4.4 etat "BUS-OFF"

Le controleur s'est isole apres trop d'erreurs. Cause quasi
certaine : quartz mal declare (timing CAN faux). Corriger le
quartz (4.1 cause 3) puis relancer avec restart-ms 100.

## 5. Test loopback (valider le module sans l'Arduino)

Le mode loopback fait que le controleur se parle a lui-meme.

    sudo ip link set can0 down
    sudo ip link set can0 type can bitrate 500000 loopback on
    sudo ip link set can0 up

Terminal 1 :  candump can0
Terminal 2 :  cansend can0 100#1122334455667788

  - La trame apparait  -> module Raspberry OK, chercher cote
                          Arduino / cablage CAN / terminaison.
  - 'up' echoue meme   -> probleme materiel sur le module
    en loopback           Raspberry lui-meme (INT, alim, quartz).

Revenir en mode normal apres le test :

    sudo ip link set can0 down
    sudo ip link set can0 type can bitrate 500000 restart-ms 100
    sudo ip link set can0 up

## 6. Diagnostic automatise

Le script diag_can.sh execute la plupart de ces verifications :

    cd 3_raspberry
    chmod +x diag_can.sh
    ./diag_can.sh
