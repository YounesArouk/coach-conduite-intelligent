/*
 * arduino_can_tx.ino  (VERSION CORRIGEE ET DURCIE)
 * =================================================
 * Arduino - Reception serie (depuis le PC) + Emission trame CAN
 *
 * CORRECTIONS PAR RAPPORT A LA VERSION PRECEDENTE :
 *   [1] Quartz : constante QUARTZ_MCP unique, FACILE a changer (cause n1
 *       des pannes CAN). Mettre MCP_8MHZ ou MCP_16MHZ selon le module.
 *   [2] LED de diagnostic (D13) : fixe = CAN OK, eteinte = erreur d'envoi.
 *   [3] Compteur d'echecs consecutifs : re-init du MCP2515 si le bus
 *       tombe (recuperation automatique du BUS-OFF cote emetteur).
 *   [4] Vidage du buffer serie en cas de trame invalide (evite la
 *       desynchronisation des trames suivantes).
 *
 * MATERIEL : Arduino Uno/Nano + module CAN MCP2515 (bus SPI)
 * BIBLIOTHEQUE : "mcp_can" par coryjfowler
 *
 * CABLAGE MCP2515 <-> Arduino Uno :
 *   VCC -> 5V    GND -> GND
 *   CS  -> D10   SCK -> D13   SI -> D11   SO -> D12
 *   INT -> D2 (non utilise)
 *
 * BUS CAN entre les 2 modules MCP2515 :
 *   CAN_H <-> CAN_H   et   CAN_L <-> CAN_L
 *   + jumper de terminaison 120 ohms ferme sur CHAQUE module.
 */
#include <SPI.h>
#include <mcp_can.h>

// ===========================================================================
// CONFIGURATION  --  VERIFIEZ CES 2 LIGNES AVANT DE COMPILER
// ===========================================================================
//
//  >>> QUARTZ_MCP : regardez le quartz metallique sur VOTRE module MCP2515.
//      Inscription "8.000"  -> MCP_8MHZ
//      Inscription "16.000" -> MCP_16MHZ
//
#define QUARTZ_MCP   MCP_8MHZ        // <-- A ADAPTER A VOTRE MODULE !
#define VITESSE_CAN  CAN_500KBPS     // doit etre identique cote Raspberry

const int           SPI_CS_PIN = 10;        // broche CS du MCP2515
const unsigned long CAN_ID     = 0x100;     // identifiant de la trame CAN
const int           LED_PIN    = 13;        // LED integree (diagnostic)

MCP_CAN CAN(SPI_CS_PIN);

float params[8];
int   echecs_consecutifs = 0;               // pour la recuperation auto

// ===========================================================================
// Encode une valeur reelle [mini..maxi] sur 1 octet [0..255]
// (operation INVERSE du decodage cote Raspberry Pi)
// ===========================================================================
byte encoder(float val, float mini, float maxi) {
  if (val < mini) val = mini;
  if (val > maxi) val = maxi;
  return (byte)((val - mini) * 255.0 / (maxi - mini) + 0.5);
}

// ===========================================================================
// Initialisation (ou re-initialisation) du controleur CAN
// ===========================================================================
bool init_can() {
  if (CAN.begin(MCP_ANY, VITESSE_CAN, QUARTZ_MCP) == CAN_OK) {
    CAN.setMode(MCP_NORMAL);
    return true;
  }
  return false;
}

// ===========================================================================
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Init CAN avec re-essai jusqu'au succes
  while (!init_can()) {
    Serial.println("CAN init KO - verifiez QUARTZ_MCP et le cablage.");
    digitalWrite(LED_PIN, HIGH); delay(250);   // clignote = echec d'init
    digitalWrite(LED_PIN, LOW);  delay(250);
  }
  digitalWrite(LED_PIN, HIGH);   // LED fixe = CAN pret
  Serial.println("CAN pret.");
}

// ===========================================================================
void loop() {
  if (!Serial.available()) return;

  // --- Lecture d'une ligne complete ---
  String ligne = Serial.readStringUntil('\n');
  ligne.trim();
  if (ligne.length() == 0) return;

  // --- Decoupage des 8 valeurs separees par des virgules ---
  int idx = 0;
  while (ligne.length() > 0 && idx < 8) {
    int virgule = ligne.indexOf(',');
    String morceau;
    if (virgule == -1) {
      morceau = ligne;
      ligne   = "";
    } else {
      morceau = ligne.substring(0, virgule);
      ligne   = ligne.substring(virgule + 1);
    }
    params[idx++] = morceau.toFloat();
  }

  // --- Verification : il faut exactement 8 valeurs ---
  if (idx != 8) {
    Serial.println("Trame serie invalide (8 valeurs attendues).");
    while (Serial.available()) Serial.read();   // vide le buffer (anti-desync)
    return;
  }

  // --- Construction de la trame CAN (8 octets) ---
  byte trame[8];
  trame[0] = encoder(params[0],    0, 180);   // vitesse        km/h
  trame[1] = encoder(params[1],   -8,   5);   // acceleration   m/s2
  trame[2] = encoder(params[2],    0, 100);   // freinage       %
  trame[3] = encoder(params[3],  700,6500);   // regime moteur  tr/min
  trame[4] = encoder(params[4],    0, 100);   // carburant      %
  trame[5] = encoder(params[5],   70, 115);   // temp moteur    degC
  trame[6] = encoder(params[6], -180, 180);   // angle volant   deg
  trame[7] = encoder(params[7],    0,  25);   // conso          L/100

  // --- Emission sur le bus CAN ---
  byte res = CAN.sendMsgBuf(CAN_ID, 0, 8, trame);

  if (res == CAN_OK) {
    Serial.println("Trame CAN envoyee.");
    echecs_consecutifs = 0;
    digitalWrite(LED_PIN, HIGH);              // LED fixe = OK
  } else {
    Serial.println("Echec envoi CAN.");
    echecs_consecutifs++;
    digitalWrite(LED_PIN, LOW);               // LED eteinte = erreur

    // [3] Recuperation auto : apres 5 echecs, on re-initialise le MCP2515
    //     (sort le controleur d'un eventuel BUS-OFF).
    if (echecs_consecutifs >= 5) {
      Serial.println("5 echecs -> re-initialisation du CAN...");
      if (init_can()) {
        Serial.println("CAN re-initialise.");
        digitalWrite(LED_PIN, HIGH);
      }
      echecs_consecutifs = 0;
    }
  }
}
