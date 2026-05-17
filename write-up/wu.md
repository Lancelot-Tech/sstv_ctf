# Write-up — SSTV Pasokon P3

**Flag :** `HSR{ThIs_iS_S0_Aw3som3}`

---

## Contexte

On reçoit un fichier `output_p3.wav` — un audio mono 44 kHz. Rien d'autre. L'objectif est d'en extraire une image contenant le flag.

---

## Étape 1 — Analyser le signal audio

Ouvrir le fichier dans **Audacity** (ou n'importe quel éditeur audio).

**Forme d'onde :** amplitude quasi constante sur toute la durée (~3.4 min). Ce n'est pas un enregistrement naturel — c'est un signal **FM** (Frequency Modulation) : l'information est dans la fréquence, pas dans l'amplitude.

**Spectrogramme** (`Analyze → Plot Spectrum` ou `View → Spectrogram`) : on observe des bandes horizontales étroites qui changent lentement dans la plage 1500–2300 Hz. Ce motif est caractéristique d'un signal qui encode des valeurs continues — typiquement de la vidéo ou de l'image.

**Début du signal :** en zoomant sur les 2 premières secondes, on voit distinctement :
- un ton stable à ~1900 Hz pendant 300 ms
- une cassure brève à ~1200 Hz (10 ms)
- à nouveau 1900 Hz pendant 300 ms
- puis des petits segments alternant 1100 Hz / 1300 Hz

Cette séquence est un marqueur standardisé : c'est un **header VIS SSTV**.

---

## Qu'est-ce que l'SSTV ?

**SSTV (Slow Scan Television)** est un protocole de transmission d'images via radio ou audio, inventé dans les années 1950 et toujours utilisé par les radioamateurs. Contrairement à la télévision classique (25 images/s), l'SSTV transmet une image fixe en plusieurs dizaines de secondes à quelques minutes.

Le principe : encoder la luminosité de chaque pixel comme une **fréquence audio**.

```
pixel noir  (valeur 0)   → 1500 Hz
pixel blanc (valeur 255) → 2300 Hz
entre les deux           → interpolation linéaire
```

La formule exacte :

```
f(v) = 1500 + 800 × (v / 255)    [Hz]
```

Le signal obtenu est un signal FM où la fréquence instantanée encode la luminosité pixel par pixel, ligne par ligne.

---

## Étape 2 — Décoder le header VIS

Le header VIS (Vertical Interval Signaling) est une séquence de bits qui identifie le **mode SSTV** (résolution, nombre de canaux couleur, durée par ligne…). C'est le même standard pour tous les modes SSTV depuis les années 1990.

### Structure du header

```
[Leader 300ms @ 1900 Hz]
[Break   10ms @ 1200 Hz]
[Leader 300ms @ 1900 Hz]
[Start   30ms @ 1200 Hz]   ← marque le début du code
[Bit 0   30ms @ 1100/1300 Hz]   \
[Bit 1   30ms @ 1100/1300 Hz]    |
[Bit 2   30ms @ 1100/1300 Hz]    | 7 bits de données (LSB en premier)
[Bit 3   30ms @ 1100/1300 Hz]    |   1100 Hz = 1
[Bit 4   30ms @ 1100/1300 Hz]    |   1300 Hz = 0
[Bit 5   30ms @ 1100/1300 Hz]    |
[Bit 6   30ms @ 1100/1300 Hz]   /
[Parité  30ms @ 1100/1300 Hz]   ← parité paire
[Stop    30ms @ 1200 Hz]        ← fin du header
```

### Lire le code VIS

En mesurant les fréquences des 7 bits de données dans le signal :

| Bit | Fréquence | Valeur |
|-----|-----------|--------|
| 0   | 1100 Hz   | 1      |
| 1   | 1300 Hz   | 0      |
| 2   | 1300 Hz   | 0      |
| 3   | 1300 Hz   | 0      |
| 4   | 1100 Hz   | 1      |
| 5   | 1100 Hz   | 1      |
| 6   | 1100 Hz   | 1      |

VIS code = `1 + 0×2 + 0×4 + 0×8 + 1×16 + 1×32 + 1×64` = **113**

Le code 113 ne correspond à aucun des modes courants (Martin M1 = 44, Scottie S1 = 60, Robot 36 = 8, PD120 = 95…). Une recherche dans les tables de référence SSTV révèle : **Pasokon P3**, un format japonais peu documenté hors du Japon.

---

## Étape 3 — Comprendre le mode Pasokon P3

### Paramètres

| Paramètre | Valeur |
|-----------|--------|
| VIS code  | 113    |
| Résolution | 640 × 496 px |
| Couleurs | RGB (3 passes par ligne) |
| Sync de ligne | 20 ms @ 1200 Hz |
| Porch | 2.08 ms @ 1500 Hz |
| Scan par canal | 128.458 ms (640 px × ~0.2007 ms/px) |
| Séparateur R→G, G→B | 1.04 ms @ 1500 Hz |
| Durée totale par ligne | ~409.5 ms |
| Durée totale image | ~203 s (~3.4 min) |

### Structure d'une ligne

```
│←── 20 ms ──→│← 2ms →│←────── 128.5 ms ──────→│← 1ms →│←── 128.5 ms ──→│← 1ms →│←── 128.5 ms ──→│
│  SYNC 1200Hz │ PORCH │       Canal R            │  SEP  │    Canal G      │  SEP  │    Canal B      │
               │ 1500Hz│  (640 pixels, FM 1500-2300Hz)    │                 │       │                 │
```

Chaque canal (R, G, B) est scanné séparément pour chaque ligne. Pour chaque pixel, la fréquence audio encode la valeur du canal.

---

## Étape 4 — Démodulation FM : la physique

Pour retrouver les pixels, il faut inverser la modulation FM : extraire la **fréquence instantanée** du signal audio.

### Définition

Un signal FM s'écrit :

```
x(t) = A · sin(φ(t))

avec φ(t) = 2π ∫ f(τ) dτ
```

La fréquence instantanée est la dérivée de la phase :

```
fᵢ(t) = (1/2π) · dφ/dt
```

### La transformée de Hilbert

Pour extraire φ(t) à partir de x(t), on utilise le **signal analytique** :

```
z(t) = x(t) + j · H{x(t)}
```

où H{·} est la transformée de Hilbert — elle décale la phase de chaque composante fréquentielle de −π/2, sans changer son amplitude. Le signal analytique a une représentation polaire :

```
z(t) = A(t) · e^(jφ(t))
```

On en déduit directement la phase instantanée :

```
φ(t) = arg(z(t)) = arctan( Im(z(t)) / Re(z(t)) )
```

Puis la fréquence instantanée (après déroulement de phase pour éviter les sauts de 2π) :

```
fᵢ(t) ≈ (1/2π) · Δφ / Δt = (fₛ / 2π) · (φ[n+1] − φ[n])
```

avec fₛ = 44100 Hz la fréquence d'échantillonnage.

En pratique, la transformée de Hilbert se calcule efficacement via FFT :

```python
from scipy.signal import hilbert
import numpy as np

analytic = hilbert(signal)          # z(t) = x(t) + j·H{x(t)}
phase    = np.unwrap(np.angle(analytic))  # φ(t), déroulée
freq     = np.diff(phase) * 44100 / (2 * np.pi)  # fᵢ(t) en Hz
```

### Du tableau de fréquences à l'image

Une fois `freq[n]` calculé, chaque sample est associé à une fréquence. On groupe les samples par pixel (640 pixels sur 128.458 ms = ~8.85 samples/pixel à 44100 Hz), on prend la valeur centrale de chaque groupe (médiane, pour éviter le ringing aux frontières de pixels), puis on applique la transformation inverse :

```
v = clip( (fᵢ − 1500) / 800 × 255 , 0, 255 )
```

### Limitation intrinsèque : le ringing de Hilbert

Aux frontières entre deux pixels, la fréquence change abruptement (fonction échelon). La transformée de Hilbert n'est pas causale — elle voit le signal dans les deux sens — et produit du **ringing** autour de ces discontinuités, sur quelques échantillons de part et d'autre de la frontière. Avec ~9 samples/pixel, 1–2 samples pollués par pixel représentent une erreur systématique de quelques unités sur 255. C'est la limite fondamentale de ce démodulateur pour l'SSTV.

En pratique : ~20 dB PSNR, erreur moyenne ~6/255 — parfaitement lisible visuellement.

---

## Étape 5 — Implémentation

### Option A — Outils graphiques

**MMSSTV** (Windows) supporte Pasokon P3 mais il faut l'activer manuellement :
`Options → RX → cocher Pasokon (P3/P5/P7)`

Charger le WAV via `File → Open`, laisser MMSSTV décoder en temps réel.

**qsstv** (Linux) supporte également Pasokon. Compiler depuis les sources ou via le dépôt de la distribution.

### Option B — Script Python

Les grandes étapes :

```python
from scipy.signal import hilbert, butter, sosfilt
import numpy as np, wave
from PIL import Image

# 1. Charger le WAV
with wave.open("output_p3.wav") as wf:
    raw = wf.readframes(wf.getnframes())
signal = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0

# 2. Filtrer (bande SSTV : 1050–2450 Hz)
sos = butter(5, [1050, 2450], btype="band", fs=44100, output="sos")
filtered = sosfilt(sos, signal)

# 3. Fréquence instantanée
analytic = hilbert(filtered)
phase    = np.unwrap(np.angle(analytic))
freq     = np.diff(phase) * 44100 / (2 * np.pi)

# 4. Localiser le header VIS (~0.91s depuis le début)
#    → trouver la première plage de fréquence ~1900 Hz ≥ 200 ms

# 5. Pour chaque ligne i = 0..495 :
#    - position nominale : vis_end + i × 18059 samples  (~409.5 ms)
#    - trouver le sync (1200 Hz, 20 ms) près de cette position
#    - décoder R à sync + 22.1ms, G à R + 129.5ms, B à G + 129.5ms
#    - pour chaque canal : moyenner sur les ~8.85 samples de chaque pixel
#    - convertir : pixel = (freq - 1500) / 800 * 255

# 6. Sauvegarder l'image
img = Image.fromarray(image_array, "RGB")
img.save("flag.png")
```

Le décodeur complet est fourni dans `decode_pasokon_p3.py`.

---

## Flag

```
HSR{ThIs_iS_S0_Aw3som3}
```

---

## Ce qui rend ce challenge difficile

| Obstacle | Pourquoi |
|----------|----------|
| Signal FM à amplitude constante | On n'identifie pas immédiatement une image cachée |
| SSTV peu connu | Les outils de stégano classiques (stegsolve, binwalk…) ne le détectent pas |
| Mode Pasokon P3 (VIS 113) | Absent de la plupart des cheat sheets CTF ; non supporté par défaut dans la majorité des outils |
| Durée de 3.4 min | On ne sait pas combien de temps attendre si on écoute à l'oreille |
| Décodage programmatique | Nécessite de comprendre la démodulation FM et la transformée de Hilbert |
