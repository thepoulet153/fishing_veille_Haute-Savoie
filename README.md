# FISHWATCH — veille pêche gratuite en Python

**Projet pédagogique entièrement gratuit** (hors éventuels coûts de connexion ou de services tiers si tu en ajoutes). Aucun abonnement, clé d'API ou modèle d'intelligence artificielle n'est requis.

Il reprend l'architecture du cours de veille (PIR, sources, requêtes, collecte, cotation, scoring, restitution et validation humaine). **Il ne contient pas d'IA** : l'analyse automatique consiste en des règles Python explicites. Si le professeur exige de l'IA dans le workflow, documente cette limite et ajoute une étape de relecture ponctuelle assistée par ChatGPT, sans prétendre que le script est de l'IA.

## 1. Commencer sur ton PC (5 minutes)

1. Installe **Python 3.10 ou plus récent** depuis https://www.python.org/downloads/ (sur Windows, coche « Add Python to PATH » si proposé).
2. Décompresse tout le ZIP dans un dossier (conserve les sous-dossiers `.github`, `config`, `data`, `examples`, `tests`).
3. Ouvre un terminal dans le dossier `FISHWATCH_Python_gratuit`.
4. Lance `python collect.py` sur Windows (ou `python3 collect.py` sur macOS/Linux).
5. Lance `python -m http.server 8000` (sur macOS/Linux, `python3 -m http.server 8000`).
6. Ouvre **http://localhost:8000** dans ton navigateur.

Sur Windows, tu peux aussi double-cliquer sur `lancer_windows.bat` si la commande `py` est disponible. Ce raccourci lance la collecte, puis le petit serveur local.

Le site **n'est pas mis à jour par un double-clic isolé sur `index.html`** : le navigateur ne peut pas lire automatiquement le fichier `veille.json` depuis une page ouverte en `file://`. Le petit serveur local règle cela. Tu peux néanmoins importer manuellement `veille.json` depuis le dashboard.

**Premier lancement :** les six requêtes Google Actualités sont interrogées, les éléments pertinents des 45 derniers jours sont dédupliqués, et `veille.json` est créé. Il peut y avoir peu d'articles si les requêtes sont trop strictes. La surveillance de page enregistre simplement une première empreinte de référence (aucune alerte n'est créée à ce moment-là).

**Démo si Internet ne fonctionne pas :** utilise « Importer JSON » dans le dashboard et sélectionne `examples/veille_demo.json`. Ce fichier contient uniquement des scénarios fictifs indiqués comme tels. Pour revenir aux données de collecte, clique « Importer JSON » avec le fichier `veille.json`, ou « Actualiser » si tu es en mode serveur local.

## 2. Automatiser gratuitement avec GitHub (PC éteint)

