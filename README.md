# MODÉLISER ET EXPLOITER DES CORPUS TEXTUELS

![banner](./img/banner.png)

### 🔥🔥🔥 seulement un corpus réduit est mis en ligne: 14 lettres sur les 267 du corpus originel
- le corpus complet, utilisé pour l'atelier du 31, n'a pas encore été publié officiellement et n'est
  donc pas mis en ligne en l'état
- les visualisations produites à partir du corpus complet sont tout de même visibles: 
  [`map_full`](./web/map_full.html) et [`network_full`](./web/network_full.html) : )

Supports pour la journée d'atelier [Modéliser et exploiter des corpus textuels](https://odhn.ens.psl.eu/evenements/atelier-modeliser-et-exploiter-des-corpus-textuels), donnée avec Léa Saint-Raymond à l'ENS-PSL (31.03.2023). Cette journée 
vise à introduire aux bases de la modélisation en XML-TEI, et surtout, aux méthodes d'analyse automatique,
de fouille de texte et de visualisation de corpus XML avec Python. 

La journée est organisée en deux parties:
- le matin, on présente l'histoire du XML et de la TEI ainsi que les principes de base de la TEI
  à partir d'un atelier d'encodage "à la main".
- l'après-midi est consacré à l'analyse outillée d'un corpus encodé en XML avec Python (analyse de 
  réseaux, cartographie, reconnaissance d'entités nommées, API, manipulation et fouille de documents
  TEI)

---

## Chaîne de traitement, ou programme des hostilités

- **`txt2xml`** (hors atelier): production du corpus, avec encodage automatique en XML-TEI du corpus
  Matsutaka en texte brut
- **`xmlanalysis`**: l'atelier en tant que tel. chaîne de traitement et d'enrichissement automatique
  du corpus en TEI.
  - extraction **d'informations géographiques** depuis `Openstreetmap`, ajouts aux documents TEI d'un 
    `tei:settingDesc` documentant les lieux d'expédition/destination de toutes les lettres du corpus.
    Librairies: `lxml`, `requests`
  - **extraction d'informations sur les entités** (personnes, organisations) qui sont auteur.ice.s de lettres
    du corpus: extraction automatique, classification à l'aide de SpaCy (résolution d'entités nommées),
    création d'un `tei:particDesc` documentant ces auteur.ice.s et ajout de cet élément aux documents TEI.
    Librairies: `lxml`, `spacy`
  - visualisation et **analyse du réseaux** d'expéditeur.ice.s / destinataires présent.e.s dans le corpus.
    Librairies: `pyvis`, `lxml`
  - **cartographie** des villes de réception/expédition des différentes lettres du corpus. Librairies 
    `lxml`, `folium`

---

## Utilisation en local

Le code et les notebooks peuvent être exécutés localement, à l'aide de Jupyter Notebook ou en exécutant
juste le code dans `src/`, sans les notebooks.

### Installation

(ps: je n'ai pu tester l'installation que sur Linux, il ne devrait pas y 
avoir de problèmes avec Mac ou Windows).

Git doit déjà être installé. Ouvrir un terminal et entrer les commandes:

```bash
# cloner le dépôt
git clone https://github.com/paulhectork/cours_ens2023_xmltei.git
cd cours_ens2023_xmltei

# installer l'environnement virtuel
python3 -m venv env  # macos/linux
python3 -m venv .\env # windows

# sourcer l'environnement
source env/bin/activate  # macos/debian
env\Scripts\activate.bat # sur Windows. si ca ne marche pas, essayer: `env\Scripts\Activate.ps1` 

# installer les dépendances
pip install -r requirements.min.txt  # pour utiliser le code sans notebook
pip install -r requirements.txt      # pour utiliser le code avec notebook
```

### Utilisation

```bash
python src/txt2xml.py  # faire la transfo texte brut vers tei sous macos/linux
python src\txt2xml.py  # sous windows

python src/xmlanalysis.py  # faire la pipeline d'analyse sous linux/macos
python src\xmlanalysis.py  # windows

jupyter notebook  # lancer les notebooks
```

---

## Utilisation sur Google Colab

