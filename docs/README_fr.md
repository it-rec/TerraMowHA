# TerraMow pour Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="Logo TerraMow" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · **Français** · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · [Português](README_pt.md) · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Ceci est une intégration Home Assistant pour les robots tondeuses TerraMow.

### Fonctionnalités

**Contrôle**
- Entité tondeuse : démarrer, mettre en pause et retourner à la station
- Tonte par zones : entité de sélection de zone et service `terramow.start_select_region`
- Bouton de tonte des bordures
- Réglages depuis Home Assistant : hauteur de tonte, vitesse, espacement, vitesse des lames, distance de coupe des bordures, mode et angles de direction principale, coupe minutieuse des coins, mode de tonte des bordures en herbe haute
- Entretien : boutons de réinitialisation des compteurs du disque de lames et de la station de base

**Surveillance**
- Caméra de carte en direct avec trajet de tonte, position du robot et station de base (plus une caméra « carte seule » épurée pour les tableaux de bord, résolution configurable via les options)
- Batterie : niveau, état de charge, état de température, chargeur connecté, interrupteur d'alimentation
- Progression du travail : surface de la session en cours, progression (%), durée et type de travail ; temps de tonte cumulé, nombre de travaux et surface tondue
- État : mission / sous-mission / état de mission, mode de fonctionnement, mode d'alimentation, raison du retour à la station, détection de pluie, indicateur de problème, indicateurs de sauvegarde des données et de conversion des données
- Carte : état, surface, indicateurs détectée / constructible / sauvegarde en cours
- Planification : prochain démarrage planifié
- Entité de mise à jour du micrologiciel, version du micrologiciel sur la page de l'appareil et capteur de compatibilité de version
- Toutes les entités se mettent à jour instantanément lors des envois de l'appareil — aucun délai d'interrogation

**Confort d'utilisation de l'intégration**
- Découverte automatique via Zeroconf/mDNS
- Flux de reconfiguration (changer l'hôte/IP sans réajouter l'intégration) et flux de réauthentification
- Téléchargement de diagnostics pour des rapports de bogues faciles
- Traduite en 14 langues (en, cs, da, de, es, fi, fr, it, nb, nl, pl, pt, sv, zh-Hans)
- Communication locale en mode push basée sur MQTT — aucun cloud requis

### Entités prises en charge

| Plateforme | Entités |
| --- | --- |
| Tondeuse | Contrôle démarrer / pause / retour à la station avec activité en direct |
| Caméra | Carte avec trajet, robot et station de base ; variante « carte seule » épurée |
| Capteur | Niveau de batterie, état de la batterie, état de température de la batterie, état de la carte, surface de la carte, hauteur de tonte, vitesse de tonte, mode de fonctionnement, position, temps de tonte total / travaux / surface tondue, surface / progression / durée / type de travail de la session en cours, temps restant des lames et de la station de base, prochain démarrage planifié, compatibilité de version, état de la direction principale, mode d'alimentation, raison du retour à la station, mission, sous-mission, état de mission |
| Capteur binaire | En charge, navigation localisée, mise à jour du micrologiciel en cours, interrupteur d'alimentation, problème, pluie détectée, carte détectée / constructible / sauvegarde en cours, sauvegarde des données, conversion des données en cours |
| Sélection | Sélection de zone, vitesse de tonte, vitesse des lames, mode de direction principale, mode de tonte des bordures en herbe haute |
| Nombre | Hauteur de tonte, distance de coupe des bordures, espacement de tonte, angle de direction unique, intervalle d'angle de rotation automatique, angle de la première / seconde direction |
| Interrupteur | Coupe minutieuse des coins |
| Bouton | Tonte des bordures, réinitialiser le minuteur des lames, réinitialiser le minuteur de la station de base |
| Mise à jour | Version du micrologiciel |

### Installation

