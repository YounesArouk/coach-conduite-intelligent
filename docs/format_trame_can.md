# Format de la trame CAN

## Identifiant

  CAN ID : 0x100  (standard, 11 bits)
  Longueur : 8 octets (DLC = 8)

## Encodage des 8 parametres

Chaque parametre est compresse sur 1 octet (0-255) par mise a
l'echelle lineaire entre un minimum et un maximum.

| Octet | Parametre        | Plage reelle    | Unite   |
|-------|------------------|-----------------|---------|
| 0     | vitesse          | 0 .. 180        | km/h    |
| 1     | acceleration     | -8 .. +5        | m/s2    |
| 2     | freinage         | 0 .. 100        | %       |
| 3     | regime_moteur    | 700 .. 6500     | tr/min  |
| 4     | niveau_carburant | 0 .. 100        | %       |
| 5     | temp_moteur      | 70 .. 115       | degC    |
| 6     | angle_volant     | -180 .. +180    | deg     |
| 7     | conso_instant    | 0 .. 25         | L/100km |

## Formule d'encodage (cote Arduino)

  octet = (valeur - mini) * 255 / (maxi - mini)

## Formule de decodage (cote Raspberry)

  valeur = mini + (octet / 255) * (maxi - mini)

## Important

Les plages (mini, maxi) doivent etre RIGOUREUSEMENT IDENTIQUES
des deux cotes :
  - Arduino  : fonction encoder() dans arduino_can_tx.ino
  - Raspberry: liste CHAMPS / PLAGES dans coach_gui_can.py

Si une plage est modifiee d'un cote, elle doit l'etre de l'autre,
sinon les valeurs decodees seront fausses.

## Precision

L'encodage sur 1 octet introduit une erreur de quantification
maximale d'environ 0,4 % de la plage. C'est negligeable pour le
modele IA (teste et valide).

## Exemple

Valeurs : vitesse=82.4 accel=1.54 frein=36.8 regime=3827
          carb=71.1 temp=86.4 volant=-66 conso=14.18

Trame CAN resultante (hexadecimal) :
  100#75BB5E89B55D5191
