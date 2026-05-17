# SSTV — Challenge CTF

Challenge de stéganographie audio où les participants doivent décoder un signal SSTV (Slow Scan Television) pour reconstituer une image contenant le flag.

---

## Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Fichiers du challenge](#fichiers-du-challenge)
3. [Générer le challenge](#générer-le-challenge)
4. [Ce qui est donné aux participants](#ce-qui-est-donné-aux-participants)
5. [Vérifier le challenge](#vérifier-le-challenge)
6. [Pistes d'exploration pour les challengers](#pistes-dexploration-pour-les-challengers)
7. [Contacts](#contacts)

---

## Vue d'ensemble

Le participant reçoit un fichier audio WAV. Ce fichier encode une image via le protocole **SSTV en mode Pasokon P3** — un format japonais très peu connu, peu supporté par les outils grand public. L'image décodée contient le flag.

**Niveau estimé :** medium/hard (identification du protocole + identification du mode)

**Durée estimée :** 1h–3h selon la familiarité avec le traitement du signal

---

## Fichiers du challenge

```
sstv/
├── sstv.png                  ← image source contenant le flag 
├── encode_pasokon_p3.py      ← encodeur : image → WAV Pasokon P3
├── decode_pasokon_p3.py      ← décodeur de référence 
├── output_p3.wav             ← fichier WAV à distribuer aux participants
└── decoded.png               ← vérification de décodage
```

---

## Générer le challenge

### Prérequis

```bash
pip install pillow numpy scipy
```

### Modifier le flag / l'image source

Remplacer `sstv.png` par n'importe quelle image PNG/JPG contenant le flag. Elle sera automatiquement redimensionnée en 640×496 à l'encodage.

### Encoder l'image en WAV

```bash
python3 encode_pasokon_p3.py sstv.png output_p3.wav
```

Durée du WAV généré : **~204 secondes (~3.4 min)**, 16 Mo environ.

### Vérifier que le décodage fonctionne

```bash
python3 decode_pasokon_p3.py output_p3.wav decoded.png
```

Ouvrir `decoded.png` et vérifier que le flag est lisible. Une légère dégradation (~20 dB PSNR) est normale et attendue — le texte du flag reste parfaitement lisible.

---

## Ce qui est donné aux participants

**Uniquement :** `output_p3.wav`

> *On a intercepté une transmission radio. Le fichier audio joint semble cacher quelque chose. À toi de le décoder.*

Ne rien dire sur SSTV, sur le mode, ni sur le format audio — c'est tout l'objet du challenge.

---

## Vérifier le challenge

### Durée et intégrité du WAV

```bash
python3 -c "
import wave
with wave.open('output_p3.wav') as w:
    dur = w.getnframes() / w.getframerate()
    print(f'Durée : {dur:.1f}s | Canaux : {w.getnchannels()} | Fréq. : {w.getframerate()} Hz')
"
```

Valeurs attendues : ~204s, 1 canal (mono), 44100 Hz.

### Décodage de référence

```bash
python3 decode_pasokon_p3.py output_p3.wav decoded.png
# → "decoded VIS = 113 (ok)"
# → ouvrir decoded.png et vérifier le flag
```

---

## Pistes d'exploration pour les challengers

Ce qui suit est une liste de pistes progressives — **à ne partager qu'en cas de blocage prolongé**, sous forme de hints discrets (Discord, système de hints du CTF).

### Hint 1 — Identification du type de fichier

Le fichier WAV est un audio mono 44100 Hz. L'ouvrir dans **Audacity** ou **Sonic Visualiser** révèle :
- une forme d'onde à amplitude quasi-constante → signal FM (pas un enregistrement naturel)
- un spectrogramme avec des bandes horizontales colorées → présence de fréquences discrètes qui changent lentement

Mots-clés à chercher : `audio steganography`, `FSK audio`, `image in audio`.

### Hint 2 — Identification de SSTV

En zoomant sur le début du signal dans Audacity, on distingue :
- ~300 ms de ton pur à ~1900 Hz (ton pilote)
- une courte coupure à ~1200 Hz
- à nouveau ~300 ms à 1900 Hz
- puis des bits à 1100/1300 Hz

Cette séquence est le **header VIS** (Vertical Interval Signaling) standard de l'SSTV. Mots-clés : `SSTV audio header`, `VIS SSTV`.

Outils à essayer : **MMSSTV** (Windows), **qsstv** (Linux), **RX-SSTV**.

### Hint 3 — Identification du mode

Les outils SSTV courants comme MMSSTV auto-détectent le mode via le code VIS. Le VIS code présent dans le signal est **113** — inconnu des modes classiques (Martin, Scottie, Robot). Il correspond au mode **Pasokon P3**, un format japonais. Dans MMSSTV, cocher `Options → RX → Pasokon` pour l'activer.

Alternativement, lire le VIS manuellement : les bits à 1100/1300 Hz après le header donnent `1 0 0 0 1 1 1` (LSB en premier) = 113 en décimal.

### Hint 4 — Décodage programmatique

Si les outils échouent, implémenter un décodeur :
1. Filtrer le signal entre 1050 et 2450 Hz (bande utile SSTV)
2. Extraire la fréquence instantanée (transformée de Hilbert)
3. Après le header (~0.91s), lire les lignes : sync 20ms + porch 2ms + R 128ms + sep + G + sep + B
4. Mapper la fréquence sur la luminosité : 1500 Hz → noir (0), 2300 Hz → blanc (255)

---

## Contacts

- Discord : Lanceløt