#### Méthode 1 : HACS (recommandée)
1. Assurez-vous que [HACS](https://hacs.xyz/) est installé
2. Utilisez le bouton ci-dessus pour ajouter l'intégration à HACS
3. Allez dans HACS → Intégrations → + → Recherchez « TerraMow »
4. Installez puis redémarrez Home Assistant

#### Méthode 2 : Installation manuelle
1. Copiez le dossier `custom_components/terramow` dans le dossier `/config/custom_components` de votre Home Assistant
2. Redémarrez Home Assistant
3. Allez dans Paramètres → Appareils et services → Ajouter une intégration
4. Recherchez « TerraMow » et suivez les étapes de configuration

### Configuration

Les appareils du réseau local sont découverts automatiquement via Zeroconf — acceptez l'appareil découvert et saisissez le mot de passe MQTT. Pour une configuration manuelle, les paramètres suivants sont requis :

- **Hôte** : adresse IP ou nom d'hôte de l'appareil TerraMow
- **Mot de passe** : mot de passe MQTT pour l'authentification

**Modifier les paramètres ultérieurement**
- *Reconfigurer* (Paramètres → Appareils et services → TerraMow → Reconfigurer) : changez l'hôte/IP ou le mot de passe sur place, par exemple après que la tondeuse a reçu une nouvelle adresse DHCP — inutile de supprimer puis de réajouter l'intégration.
- *Options* (Configurer) : définissez la résolution de sortie de la caméra de carte. Des valeurs plus élevées donnent une image de tableau de bord plus nette, au prix de davantage de bande passante et de CPU par rendu.
- Si le mot de passe de l'appareil change, Home Assistant démarre automatiquement un flux de *réauthentification*.

### Prérequis

- Home Assistant 2023.9.3 ou ultérieur (testé avec 2025.1.1)
- Micrologiciel TerraMow version 6.6.0 ou ultérieure
- APP TerraMow version 1.6.0 ou ultérieure
- La carte en direct et le trajet de tonte nécessitent la version 3 du module HA du micrologiciel ; avec la version 2 (par ex. S800), tout le reste fonctionne et le capteur de compatibilité de version le signale

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

### Diagnostics et dépannage

- **Téléchargement de diagnostics** : Paramètres → Appareils et services → TerraMow → menu à trois points → *Télécharger les diagnostics* produit un instantané JSON expurgé (état de l'appareil, compatibilité du micrologiciel, caches bruts des points de données) — veuillez le joindre à vos rapports de bogues.
- **Découvrir des fonctionnalités non prises en charge** : la tondeuse publie plus de points de données que ceux documentés. La première charge utile de chaque point de données inconnu est journalisée une seule fois au niveau INFO ; activez la journalisation de débogage pour l'intégration `terramow` afin de tous les enregistrer. Si vous trouvez un point de données correspondant à une fonctionnalité manquante (par ex. alarme de soulèvement, interrupteur de planification, codes d'erreur), merci de le partager dans une issue.

### Langues

L'intégration est traduite en : Čeština, Dansk, Deutsch, English, Español, Français, Italiano, Nederlands, Norsk (bokmål), Polski, Português, Suomi, Svenska et 简体中文.

### Notes de mise à niveau

- **v0.5.0** : les valeurs d'état des entités sont passées des majuscules aux minuscules (par ex. `MISSION_IDLE` → `mission_idle`) afin de se conformer aux exigences de traduction de Home Assistant. Les automatisations ou modèles comparant des chaînes d'état brutes nécessitent une mise à jour ponctuelle ; les noms affichés restent inchangés.

### Assistance

Ouvrez une issue sur [GitHub](https://github.com/TerraMow/TerraMowHA/issues) pour obtenir de l'aide.

### Informations pour les développeurs

Les développeurs souhaitant comprendre ou étendre cette intégration peuvent consulter le [Guide du développeur](en/developers.md).

Pour exécuter la suite de tests localement :

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licence

Ce projet est sous licence GNU General Public License v3.0 — consultez le fichier [LICENSE](../LICENSE) pour plus de détails.
