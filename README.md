# FISHWATCH — veille pêche gratuite en Python
## 3. Comment fonctionne le tri

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
