# Cahier des charges — Module Abonnement & Paiement (PredictX)

## 1. Contexte

Le site affiche un **coupon du jour** (sélection des pronostics les plus fiables). Les **résultats** des pronostics passés sont visibles par tout le monde, abonnés comme non-abonnés — c'est le **détail des marchés du jour** (1X2, plus/moins de buts, double chance, GG) qui est réservé aux abonnés.

## 2. Parcours utilisateur (visiteur non abonné)

1. Le visiteur arrive sur le site, voit le coupon du jour (aperçu) et peut consulter librement l'historique des résultats.
2. Il clique sur **"S'abonner"**.
3. Un choix de formule s'affiche :
   - **Semaine — 1000 FCFA**
   - **Mois — 4000 FCFA**
   - **Année — 10 000 FCFA**
4. Dès qu'il **sélectionne une formule**, il est redirigé automatiquement vers WhatsApp, sur le numéro professionnel :
   **+229 01 40 30 54 83**
   (le message pré-rempli peut indiquer la formule choisie, pour que l'admin sache directement quoi débloquer)
5. Le visiteur discute avec l'admin (toi) sur WhatsApp, effectue le paiement (Fedapay / Mobile Money), et attend le déblocage.

## 3. Parcours admin (toi)

1. Tu reçois le message WhatsApp avec le nom de l'utilisateur et la formule demandée.
2. Une fois le paiement confirmé, tu te rends sur la **page base de données** (protégée par mot de passe, connu de toi seul).
3. Tu recherches l'utilisateur par son nom dans la liste.
4. À côté de chaque nom, trois boutons sont disponibles : **[Semaine] [Mois] [Année]**.
5. Tu cliques sur le bouton correspondant à la formule payée.
6. Le système :
   - enregistre la date de début et calcule automatiquement la **date d'expiration** selon la formule choisie (7 jours / 30 jours / 365 jours)
   - marque le compte comme **abonné actif**

## 4. Côté utilisateur après déblocage

- Dès que l'utilisateur **actualise la page** du site, il voit automatiquement :
  - le détail complet des marchés du coupon du jour (1X2, plus/moins, double chance, GG)
  - toutes les fonctionnalités réservées aux abonnés
- Aucune action supplémentaire n'est nécessaire de son côté : le déblocage est **instantané dès l'actualisation**, sans rechargement de page spécial ni reconnexion.

## 5. Expiration de l'abonnement

- Un script vérifie automatiquement (quotidiennement) la date d'expiration de chaque abonné.
- Dès que la date est dépassée :
  - le compte repasse automatiquement en statut **non-abonné**
  - l'utilisateur perd l'accès au détail des marchés (mais garde l'accès aux résultats, comme tout visiteur)
- Pour renouveler, l'utilisateur reprend le même parcours (clic "S'abonner" → choix formule → WhatsApp → déblocage admin).

## 6. Règles importantes

| Élément | Accès visiteur (non abonné) | Accès abonné |
|---|---|---|
| Coupon du jour (aperçu) | ✅ | ✅ |
| Détail des marchés (1X2, +/- buts, double chance, GG) | ❌ | ✅ |
| Historique des résultats (gagnant/perdant) | ✅ | ✅ |
| Contact/abonnement | ✅ (redirection WhatsApp) | — |

## 7. Éléments techniques à prévoir (backend)

- Table `users` avec champs : nom, statut abonnement (actif/inactif), date de début, date d'expiration, formule choisie
- Page admin protégée par mot de passe (`.env`), avec recherche par nom + 3 boutons d'action (semaine/mois/année)
- Logique de calcul automatique de la date d'expiration selon le bouton cliqué
- Tâche planifiée quotidienne (cron / script `.cmd` déjà en place dans le projet) qui vérifie les expirations et repasse les comptes expirés en "non-abonné"
- Endpoint API qui renvoie le statut abonné/non-abonné de l'utilisateur connecté, vérifié à chaque chargement de page (pour le déblocage instantané à l'actualisation)
- Lien WhatsApp dynamique généré au clic sur une formule : `https://wa.me/22901403054083?text=...` avec message pré-rempli mentionnant la formule choisie
