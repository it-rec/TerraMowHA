# TerraMow pour Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="Logo TerraMow" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · **Français** · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Ceci est une intégration Home Assistant pour les robots tondeuses TerraMow.

### Fonctionnalités

**Commande**
- Entité tondeuse : démarrer, mettre en pause et retourner à la base
- Tonte par zone : entité de sélection de zone et service `terramow.start_select_region`
- **Modification du planning** — les services `terramow.add_schedule` / `terramow.delete_schedule` écrivent des créneaux de tonte hebdomadaires sur la tondeuse et les vérifient par relecture. *Remarque :* le micrologiciel commercial actuel n'accepte pas encore l'écriture du planning via MQTT local (l'application du fabricant utilise Bluetooth/cloud) — en attendant, utilisez le **blueprint de tonte adaptée à la météo** pour planifier côté HA
- **Carte interactive** — carte vectorielle de la pelouse avec déplacement/zoom pour les tableaux de bord : position en direct du robot (teintée selon l'activité, avec mode suivi), commandes démarrer / pause / base directement sur la carte, pastilles batterie / progression / temps restant, ombrage de la surface tondue avec progression par zone, trajet de tonte, station de base, zones avec sélection par appui pour tondre, zones interdites et murs virtuels, défauts actifs épinglés à leur emplacement, et une **carte de chaleur Wi-Fi** de la pelouse ; un **bouton de vue** fait défiler Les deux / Trajet / Surface / Wi-Fi. Compatible avec les thèmes, auto-enregistrée, avec un éditeur d'interface (`custom:terramow-map-card`)
- Bouton de tonte des bordures
- Réglages depuis Home Assistant : hauteur de coupe, vitesse, espacement, vitesse de lame, distance de coupe de bordure, mode et angles de direction principale, coupe soignée des angles, mode de tonte de bordure pour herbe haute
- Entretien : boutons de réinitialisation des compteurs du disque de lame et de la station de base

**Surveillance**
- Caméra de carte en direct avec trajet de tonte, position du robot et station de base (plus une caméra « carte seule » épurée pour les tableaux de bord, résolution configurable dans les options)
- Batterie : niveau, état de charge, état de température, chargeur connecté, interrupteur d'alimentation
- Progression : surface de la session en cours, progression (%), durée et type de tâche ; temps de tonte cumulé, nombre de tâches et surface tondue
- État : mission / sous-mission / état de mission, mode de fonctionnement, mode d'alimentation, motif du retour à la station, détection de pluie, indicateur de problème, indicateurs d'enregistrement et de conversion des données
- **Capteur de défaut** — le défaut actif sous forme de texte lisible (par ex. *Tondeuse bloquée*, *Tondeuse soulevée* ou *OK*), pour qu'une notification ou un assistant vocal puisse dire ce qui ne va pas sans exploiter un attribut via un modèle
- Capteur de tâche en cours (conserve la mission active malgré les interruptions du signal de présence) et capteur de puissance du signal Wi-Fi côté tondeuse
- Carte : état, surface, indicateurs détectée / constructible / sauvegarde en cours
- Planning : capteur du prochain départ programmé et **calendrier du planning de tonte** en lecture seule (la prochaine tonte apparaît sur la carte calendrier)
- Entité de mise à jour du micrologiciel, version du micrologiciel sur la page de l'appareil et capteur de compatibilité de version
- Toutes les entités se mettent à jour instantanément lors des envois de l'appareil — aucun délai d'interrogation

**Diagnostics avancés** (points de données obtenus par ingénierie inverse — principalement dans la catégorie d'entité *Diagnostic*, beaucoup désactivés par défaut ; voir les [notes sur les points de données non officiels](en/developers/data_point_unofficial.md))
- Erreurs et événements : nombre d'erreurs actives (avec la liste brute des erreurs en attribut) et code du dernier événement. Les codes d'erreur connus sont traduits en texte lisible via un catalogue alimenté par la communauté (`error_codes.py`), qui décode aussi le dernier code d'erreur de la tondeuse (dp_115)
- Cellulaire / 4G : modem activé, puissance du signal (RSRP / RSRQ), type de connexion et un relevé *forcer le réseau cellulaire*
- Environnement : lever / coucher du soleil rapportés par l'appareil, état de lumière du jour, chauffage antibuée, éclairage et alerte météo extrême (avec une URL d'information optionnelle)
- Sécurité et réglages avancés : état de la détection de vide et de pente, seuil du capteur de pluie, reprise automatique après la pluie et son délai, et un relevé *forcer une station de base unique*
- Modes de fonctionnement : chaînes des modes déplacement / carte / tonte
- Cartographie et progression : indicateurs d'aide à la cartographie manuelle (repositionnement / reprise nécessaire, périmètre fermé) et pourcentage de progression de l'enregistrement de la carte

**Événements et automatisations**
- **Entité d'événement de la tondeuse** — déclenche un événement distinct à chaque transition notable (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), chacun portant les champs bruts de la mission, pour que les automatisations réagissent aux *faits* sans interroger l'état d'activité
- Blueprints d'automatisation importables en un clic (voir ci-dessous)

**Confort d'utilisation de l'intégration**
- Découverte automatique via Zeroconf/mDNS
- Flux de reconfiguration (changer l'hôte/IP sans réinstaller) et flux de réauthentification
- **Signalements de réparation** — cartes de tableau de bord exploitables pour un micrologiciel incompatible et pour l'entretien dû de la lame / de la station de base
- Téléchargement des diagnostics pour faciliter les rapports de bug
- Traduit en 33 langues (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Commandes confirmées** — la tonte par zone attend l'accusé de réception dp_119 de l'appareil et signale les rejets au lieu de « réussir » silencieusement
- Communication locale en push basée sur MQTT — aucun cloud requis

### Entités prises en charge

| Plateforme | Entités |
| --- | --- |
| Tondeuse | Commande démarrer / pause / base avec activité en direct |
| Caméra | Carte avec trajet, robot et station de base ; variante épurée « carte seule » |
| Capteur | Niveau de batterie, état de la batterie, état de température de la batterie, état de la carte, surface de la carte, hauteur de coupe, vitesse de tonte, mode de fonctionnement, position, temps de tonte / tâches / surface tondue cumulés, surface / progression / durée / type de tâche de la session en cours, tâche en cours, défaut, temps restant pour la lame et la station de base, prochain départ programmé, compatibilité de version, état de la direction principale, mode d'alimentation, motif du retour à la station, mission, sous-mission, état de mission. *Diagnostic :* erreurs actives, dernier événement, signal Wi-Fi, cellulaire RSRP / RSRQ / type, lever du soleil, coucher du soleil, modes déplacement / carte / tonte, seuil du capteur de pluie, délai de reprise après la pluie, progression de l'enregistrement de la carte |
| Capteur binaire | En charge, navigation localisée, mise à jour du micrologiciel en cours, interrupteur d'alimentation, problème, pluie détectée, carte détectée / constructible / sauvegarde en cours, enregistrement des données, conversion des données en cours. *Diagnostic :* cellulaire activé, chauffage antibuée, éclairage, lumière du jour, météo extrême, détection de vide / de pente, reprise automatique après la pluie, forcer une station de base unique, forcer le réseau cellulaire, cartographie manuelle repositionnement / reprise / périmètre fermé, indicateur d'état 134 (non décodé) |
| Sélection | Sélection de zone, vitesse de tonte, vitesse de lame, mode de direction principale, mode de tonte de bordure pour herbe haute |
| Nombre | Hauteur de coupe, distance de coupe de bordure, espacement de tonte, angle de direction unique, intervalle de rotation automatique de l'angle, angle de la première / deuxième direction |
| Interrupteur | Coupe soignée des angles |
| Bouton | Tonte des bordures, réinitialiser le minuteur de lame, réinitialiser le minuteur de la station de base |
| Mise à jour | Version du micrologiciel |
| Événement | Événement de la tondeuse (tonte démarrée / en pause / retour / à la base / terminée / erreur) |
| Calendrier | Planning de tonte (prochaine tonte programmée) |

### Installation

[![Ouvrez votre instance Home Assistant et ouvrez un dépôt dans le Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Méthode 1 : HACS (recommandée)
1. Assurez-vous que [HACS](https://hacs.xyz/) est installé
2. Utilisez le bouton ci-dessus pour ajouter l'intégration à HACS
3. Ouvrez HACS, recherchez « TerraMow » et sélectionnez l'intégration
4. Installez-la et redémarrez Home Assistant

#### Méthode 2 : Installation manuelle
1. Copiez le dossier `custom_components/terramow` dans le dossier `/config/custom_components` de votre Home Assistant
2. Redémarrez Home Assistant
3. Allez dans Paramètres → Appareils et services → Ajouter une intégration
4. Recherchez « TerraMow » et suivez les étapes de configuration

### Configuration

Les appareils du réseau local sont découverts automatiquement via Zeroconf — acceptez l'appareil détecté et saisissez le mot de passe MQTT. Pour une configuration manuelle, les paramètres suivants sont requis :

- **Hôte** : adresse IP ou nom d'hôte de l'appareil TerraMow
- **Mot de passe** : mot de passe MQTT pour l'authentification

**Modifier les réglages ultérieurement**
- *Reconfigurer* (Paramètres → Appareils et services → TerraMow → Reconfigurer) : changez l'hôte/IP ou le mot de passe sur place, par ex. après que la tondeuse a reçu une nouvelle adresse DHCP — inutile de supprimer et de rajouter l'intégration.
- *Options* (Configurer) :
  - **Résolution de sortie de la carte** — plus élevée signifie plus net, mais coûte plus de bande passante et de CPU à chaque rendu.
  - **Thème de la carte** — `light` ou `dark`.
  - **Afficher la surface tondue** — ombre la zone déjà tondue sous la ligne du trajet.
  - **Considérer toute tâche terminée comme achevée à 100 %** — certains micrologiciels terminent une tâche sans émettre de signal d'achèvement, si bien que la progression de la session n'atteint jamais 100 % alors que la pelouse est faite (elle apparaît comme « interrompue »). Activez cette option pour considérer toute tâche terminée comme achevée, comme le fait l'application du fabricant ; laissez-la désactivée pour conserver la valeur honnête du compteur. *Par défaut : désactivé.*
- Si le mot de passe de l'appareil change, Home Assistant lance automatiquement un flux de *réauthentification*.

### Prérequis

- Home Assistant 2024.6.0 ou plus récent (l'intégration continue valide contre la version actuelle de HA Core)
- Micrologiciel TerraMow version 6.6.0 ou plus récent
- Application TerraMow version 1.6.0 ou plus récente
- La carte en direct et le trajet de tonte nécessitent la version 3 du module HA du micrologiciel ; en version 2 (par ex. S800) tout le reste fonctionne, et le capteur de compatibilité de version le signale

### Appareils pris en charge

Cette intégration fonctionne avec les robots tondeuses TerraMow qui exposent l'interface MQTT/HTTP locale — c'est-à-dire tout modèle disposant du micrologiciel requis. Elle est utilisée avec la série S de TerraMow, y compris le **S800** (qui rapporte la version 2 du module HA du micrologiciel) et des unités plus récentes en version 3. Toute tondeuse TerraMow avec le micrologiciel 6.6.0+ et l'application 1.6.0+ devrait fonctionner ; le capteur de compatibilité de version et un signalement de réparation indiquent si le micrologiciel d'une unité donnée est trop ancien pour une fonctionnalité précise.

### Services

#### `terramow.start_select_region`

Démarre la tonte pour une liste de sous-régions sélectionnées.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Écrit ou supprime un créneau de tonte hebdomadaire sur la tondeuse. Chaque
écriture est confirmée auprès de l'appareil (accusé de réception dp_119 plus une
relecture du planning).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` attend l'`item_id` du créneau (affiché comme uid de
l'événement de calendrier et renvoyé lors de l'ajout d'un créneau).

> **Remarque :** le micrologiciel commercial actuel n'accepte pas encore
> l'écriture du planning via MQTT local (l'application du fabricant utilise
> Bluetooth/cloud). En attendant, utilisez le **blueprint de tonte adaptée à la
> météo** pour planifier côté HA.

### Carte interactive

L'intégration fournit sa propre carte Lovelace — enregistrée automatiquement, sans ressource manuelle ni installation frontend HACS séparée :

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Elle dessine la pelouse en vecteurs (nette à tout niveau de zoom, suit votre thème HA) : zones, zones interdites, murs virtuels, trajet de tonte, station de base et position en direct du robot. Faites glisser pour déplacer, molette ou pincement pour zoomer, double appui pour réajuster. **Appuyez sur une ou plusieurs zones** puis sur le bouton qui apparaît pour tondre exactement ces zones (`terramow.start_select_region` en coulisses).

Un **bouton de vue** fait défiler ce que la carte superpose à la pelouse :

| Mode | Affiche |
| --- | --- |
| **Les deux** | la surface tondue *et* le trajet de tonte (par défaut quand l'affichage de la surface est actif) |
| **Trajet** | uniquement le trajet de la tâche en cours et de la précédente |
| **Surface** | uniquement l'ombrage de la surface tondue, avec la progression par zone |
| **Wi-Fi** | une **carte de chaleur Wi-Fi** de la pelouse, mesurée par la tondeuse pendant la tonte (vert = fort). Les vides entre les passes sont interpolés depuis les mesures voisines ; le terrain jamais parcouru reste vide |

Le mode choisi est mémorisé par entité dans le navigateur. Options et détails : voir le [guide des tableaux de bord](en/dashboard.md#interactive-map-card) (en anglais). Les données de carte en direct nécessitent la version 3 du module HA du micrologiciel (comme la caméra de carte). La carte est aussi proposée dans le sélecteur de cartes du tableau de bord sous le nom **TerraMow Map Card**, avec un éditeur d'interface complet — aucun YAML requis.

### Exemple de tableau de bord

Une vue Lovelace prête à l'emploi (carte en direct, commandes, jauge de progression, aperçu d'état) et des automatisations de notification : voir le [guide des tableaux de bord](en/dashboard.md) (en anglais).

### Blueprints d'automatisation

Blueprints importables en un clic pour les notifications les plus courantes — chacun demande seulement l'entité TerraMow concernée et une action de notification :

- **Tonte adaptée à la météo** — démarre la tonte selon votre planning, ignorée automatiquement si la pluie est détectée ou prévue
  [![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Notification de problème** — lorsque la tondeuse signale un défaut
  [![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Retour à cause de la pluie** — lorsque la tondeuse rentre à la base à cause de la pluie
  [![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Tonte terminée** — lorsqu'une tâche de tonte s'achève
  [![Importer le blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Utiliser directement l'entité d'événement** — l'entité d'événement de la tondeuse est le déclencheur le plus souple. Son attribut `event_type` vaut `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed` ou `error`, et elle porte les champs bruts `mission`, `sub_mission`, `state`, `back_to_station_reason` et `has_error` :

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "TerraMow a terminé la tonte 🌱"
```

### Signalements de réparation

L'intégration crée des signalements de réparation Home Assistant exploitables (Paramètres → Appareils et services → Réparations) au lieu de cacher les problèmes dans des capteurs :

- **Micrologiciel incompatible / mise à jour requise** — le micrologiciel est trop ancien pour l'intégration (ou pour une fonctionnalité précise). Déduit du contrôle de compatibilité de version ; disparaît dès qu'un micrologiciel compatible se signale.
- **Entretien de la lame dû** — le disque de lame a atteint son intervalle d'entretien recommandé de 240 heures. Nettoyez ou remplacez les lames puis appuyez sur le bouton *Réinitialiser le minuteur de lame* pour l'effacer.
- **Entretien de la station de base dû** — la station de base a atteint son intervalle d'entretien recommandé de 30 jours. Nettoyez-la puis appuyez sur le bouton *Réinitialiser le minuteur de la station de base* pour l'effacer.

### Diagnostics et dépannage

- **Téléchargement des diagnostics** : Paramètres → Appareils et services → TerraMow → menu à trois points → *Télécharger les diagnostics* produit un instantané JSON expurgé (état de l'appareil, compatibilité du micrologiciel, caches bruts des points de données) — merci de le joindre aux rapports de bug.
- **Découvrir des fonctionnalités non prises en charge** : la tondeuse publie plus de points de données qu'il n'en est documenté. La première charge utile de chaque point de données inconnu est journalisée une fois au niveau INFO ; activez la journalisation de débogage pour l'intégration `terramow` afin de les enregistrer tous. Si vous trouvez un point de données correspondant à une fonctionnalité manquante (par ex. alarme de soulèvement, interrupteur de planning, codes d'erreur), partagez-le dans une issue.

### Comment les données sont mises à jour

TerraMow est une intégration **local push**. La tondeuse héberge un broker MQTT sur l'appareil ; Home Assistant s'y connecte directement via le réseau local (sans cloud) et s'abonne aux sujets de points de données de l'appareil, si bien que les états des entités se mettent à jour à l'instant où la tondeuse signale un changement, et non selon un intervalle d'interrogation. Les charges utiles plus volumineuses (la carte, le trajet en direct) sont annoncées via MQTT et récupérées à la demande via HTTP local. Si la tondeuse est en veille ou hors réseau, la connexion est retentée avec un délai exponentiel, et l'entité tondeuse expose la perte de connexion via son activité `error`.

**Les commandes échouent bruyamment, pas silencieusement.** Lorsque vous envoyez une commande — `dock`, `start_mowing`, `pause`, tonte des bordures, tonte par zone ou tout changement de réglage — elle est publiée en MQTT QoS 1 (une brève reconnexion la met donc en mémoire tampon au lieu de la perdre). Si la tondeuse est hors ligne ou injoignable, si le broker rejette la publication, ou si une commande arrive plus vite que l'appareil ne peut l'accepter, l'appel de service **échoue avec une erreur** au lieu de signaler un succès silencieux. Ainsi, une automatisation qui appelle `lawn_mower.dock` alors que la tondeuse est injoignable voit l'échec (et peut réessayer ou notifier) au lieu de croire que la tondeuse rentre alors qu'elle n'a jamais reçu la commande.

### Limitations connues

- **Pas d'accès cloud / à distance** — Home Assistant doit être sur le même réseau local que la tondeuse ; il n'existe pas de solution de repli via le cloud.
- **Fonctionnalités conditionnées par le micrologiciel** — la carte en direct et la vue du trajet de tonte nécessitent la version 3 du module HA ; en version 2 (par ex. le S800) tout le reste fonctionne, et le capteur de compatibilité / le signalement de réparation indique la limitation.
- **Les mises à jour du micrologiciel** se font via l'application TerraMow, pas depuis Home Assistant ; l'entité `update` du micrologiciel est purement informative.
- **Le capteur de position et la caméra de carte épurée sont désactivés par défaut** (le capteur de position se met à jour à environ 2 Hz) ; activez-les dans les réglages d'entité si vous en avez besoin.
- **De nombreuses entités de diagnostic avancé sont désactivées par défaut** et regroupées dans la catégorie *Diagnostic* (cellulaire, lever/coucher du soleil, modes de fonctionnement, indicateurs de cartographie manuelle, etc.) ; elles proviennent de points de données obtenus par ingénierie inverse — n'activez donc que celles dont vous avez besoin. Voir les [notes sur les points de données non officiels](en/developers/data_point_unofficial.md).
- Certains points de données de l'appareil ne sont pas documentés ; les inconnus sont journalisés une fois pour aider à découvrir les fonctionnalités manquantes.

### Cas d'usage

- **Notifications liées à la pluie** — recevez une notification lorsque la tondeuse rentre à sa base à cause de la pluie (voir les blueprints ci-dessus).
- **Alertes de défaut** — soyez averti dès que la tondeuse signale un problème (bloquée, soulevée, obstruée).
- **Tonte par zone depuis des automatisations** — appelez `terramow.start_select_region` pour tondre des sous-régions précises selon un planning ou depuis un bouton du tableau de bord.
- **Rappels d'entretien** — les capteurs de temps restant pour la lame / la station de base et les boutons de réinitialisation permettent d'automatiser les rappels d'entretien.
- **Carte en direct sur un tableau de bord** — affichez la caméra de carte avec la position du robot et le trajet de tonte (voir le guide des tableaux de bord).

### Langues

L'intégration est traduite en : Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Notes de mise à niveau

- **v0.5.0** : les valeurs d'état des entités sont passées des majuscules aux minuscules (par ex. `MISSION_IDLE` → `mission_idle`) pour se conformer aux exigences de traduction de Home Assistant. Les automatisations ou modèles comparant les chaînes d'état brutes nécessitent une adaptation unique ; les noms affichés restent inchangés.

### Assistance

Ouvrez une issue sur [GitHub](https://github.com/it-rec/TerraMowHA/issues) pour obtenir de l'aide.

### Informations pour les développeurs

Pour les développeurs souhaitant comprendre ou étendre cette intégration (la documentation développeur est en anglais) :

- [Guide de contribution](../CONTRIBUTING.md) — mise en place, exigences de qualité (100 % de couverture, `mypy --strict`, traductions), processus de PR et de publication
- [Architecture](ARCHITECTURE.md) — les rouages internes : cycle de vie du hub, modèle d'exécution, catalogue des points de données, pipeline carte/trajet
- [Guide du développeur](en/developers.md) — le protocole MQTT/HTTP de l'appareil sur le fil
- [Ce que ce fork ajoute par rapport à l'upstream](UPSTREAM_DELTA.md)

Pour exécuter la suite de tests en local :

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licence

Ce projet est sous licence GNU General Public License v3.0 — voir le fichier [LICENSE](../LICENSE) pour les détails.