1. Crée un compte gratuit sur https://github.com si tu n'en as pas.
2. Installe **GitHub Desktop** https://desktop.github.com/ (plus simple qu'une ligne de commande Git).
3. Dans GitHub Desktop, choisis *File > Add local repository* et sélectionne ton dossier projet. Si le logiciel propose de **créer un dépôt ici**, accepte.
4. Fais un premier commit, puis *Publish repository*. Choisis un **dépôt public** si tu veux utiliser gratuitement GitHub Pages sans configuration supplémentaire.
5. Sur GitHub, ouvre **Actions > Veille pêche gratuite > Run workflow** (la première exécution peut demander d'activer les Actions du dépôt).
6. Ouvre **Settings > Pages > Build and deployment > Deploy from a branch** puis sélectionne `main` et `/ (root)` et enregistre.
7. Une fois la publication terminée, ton URL ressemble à `https://TON-PSEUDO.github.io/NOM-DU-DEPOT/`.

Le fichier `.github/workflows/veille.yml` lance automatiquement les tests et la collecte environ **toutes les 6 heures**, sans que ton PC reste allumé. Le script conserve les articles déjà trouvés et empêche leur duplication. La page charge `veille.json` automatiquement au démarrage, et le bouton « Actualiser » le recharge.

**Si GitHub Actions indique `Permission denied` au moment du `git push` :** ouvre *Settings > Actions > General > Workflow permissions* et autorise *Read and write permissions* si ton dépôt le permet. Le workflow demande déjà `contents: write`, mais la politique du dépôt peut rester restrictive.

**Attention :** les Actions programmées peuvent démarrer en retard, ou être désactivées sur un dépôt public après 60 jours sans activité (réactivation manuelle possible). Le tableau de bord et les articles seront publics sur GitHub Pages. Ne publie aucun secret ni données personnelles.

## 3. Comment fonctionne le tri (100 % transparent)

Le programme suit six recherches RSS stockées dans `config/sources.json` : **deux par PIR**.

| PIR | Objectif | Déclencheurs types |
|---|---|---|
| PIR-1 | Réglementation | arrêté, consultation, interdiction, fermeture |
| PIR-2 | Environnement | sécheresse, étiage, débit, crue |
| PIR-3 | Santé piscicole | pollution, mortalité, maladie, étude |

Le filtre exige un **lien géographique** avec la Haute-Savoie et un **contexte aquatique**. Il élimine certaines publicités, les doublons et les publications de plus de 45 jours.

La grille de score est celle du cours :

- +3 : répond à une PIR ;
- +3 : déclenche un indicateur défini ;
- +2 : concerne le périmètre du commanditaire ;
- +1 : source primaire ou source préqualifiée A/B ;
- +1 : nouvelle information non doublonnée.

Le dashboard affiche les éléments à **7–10 comme signaux prioritaires à vérifier**, ceux à **4–6 comme à analyser**, et les autres comme rejetés. **Le score mesure la pertinence, pas la fiabilité ni l'urgence réelle.** Le tri est volontairement conservateur sur les articles hors périmètre, mais il reste imparfait. Les critères sont modifiables dans `collect.py` et `config/sources.json`.

La cote `A6`, `B6` ou `F6` est *provisoire* : première lettre = évaluation initiale de la **fiabilité du site éditeur** (A, B ou non évaluable F), chiffre 6 = **crédibilité du fait non évaluée**. La collecte ne vérifie jamais automatiquement qu'un arrêté a été adopté ou qu'un signalement de pollution est vrai.

Google Actualités sert à **repérer** une publication, non de preuve primaire : suivre le lien et remonter au texte original. Un flux RSS n'expose souvent qu'un extrait ; aucun résumé automatique inventé n'est produit.

## 4. Sonde Python de changement de page

Dans `config/sources.json`, la page officielle de la préfecture relative à la pêche est surveillée (champ `website_monitors`).

- Première exécution : prise d'une empreinte du contenu HTML principal `<main>` ; **aucune alerte**.
- À partir de la deuxième : si le contenu principal change, une fiche **« Modification de page à vérifier »** est ajoutée à la catégorie PIR-1 (score 5, révision humaine obligatoire).
- S'il n'y a pas de bloc `<main>` stable, la sonde se met en erreur : cela est indiqué dans les logs et dans `veille.json` plutôt que d'affirmer une modification.

Cela reproduit le *principe* d'une sonde Distill, mais avec moins de précision. Une modification d'un menu ou d'un bandeau peut produire un faux positif. Les pages officielles peuvent changer de structure ; vérifier que les URL correspondent aux bonnes rubriques.

## 5. Fichiers du projet

```
FISHWATCH_Python_gratuit/
├── index.html                      # dashboard autonome
├── collect.py                      # collecte, tri, scoring, dédoublonnage, sonde
├── veille.json                      # données réelles (vide avant lancement)
├── config/sources.json            # deux requêtes Google News par PIR + page surveillée
├── data/monitor_state.json        # empreinte de la page surveillée
├── examples/veille_demo.json      # données FICTIVES pour démonstration
├── tests/test_collect.py          # tests hors ligne
├── .github/workflows/veille.yml   # exécution toutes les six heures
├── lancer_windows.bat             # raccourci local Windows
└── README.md
```

Tests : `python -m unittest discover -s tests -v`.

**Comment présenter le projet à l'oral :** explique d'abord les trois PIR et leurs indicateurs, puis les sources et les requêtes, puis le diagramme « RSS → Python → score → JSON → HTML → validation humaine », et enfin une fiche sourcée et son statut « non vérifié ». La matrice ACH du dashboard est une **simulation** ; il faut l'alimenter en preuves réelles cotées pour en tirer une conclusion.

## 6. Limites et améliorations

- La collecte se base principalement sur Google Actualités : elle **ne remplace pas** la lecture directe des sources institutionnelles ; certaines publications ne sont pas indexées.
- Le classement lexical ne comprend pas réellement le contexte : faux positifs et faux négatifs possibles. Réviser les rejets chaque semaine ; garder un journal du bruit.
- Les validations humaines faites dans le dashboard sont **locales à ton navigateur**, non synchronisées sur GitHub. Tu peux les exporter en JSON ; ne les présente pas comme un circuit multi-utilisateurs.
- Sans IA, le projet remplit la partie **automatisation de veille** du cours, mais **pas** littéralement la partie « veille avec IA ». Pour ce dernier point, l'IA peut intervenir comme relecteur/contradicteur ponctuel, avec sources fournies et vérification humaine, sans API ni modèle local.