Le notebook est disponible à [cette addresse](https://colab.research.google.com/drive/1x9fPUqPRTXmHtTcYaHgBN3Qzo3VRDN7L?usp=sharing)

Pour l'utiliser, il faut avoir la structure de dossier ci-dessous (je ne mets pas le notebook ici, 
puisque celui-ci est placé automatiquement par Google Colab). Tous les autres fichiers/dossiers sont 
créés à la demande par le notebook.

```
content/ (le dossier avec une icône de folder, 4e icône en partant du haut 
  |      tout à gauche, en dessous du signe équation)
  |__xml/
      |__corpus_matsutaka.zip
```

Pour que le script puisse fonctionner, il faut que, après le dézippage, les
fichiers XML soient enregistrés dans `/content/xml/unzip/` (ce qui devrait être 
géré automatiquement par le script).

---

## Structure du dépôt

```
/racine
  |__google_colab/  les notebooks utilisables en ligne sur Google Colab
  |
  |__jupyter_notebook/  les notebooks utilisables localement sur Jupyter Notebook
  |
  |__slides/  les slides de la matinée (présentation du XML-TEI)
  |
  |__src/  le code source utilisé pour l'atelier
  |   |__txt2xml.py  chaîne d'encodage automatique du texte brut au XML-TEI (bonus!)
  |   |__xmlanalysis.py  chaîne de fouille des corpus XML-TEI. code source de
  |                      l'atelier à proprement parler
  |
  |__txt/  dossier contenant les fichiers en texte brut encodés en TEI avec `src/txt2xml.py`
  |  
  |__web/  dossier de sortie de `xmlanalysis`
  |   |__json/  dossier contenant des geojson récupérés de l'API nominatim contenant les infos
  |   |         géolocalisées sur le corpus
  |   |__network.html  la visualisation du réseau d'expéditeurices/destinataires du corpus Matsutaka
  |   |                produit automatiquement
  |   |__map.html  une visualisation cartographique des villes d'expédition/destination des lettres
  |                du corpus Matsutaka
  |
  |__xml/  dossier contenant les fichiers XML-TEI produits avec `txt2xml.py` et utilisés comme source
  |   |    de l'atelier de l'après-midi
  |   |__schema/  dossier contenant le schema RNG de la TEI (publié sous license libre par le TEI consortium)
  |   |__template/  structure de base des documents TEI produits avec `txt2xml.py`
  |   |__unzip/  dossier contenant les fichiers XML dézippés utilisés pour l'atelier de l'après-midi
  |   |__corpus_matsutaka.zip  archive zip de tous les fichiers XML
  |
  |__requirements.txt  les dépendances à installer pour une utilisation sur Jupyter Notebook
  |__requirements.min.txt  les dépendances à installer pour utiliser seulement le code python
                           (sans notebook) ou pour utiliser les notebooks Google Colab
```

--- 

## Debug et `pip`

Les modèles Spacy et les librairies utilisées sont très lourdes. J'ai rencontré
beaucoup de bugs pendant l'installation de dépendances, et il se peut que vous
aussi. Voilà quelques solutions trouvées:

- dans un terminal, sous Ubuntu/Debian Linux (et peut-être MacOS):
  - `pip install -U pip`: mettre à jour `pip`
  - `rm -r $(find . -name __pycache__)`: supprimer les fichiers `*.pyc` qui peuvent 
    causer des erreurs: `EOFError: marshal data too short.` à l'installation des
    dépendances.
- installer une version différente de Spacy ou de Tensorflow en fonction des spécificités
  de votre système (GPU ou non...). 
- ne pas installer les modèles `en_core_web_trf` et `fr_dep_news_trf`, très lourd,
  mais les modèles `en_core_web_sm` et `fr_core_news_sm`. Dans ce cas, il faut désinstaller
  Spacy, supprimer tout l'environnement virtuel, et recommencer "à la main" les installations
  (sans fichier de requirements, puisque dessus sont les modèles lourds et les dépendances 
  encore plus lourdes qui sont installées avec).

---

## Crédits

### Production du corpus en texte brut 

Léa Saint-Raymond. Dans l'attente d'une publication officielle, il n'est 
pas autorisé d'utilisé le corpus en dehors de l'atelier du 31 mars 2023.

### Code

Paul, Hector Kervegan, license libre GNU GPL 3.0. Ce dépôt contient le schéma RNG
de la TEI
