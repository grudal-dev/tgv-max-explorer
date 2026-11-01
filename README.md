# 🚄 TGV MAX Explorer

Toutes les places **MAX JEUNE / MAX SENIOR** disponibles sur une carte de France.
Choisis une date et une gare de départ : la carte affiche toutes les destinations
accessibles, avec horaires et temps de trajet.

Données : open data SNCF, jeu [« tgvmax »](https://ressources.data.sncf.com/explore/dataset/tgvmax/)
(30 jours glissants, mis à jour chaque matin, licence ODbL).

## Fonctionnalités

- **Carte interactive** (Leaflet) : vue d'ensemble des gares, puis toutes les destinations
  depuis une gare, avec la durée du trajet le plus rapide. Survol carte ↔ liste synchronisé.
- **Recherche** par date (‹ › pour changer de jour), départ, arrivée, heure, durée max.
  Mise à jour instantanée sans rechargement (HTMX).
- **Trajets avec 1 correspondance** quand il n'y a pas de direct (temps en gare entre 20 min et 2 h,
  réglable).
- **Week-end aller-retour** : seulement les villes où un aller **et** un retour MAX sont dispo.
  Raccourcis Ven → Dim, Sam → Dim, Ven → Lun, aller-retour dans la journée.
- **Alertes e-mail** : surveille un trajet complet et reçois un e-mail dès qu'une place se libère.
  Un e-mail par nouveau train, lien de désactivation inclus.
- Admin Django pour corriger les coordonnées des gares et consulter les synchronisations.

## Installation

Prérequis : Python 3.11+.

```bash
git clone https://github.com/grudal-dev/tgv-max-explorer.git
cd tgv-max-explorer
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optionnel
python manage.py migrate
python manage.py sync_tgvmax       # télécharge les données SNCF (~1 min)
python manage.py runserver
```

Puis ouvre http://127.0.0.1:8000.

Pas de connexion, ou envie de tester vite ? `python manage.py load_demo_data` charge un réseau
fictif mais réaliste sur 30 jours.

## Commandes

| Commande | Rôle |
|---|---|
| `sync_tgvmax` | Importe les données SNCF puis envoie les alertes. Options : `--days N`, `--file export.json`, `--no-alerts` |
| `check_alerts` | Envoie les alertes sans resynchroniser (`--dry-run` pour simuler) |
| `geocode_stations` | Ajoute les coordonnées manquantes (table intégrée puis référentiel des gares SNCF) |
| `load_demo_data` | Données de démonstration (`--reset`, `--days`, `--seed`) |
| `createsuperuser` | Crée un compte pour l'admin (`/admin/`) |

### Synchronisation automatique

La SNCF met le jeu à jour tôt le matin. Une synchro par jour suffit pour la carte. Pour les
alertes, deux synchros par jour donnent une meilleure réactivité.

- **macOS / Linux** (`crontab -e`) :
  ```
  15 7,13 * * * cd /chemin/tgv-max-explorer && .venv/bin/python manage.py sync_tgvmax >> sync.log 2>&1
  ```
- **Windows** : Planificateur de tâches → action `C:\chemin\.venv\Scripts\python.exe`,
  arguments `manage.py sync_tgvmax`, dossier de départ `C:\chemin\tgv-max-explorer`.

### Alertes e-mail

Sans configuration, les e-mails s'affichent dans la console (pratique en local). Pour un vrai envoi,
renseigne `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` dans `.env` (voir `.env.example`).
Avec Gmail, il faut un [mot de passe d'application](https://myaccount.google.com/apppasswords).

## Architecture

```
config/                 réglages Django (variables d'environnement via .env)
trains/
  models.py             Station, Trip, SyncRun, Alert
  services/
    sncf.py             client de l'API open data SNCF (export JSON)
    sync.py             import idempotent (bulk create/update, suppression des trajets passés)
    search.py           directs, correspondances, allers-retours
    alerts.py           envoi des alertes
    geo.py              coordonnées des gares + normalisation des noms
  management/commands/  sync_tgvmax, check_alerts, geocode_stations, load_demo_data
  templates/trains/     pages + partiels HTMX
  static/trains/        app.css, app.js, Leaflet et HTMX intégrés (aucun CDN requis)
  tests/                tests unitaires et de vues
```

Pourquoi importer en base au lieu d'appeler l'API à chaque clic ? Les recherches sont instantanées,
les correspondances et allers-retours se calculent facilement, et on peut détecter quand un train
complet redevient disponible (alertes).

## Tests

```bash
python manage.py test trains
```

## Limites connues

- Une place affichée a pu partir depuis la dernière mise à jour SNCF : vérifie toujours sur SNCF Connect.
- Le jeu TGVmax ne contient pas de coordonnées : elles viennent d'une table intégrée (~200 gares).
  Les gares inconnues apparaissent dans les listes mais pas sur la carte. Lance `geocode_stations`
  ou complète-les dans l'admin.

Projet non affilié à la SNCF. Fonds de carte © OpenStreetMap, © CARTO.
