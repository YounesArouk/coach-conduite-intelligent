# Cablage des modules MCP2515

## 1. MCP2515 (Raspberry) <-> Raspberry Pi  (bus SPI)

| MCP2515 | Raspberry Pi   | Remarque                          |
|---------|----------------|-----------------------------------|
| VCC     | 5V  (Pin 2)    | IMPERATIF 5V, pas 3.3V            |
| GND     | GND (Pin 6)    |                                   |
| CS      | CE0 (Pin 24)   | SPI Chip Select                   |
| SCK     | SCLK(Pin 23)   | SPI Clock                         |
| SI      | MOSI(Pin 19)   | SPI Master-Out                    |
| SO      | MISO(Pin 21)   | SPI Master-In                     |
| INT     | GPIO25 (Pin 22)| OBLIGATOIRE - cause n1 du timeout |

ATTENTION : la broche INT est la plus souvent oubliee. Sans elle,
la puce est detectee au demarrage mais 'ip link set can0 up' echoue
avec "Connection timed out".

## 2. MCP2515 (Arduino) <-> Arduino Uno  (bus SPI)

| MCP2515 | Arduino Uno |
|---------|-------------|
| VCC     | 5V          |
| GND     | GND         |
| CS      | D10         |
| SCK     | D13         |
| SI      | D11         |
| SO      | D12         |
| INT     | D2          |

## 3. Bus CAN entre les DEUX modules MCP2515

    MCP2515 Arduino                MCP2515 Raspberry
       CAN_H  ----------------------  CAN_H
       CAN_L  ----------------------  CAN_L

- Ne JAMAIS croiser CAN_H et CAN_L.
- 2 fils seulement, aussi courts que possible.

## 4. Resistances de terminaison 120 ohms

Le bus CAN exige une resistance 120 ohms a CHAQUE extremite.
Chaque module MCP2515 possede un cavalier (jumper) "J1" qui
active sa resistance interne.

  -> Les DEUX jumpers J1 doivent etre FERMES.

VERIFICATION AU MULTIMETRE (les 2 cartes hors tension) :
mesurer la resistance entre CAN_H et CAN_L.

  ~60 ohms   -> 2 terminaisons OK (60 = 120 // 120)
  ~120 ohms  -> une seule terminaison : fermer le 2e jumper
  infini     -> aucune terminaison : fermer les 2 jumpers

## 5. Quartz du MCP2515

Chaque module porte un quartz metallique avec une inscription :
  "8.000"  -> quartz 8 MHz
  "16.000" -> quartz 16 MHz

Cette valeur doit etre declaree de maniere coherente :
  - Raspberry : oscillator=8000000 ou 16000000 dans config.txt
  - Arduino   : MCP_8MHZ ou MCP_16MHZ dans arduino_can_tx.ino

Les deux modules peuvent avoir des quartz differents : chacun
se configure independamment avec SON propre quartz.
