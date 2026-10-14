#!/bin/bash
# =============================================================================
# diag_can.sh - Diagnostic complet du bus CAN sur Raspberry Pi
# =============================================================================
# Lance ce script sur le Raspberry pour identifier rapidement la cause
# d'un probleme de communication CAN.
#
#   chmod +x diag_can.sh
#   ./diag_can.sh
# =============================================================================
CANAL="can0"
echo "=================================================="
echo "  DIAGNOSTIC CAN - $(date '+%H:%M:%S')"
echo "=================================================="

# --- 1. Le module noyau est-il charge ? ---
echo ""
echo "[1] Module noyau mcp251x :"
if lsmod | grep -q mcp251x; then
    echo "    OK - le pilote mcp251x est charge."
else
    echo "    KO - pilote absent. Verifiez le dtoverlay dans config.txt."
fi

# --- 2. L'interface existe-t-elle ? ---
echo ""
echo "[2] Interface $CANAL :"
if ip link show "$CANAL" > /dev/null 2>&1; then
    echo "    OK - l'interface existe."
else
    echo "    KO - interface absente. Le MCP2515 n'est pas detecte."
    echo "    -> Verifiez le cablage SPI et le dtoverlay."
    exit 1
fi

# --- 3. Etat et horloge ---
echo ""
echo "[3] Etat detaille :"
DETAILS=$(ip -details link show "$CANAL")
ETAT=$(echo "$DETAILS"   | grep -oE 'state [A-Z-]+'  | awk '{print $2}')
CANSTATE=$(echo "$DETAILS"| grep -oE 'can state [A-Z-]+' | awk '{print $3}')
CLOCK=$(echo "$DETAILS"   | grep -oE 'clock [0-9]+'  | awk '{print $2}')
BITRATE=$(echo "$DETAILS" | grep -oE 'bitrate [0-9]+'| awk '{print $2}')

echo "    Etat interface : ${ETAT:-inconnu}"
echo "    Etat CAN       : ${CANSTATE:-inconnu}"
echo "    Horloge (clock): ${CLOCK:-inconnu} Hz"
echo "    Bitrate        : ${BITRATE:-inconnu} bit/s"

# --- 4. Diagnostic de l'horloge ---
echo ""
echo "[4] Analyse de l'horloge :"
if [ "$CLOCK" = "8000000" ] || [ "$CLOCK" = "16000000" ]; then
    echo "    OK - horloge coherente ($CLOCK Hz)."
else
    echo "    PROBLEME - horloge = $CLOCK Hz (anormal !)."
    echo "    Un MCP2515 a un quartz 8 ou 16 MHz, jamais autre chose."
    echo "    -> Corrigez 'oscillator=' dans /boot/firmware/config.txt"
fi

# --- 5. Diagnostic BUS-OFF ---
echo ""
echo "[5] Analyse de l'etat CAN :"
if [ "$CANSTATE" = "BUS-OFF" ]; then
    echo "    PROBLEME - le controleur est en BUS-OFF."
    echo "    -> Cause n1 : quartz mal declare (voir [4])."
    echo "    -> Relancez :"
    echo "       sudo ip link set $CANAL down"
    echo "       sudo ip link set $CANAL type can bitrate 500000 restart-ms 100"
    echo "       sudo ip link set $CANAL up"
elif [ "$CANSTATE" = "ERROR-ACTIVE" ]; then
    echo "    OK - le controleur est en ERROR-ACTIVE (etat normal)."
else
    echo "    Etat : ${CANSTATE:-inconnu}"
fi

# --- 6. Compteurs d'erreurs ---
echo ""
echo "[6] Compteurs d'erreurs :"
ip -statistics link show "$CANAL" | grep -A1 -E 'RX:|TX:' || \
    echo "    (statistiques non disponibles)"

# --- 7. Ecoute breve du bus ---
echo ""
echo "[7] Ecoute du bus pendant 3 secondes..."
if command -v candump > /dev/null 2>&1; then
    TRAMES=$(timeout 3 candump -n 5 "$CANAL" 2>/dev/null | wc -l)
    if [ "$TRAMES" -gt 0 ]; then
        echo "    OK - $TRAMES trame(s) recue(s). Le bus fonctionne !"
    else
        echo "    Aucune trame recue."
        echo "    -> Verifiez : Arduino sous tension, fils CAN_H/CAN_L,"
        echo "       jumpers de terminaison 120 ohms, quartz Arduino."
    fi
else
    echo "    candump absent. Installez : sudo apt install can-utils"
fi

echo ""
echo "=================================================="
echo "  FIN DU DIAGNOSTIC"
echo "=================================================="
