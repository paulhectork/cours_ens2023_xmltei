from pyvis.network import Network
from langdetect import detect
from statistics import mode
from zipfile import ZipFile
from lxml import etree
import unidecode
import requests
import folium
import shutil
import spacy
import json
import time
import math
import sys
import re
import os


# *****************************************************************
# analyse de la correspondance Matsutaka en XML-TEI.
# pour lire le code, commencer par regarder la fonction
# `pipeline()` à la fin. elle appelle toutes les autres
# fonctions dans ce script : ) 
# 
# crédits:
# - code: Paul Kervegan, 2023. code sous licence `GNU GPLv3.0`
# - données source: Léa Saint-Raymond (ENS-PSL) à partir 
#   d'originaux conservés au Musée Rodin et à l'INHA.
#   licence propriétaire: l'utilisation des données en 
#   dehors de cet atelier est interdite
# *****************************************************************


# variables constantes: les chemins vers les fichiers/dossiers utilisés
CURDIR = os.path.abspath(os.path.dirname(__file__))                              # dossier actuel
TXT = os.path.abspath(os.path.join(CURDIR, os.pardir, "txt"))                    # dossier `txt/`
WEB = os.path.abspath(os.path.join(CURDIR, os.pardir, "web"))                    # dossier `web/`
XML = os.path.abspath(os.path.join(CURDIR, os.pardir, "xml"))                    # dossier `xml/`
UNZIP = os.path.abspath(os.path.join(XML, "unzip"))                              # dossier `xml/unzip`
NS_TEI = {"tei": "http://www.tei-c.org/ns/1.0"}                                  # tei namespace
NS_XML = {"id": "http://www.w3.org/XML/1998/namespace"}                          # general xml namespace
TEI_RNG = "https://tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng"  # odd in .rng to validate tei files
PARSER = etree.XMLParser(remove_blank_text=True)                                 # parser xml custom
COLORS = { "green": "#8fc7b1",                                                   # codes couleurs html 
           "gold": "#da9902", 
           "plum": "#710551", 
           "darkgreen": "#00553e" }
# RNG = etree.RelaxNG( etree.parse(os.path.join(XML, "schema", "tei_all.rng")) )   # schéma xml rng de validation de la TEI
# TEMPLATE = etree.parse(os.path.join(XML, "template.xml"))                        # arbre etree contenant la structure XML de base


def zip2tei():
    """
    extraire tous les fichiers de l'archive zip dans `xml/unzip`
    
    :returns: liste du chemin absolu vers les fichiers xml dans `UNZIP`
    """
    with ZipFile( os.path.join(XML, "corpus_matsutaka.zip"), mode="r" ) as zip:
        zip.extractall(path=UNZIP)
    return [ os.path.join(UNZIP, f) for f in os.listdir(UNZIP) ]


def xmlid(text):
    """
    fonction pour créer un @xml:id à partir de la chaîne de caractère `text`.
    permet de normaliser la création d'identifiants uniques. on ne garde que
    les caractères alphanumériques sans majuscules de `text` + on enlève les
    accents des lettres avec `unidecode`.
    
    :param text: le texte à partir duquel produire un identifiant
    :returns: l'identifiant
    """
    return unidecode.unidecode("".join( c for c in text.lower() if c.isalnum()))
    

def geography(corpus):
    """
    faire des enrichissements géographiques du corpus
    
    chaine de traitement
    ~~~~~~~~~~~~~~~~~~~~
    - créer une liste de tous les lieux d'expédition/récéption du corpus
    - à partir de cette liste, créer un `settingDesc` dans le 
      `profileDesc` du `teiHeader` de chaque corpus. ce `settingDesc` 
      contient une liste de tous les lieux, avec sa géolocalisation
    - ajouter à chaque `placeName` dans le document encodé un attribut 
      `@ref` qui pointe vers une entrée du `settingDesc`
    - enregistrer la géolocalisation sous la forme d'un geojson 
      dans le dossier `web/json`.
    
    api nominatim:
    ~~~~~~~~~~~~~~
    https://nominatim.org/release-docs/develop/api/Search/
    
    structure de sortie:
    ~~~~~~~~~~~~~~~~~~~~
    ce settingDesc sera ajouté à tous les profileDesc
    <settingDesc xmlns:tei="http://www.tei-c.org/ns/1.0">
        <listPlace>
            <place xml:id="kobe">
                <placeName>Kobe</placeName>
                <location>
                    <geo>135.1943764 34.6932379</geo>
                </location>
            </place>
            <!-- ... -->
        </listPlace>
    </settingDesc>
    
    :param corpus: la liste des fichiers xml du corpus
    :returns: la liste des fichiers xml du corpus, après une mise
              à jour de ces fichiers pour y ajouter le `settingDesc`
    """
    # 1) DÉFINITION DES VARIABLES ET ÉLÉMENTS DE BASE
    #
    # on créé `settingDesc`, notre structure d'accueil pour 
    # les lieux: un élément tei settingDesc, qui contient un 
    # `listPlace` qui liste tout les lieux d'expédition/destination 
    # de notre corpus
    place_list = []  # liste de lieux
    endpoint = "https://nominatim.openstreetmap.org/search?"  # url de l'api nominatim
    settingDesc = etree.Element(
        "settingDesc"
        , nsmap=NS_TEI
    )
    listPlace = etree.SubElement(
        settingDesc
        , "listPlace"
        , nsmap=NS_TEI
    )
    
    # 2) CRÉATION D'UNE LISTE DE LIEUX
    #
    # d'abord, on construit une liste dédoublonnée de tous les différents
    # lieux d'expédition / récéption de lettres
    for fpath in corpus:
        tree = etree.parse(fpath, parser=PARSER)
        for place in tree.xpath(".//tei:correspAction/tei:placeName", namespaces=NS_TEI):
            place = place.text.replace("?", "").strip()  # simplifier la chaîne de caractères
            if (
                place not in place_list 
                and not re.search("^(inconnu|aucun)$", place)
            ):
                # ajouter le lieu s'il n'est pas déjà dans la liste
                # en supprimant les notations équivalentes à "NA" (lieu inconnu)
                place_list.append(place)                
    
    # 3) GÉOLOCALISATION DES LIEUX
    # 
    # ensuite, en utilisant l'API nominatim, récupérer 
    # les géolocalisations des différents lieux + enregistrer
    # des geojson de ces lieux
    for placename in place_list:
        # créer un identifiant unique @xml:id
        idx = xmlid(placename)
        
        # créer l'élément tei `place`, contenu par `listPlace`
        # et qui contient toutes les informations sur le lieu
        place = etree.SubElement(
            listPlace
            , "place"
            , nsmap=NS_TEI
        )
        place.set("{http://www.w3.org/XML/1998/namespace}id", idx)
        etree.SubElement(
            place
            , "placeName"
            , nsmap=NS_TEI
        ).text = placename
        
        if placename == "NA":
            # "NA", logiquement, n'est pas géocoordonnée
            # => on ne fait pas de requête sur nominatim et on
            # ne complète pas l'élément `place` créé avec des infos géolocalisées 
            continue
        
        # on commence par chercher un nom de ville: la majorité des `placename` sont des villes
        time.sleep(1)  # il faut attendre 1s entre 2 requêtes
        r = requests.get(endpoint, params={ 
            "city": placename,    # le nom de la ville recherchée
            "format": "geojson",  # format de la réponse: json
            "limit": 1            # nombre de résultats à afficher
        })
        
        # si on ne trouve pas de nom de ville, alors on fait une recherche 
        # libre en utilisant le param `q` à la place de `city`
        if len(r.json()) == 0:
            time.sleep(1)
            r = requests.get(endpoint, params={ 
                "q": placename,       # `q`: query, paramètre de recherche libre
                "format": "geojson",  # format de la réponse: json
                "limit": 1            # nombre de résultats à afficher
            })
        
        # si la requête s'est bien passée et qu'on a des résultats, alors
        # - on complète notre élément xml `place` avec un `location` qui
        #   contient un `geo`, celui-ci contenant les géocoordonnées
        # - on enregristre notre geojson dans le dossier `WEB/json/`
        res = r.json()
        if r.status_code == 200 and len(res["features"]) > 0:
            
            # on extrait les coordonnées et les ajoute à `place`
            if res["features"][0]["geometry"]["type"] == "Point":
                # on convertit la liste de coordonnées en string
                coordinates = "".join( 
                    f"{c} " for c in res["features"][0]["geometry"]["coordinates"] 
                ).strip()
                # on crée notre élément xml
                location = etree.SubElement(
                    place
                    , "location"
                    , nsmap=NS_TEI
                )
                etree.SubElement(
                    location
                    , "geo"
                    , nsmap=NS_TEI
                ).text = coordinates
                
                # enfin, on enregistre notre json. la réponse est en geojson => on crée
                # un fichier geojson et on l'enregistre, pour pouvoir y accéder +tard
                with open( os.path.join(WEB, "json", f"{idx}.geojson"), mode="w") as fh:
                    json.dump(res, fh, indent=4)
                
            else:
                # il n'y a pas de coordonnées, c'est étrange => on print
                print(f"pas de coordonnées pour '{placename}'", "\n", res, "\n\n")
    
    # 4) MISE À JOUR DES FICHIERS XML
    # 
    # ensuite, on met à jour les fichiers xml:
    # - on ajoute le `settingDesc` au `profileDesc`
    # - on ajoute des `@ref` aux `placeName` en dehors du
    #   `settingDesc` qui pointent vers les `@xml:id` du 
    #   `settingDesc`
    # - enfin, on enregistre les fichiers
    for fpath in corpus:
        tree = etree.parse(fpath, parser=PARSER)
        
        # ajout du `settingDesc`
        tree.xpath(".//tei:profileDesc", namespaces=NS_TEI)[0].append(settingDesc)
        
        # ajout des `@ref` aux `placeName`.
        # pour ce faire, on reconstruit un identifiant pour le lieu tel que l'`@xml:id`
        # du lieu a été créé dans le `settingDesc` => il suffira de faire la comparaison.
        # entre l'identifiant créé ici (`placetext`) et l'`@xml:id` du `settingDesc`  
        # on préfixe toujours la valeur d'un `@ref` par un `#`
        for placename in tree.xpath(".//*[not(tei:settingDesc)]//tei:placeName", namespaces=NS_TEI):
            placetext = xmlid(placename.text)
            # inconnu, aucun => on donne la valeur `#na` à `@ref`
            if re.search("^(inconnu|aucun)$", placetext):
                placename.set("ref", "#na")
            # pour vérifier que tous les `@ref` des `placename` renvoient bien à l'un
            # des `@xml:id` du `settingDesc`. rien ne devrait être printé à cette étape
            elif placetext not in settingDesc.xpath(".//@xml:id", namespaces=NS_TEI):
                print(f"no @xml:id found matching with {placename.text}: {placetext} not in "
                      + f"@xml:id list: {settingDesc.xpath('.//@xml:id', namespaces=NS_TEI)}")
            # pour tous les autres cas, on définit le `@ref`.
            else:
                placename.set("ref", f"#{placetext}")
                
        # enfin, on écrit les arbres xml mis à jour dans les bons fichiers
        etree.cleanup_namespaces(tree)
        etree.ElementTree(tree.getroot()).write(
            fpath
            , pretty_print=True
        )
        
    return corpus


def entity(corpus):
    """
    créer des enrichissements sur les personnes mentionnées
    dans le corpus. stocker toutes les données sur les entités
    dans les corpus xml: `TEI//profileDesc/particDesc/(listPerson|listOrg)`
    
    chaîne de traitement
    ~~~~~~~~~~~~~~~~~~~~
    - on créé `entities`, un dictionnaire associant à l'identifiant 
      unique de chaque expéditeur/destinataire les différentes orthographes 
      de son nom + la langue dans laquelle la lettre comportant son nom
      est écrite
    - avec Spacy, on identifie le type de chaque entité nommée: est-ce que
      c'est le nom d'une personne, d'une organisation? si oui, quel type 
      d'organisation?
    - on crée un `particDesc` qui contient un `listPerson` avec la liste
      de `person` et un ;`listOrg` avec la liste d'`org` expéditrices/destinataires 
      de lettres dans le corpus, en fonction des données produites par spacy
    - on met à jour le `correspDesc` en fonction des informations dans
      le `particDesc`
    - on met à jour les fichiers
    
    à propos des librairies utilisées
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    spacy: documentation en bref: https://spacy.io/usage/spacy-101
    spacy: ner: https://spacy.io/usage/linguistic-features#named-entities
    langdetect: documentation: https://pypi.org/project/langdetect/
    
    installer spacy et les corpus de langues
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    :windows:
    python -m venv .env.env\Scripts\activate
    pip install -U pip setuptools wheel
    pip install -U spacy
    python -m spacy download en_core_web_trf
    python -m spacy download fr_dep_news_trf
    :linux/macos:
    python -m venv .env
    source .env/bin/activate
    pip install -U pip setuptools wheel
    pip install -U spacy
    python -m spacy download en_core_web_trf
    python -m spacy download fr_dep_news_trf
    
    
    :return: corpus, la liste des chemins vers les fichiers
    """
    # 1) DÉFINITION DES VARIABLES ET ÉLÉMENTS DE BASE
    #
    # entities associe à un xml:id 3 clés:
    # - `name`: la liste des différentes orthographes de ce nom
    # - `type`: le type d'entité (personne, organisation...)
    # - `lang`: la langue du nom (pour définir le modèle spacy à utiliser)
    entities = {}
    lang_dict = {}                          # dictionnaire associant à l'xml:id d'une lettre la langue parlée                       
    nlp_fr = spacy.load("en_core_web_trf")  # modèle spacy pour l'anglais
    nlp_en = spacy.load("fr_dep_news_trf")  # modèle spacy pour le français
    particDesc = etree.Element(             # élément xml qui accueillera la liste de personnes 
        "particDesc"
        , nsmap=NS_TEI
    )
    listPerson = etree.SubElement(          # la liste de personnes
        particDesc
        , "listPerson"
        , nsmap=NS_TEI
    )
    listOrg = etree.SubElement(             # la liste des organisations
        particDesc
        , "listOrg"
        , nsmap=NS_TEI
    )
    
    # 1) PREMIER TRAITEMENT DES LETTRES
    #
    # 2 opérations:
    # - on créé un `listPerson` uniquement en prenant
    #   les nom des expéditeur.ice.s et des destinataires
    #   dans les `correspAction` de chaque lettre. la méthode
    #   de création est donc très similaire à celle du `listPlace`
    #   dans la fonction `geography`
    # - on détermine la langue de chaque lettre avec `langdetect` 
    #   pour pouvoir déterminer le modèle spacy à utiliser
    for fpath in corpus:
        tree = etree.parse(fpath, parser=PARSER)
        letter_idx = tree.xpath("./@xml:id", namespaces=NS_TEI)[0]  # letter's @xml:id
        
        # on détecte la langue de chaque lettre. pour ce faire, on extrait
        # le texte de la lettre avec une xpath, on en fait une seule chaîne
        # de caractère et on utilise `detect()` de la librairie `langdetect`
        lang = detect( " ".join(s for s in tree.xpath(".//tei:body//text()", namespaces=NS_TEI)) )
        lang_dict[letter_idx] = lang  # on ajoute la langue à `lang_dict`
        
        for pers in tree.xpath(".//tei:correspAction//tei:persName", namespaces=NS_TEI):
            
            # pour éviter les doublons inutiles, on ajoute pas tous les noms à `place_dict`
            # - on enlève les initiales
            # - on simplifie les chaînes de caractères avec la fonction `xmlid()`
            # - on ajoute le nom non simplifié en valeur de `entities` seulement si
            #   ce nom n'est pas déjà une valeur de `entities[idx]`
            # - à chaque fois, on ajoute le code de la langue pour déterminer le modèle
            #   à utiliser sur les noms extraits
            idx = xmlid(re.sub("((?<=\s)|(?<=^))[A-Z][a-zàâäéèûüùîïì]*\.", "", pers.text))
            
            # traitement spécifique pour `na` et équivalents: l'@xml:id défini sera `napartic`
            if re.search("^(inconnu|aucun|na)$", idx):
                if "napartic" not in entities.keys():
                    entities["napartic"] = { "name": [pers.text], "type": "", "lang": [lang] }
                elif pers.text not in entities["napartic"]["name"]:
                    entities["napartic"]["name"].append(pers.text)
                    entities["napartic"]["lang"].append(lang)
            # pour les autres noms:
            else:
                if idx not in entities.keys():
                    entities[idx] = { "name": [pers.text], "type": "", "lang": [lang] }
                elif  pers.text not in entities[idx]["name"]:
                    entities[idx]["name"].append(pers.text)
                    entities[idx]["lang"].append(lang)
    
    
    # 2) DÉTECTER LE TYPE D'ENTITÉ CONTENUE DANS `entities`
    # on a donc un dictionnaire associant un @xml:id de nom à toutes 
    # ses orthographes et aux langues des lettres où le nom apparaît
    # ensuite, on détecte le type d'entité nommée contenue dans `entities`
    for k in entities.keys():
        if len(entities[k]["lang"]) > 0:
            entities[k]["lang"] = mode(entities[k]["lang"])  # on extrait le mode, soit la langue la plus répandue pour la liste de lettres avec ce nom
        else:
            entities[k]["lang"] = ""  
        for name in entities[k]["name"]:
            # on sélectionne le bon modèle en fonction du langage. 
            # si le langage détecté n'est ni le français, ni l'anglais,
            # on affiche une erreur mais on utilise le modèle français: la
            # lettre est surement en français 
            if entities[k]["lang"] == "fr":
                doc = nlp_fr(name)
            elif entities[k]["lang"] == "en":
                doc = nlp_en(name)
            else:
                print(f"pas de modèle disponible pour la langue '{entities[k]['lang']}'"
                      + f"détectée dans la lettre: '{letter_idx}'. utilisation du modèle"
                      + " français par défaut 'fr_dep_news_trf'")
                doc = nlp_fr(name)
            
            # enfin, avec spacy, on détecte le type d'entité nommée encodée dans
            # les `correspAction` et on ajoute le label donné à l'entité nommée par spacy 
            # dans `name` à `entities`. spacy produit plusieurs entités nommées => on extrait
            # le mode, soit le type d'entité le + souvent détecté dans notre `name`. vu la 
            # taille de notre corpus c'est un peu inutile, mais bon
            if len(list(doc.ents)) > 0:
                entities[k]["type"] = mode([ ent.label_ for ent in doc.ents ])  # on calcule le mode parmi tous les types d'entités nommées relevées
            else:
                entities[k]["type"] = ""
            # pour une explication de chaque entité nommée identifiée dans `name`,
            # décocher le bloc ci-dessous
            # for ent in doc.ents: 
            #     print(name
            #           , "~~~~~~~~~~~~~~~~"
            #           , ent.text
            #           , ent.label_
            #           , spacy.explain(ent.label_))

    # 3) CRÉER LE `PARTICDESC`
    #
    # on a extrait toutes nos entités nommées. il ne reste plus qu'à créer notre 
    # `particDesc`. celui-ci contiendra:
    # -  un `listPerson`, avec tous les membres du `correspAction` identifié.es
    #    comme des personnes; 
    # - un `listOrg`, avec tous les membres du `correspAction` qui n'ont pas été 
    #   identifié.es comme des personnes par spacy.
    # pour chaque `person` / `org`, ajouter un `@xml:id` (la clé de `entities`)
    # et un `@type` (qui contient le type d'entité identifié par spacy
    for k in entities.keys():
        # définir `entity`, un élément de `listPerson` ou de `listOrg`.
        # déterminer son élément conteneur `parent` (`listPerson` ou `listOrg`)
        # , le nom de l'élément lui-même `el` (`person` / `org`)
        # , le nom du `elname`: `persName` ou `orgName`, élément indiquant le nom de `el`
        if entities[k]["type"] == "PERSON" or entities[k]["type"] == "":
            parent = listPerson
            el = "person"
            elname = "persName"
        else:
            parent = listOrg
            el = "org"
            elname = "orgName"
        # définir `entity`
        entity = etree.SubElement(
            parent
            , el
            , nsmap=NS_TEI
        )
        if entities[k]["type"] != "":
            entity.set("type", entities[k]["type"])  # définir le `@type`: type d'entité
        entity.set("{http://www.w3.org/XML/1998/namespace}id", k)  # définir l'identifiant de `entity`
        # définir ses sous-éléments `persName` ou `orgName`, portant les 
        # variantes d'appellations associées à cette entité dans les 
        # différentes lettres du corpus
        for name in entities[k]["name"]:
            etree.SubElement(
                entity
                , elname
                , nsmap=NS_TEI
            ).text = name
            
    # 4) METTRE À JOUR LES FICHIERS XML
    #
    # on reparse les fichiers xml pour:
    # - modifier les `correspAction`: si le `persName` renvoie en fait
    #   à une organisation, alors remplacer ce `persName` par un `orgName`
    #   (on fait ça à l'aide des différents `persName` / `orgName` dans le
    #   `particDesc`
    # - ajouter les `@ref` dans le `correspAction` qui font référence aux 
    #   @xml:id des entités identifiées dans le `particDesc`
    # - ajouter le `particDesc` au `encodingDesc` du fichier xml
    # - sauvegarder les arbres mis à jour
    for fpath in corpus:
        tree = etree.parse(fpath, parser=PARSER)
        
        # ajout du `particDesc` à l'arbre
        tree.xpath(".//tei:profileDesc", namespaces=NS_TEI)[0].append(particDesc)
        
        # on modifie les correspAction:
        # `corresp` = tous les noms expéditeur.ice.s/destinataires dans le `correspAction`
        for corresp in tree.xpath(".//tei:correspAction/tei:persName", namespaces=NS_TEI):
            
            # on cible l'élément du `particDesc` qui correspond à `corresp`
            for matched_entity in particDesc.xpath(f".//*[./text()='{corresp.text}']", namespaces=NS_TEI):
                # on met à jour le tag de `corresp`: si avec spacy, on a détecté que le nom
                # dans `corresp` n'est pas celui d'une personne, alors on change `persName` par
                # le bon tag
                corresp.tag = matched_entity.tag
                # enfin, on ajoute un `@ref` à `corresp` qui pointe vers le bon
                # `persName / org` dans le `particDesc` 
                idx = matched_entity.xpath("./parent::*/@xml:id")[0]
                corresp.set("ref", f"#{idx}")
        
        # on sauvegarde le fichier
        etree.cleanup_namespaces(tree)
        etree.ElementTree(tree.getroot()).write(
            fpath
            , pretty_print=True
        )
    
    return corpus


def network(corpus):
    """
    faire une visualisation en graphes / réseau du corpus de lettres:
    réseau d'expéditeur.ices et destinataires des lettres dans le 
    `correspAction`.
    
    structure de `nodes`: nodes représente les expéditeur.ice.s/destinataires
    ~~~~~~~~~~~~~~~~~~~~
    {
        # 1ere entrée
        "@xml:id de la personne": [
            "nom complet qui sera affiché"
            , <nombre de fois qu'iel est mentionnée comme expéditeur.ice ou destinataire>
        ]
        # 2e entrée
        , "@xml:id": [
            "nom complet"
            , <décompte>
        ]
    }
    
    structure de `edges`: edges représente les liens entre 2 nœuds du réseau
    ~~~~~~~~~~~~~~~~~~~~
    [
        # 1ere relation
        { 
            "from": "@xml:id de l'expéditeur.ice",
            "to": "@xml:id du destinataire"
            "count": <nombre de relations dans ce sens entre expéditeur.ice et destinataire>
        }
        # 2e relation
        , {
            "from": "@xml:id",
            "to":"@xml:id",
            "count": <décompte>
        }
    ]
    
    pyvis
    ~~~~~
    https://pyvis.readthedocs.io/en/latest/tutorial.html
    https://pyvis.readthedocs.io/en/latest/documentation.html
    
    :param corpus: la liste de chemins vers les fichiers xml
    :returns: pareil, le corpus
    """
    # 1) EXTRACTION DE DONNÉES
    #
    # on lit toutes les lettres du corpus, extrait les données pour 
    # construire un graphe (noms des expéditeur.ice.s/destinataire et 
    # nombre de mention de chacun.e, relation orientées entre expéditeur.ice
    # et destinataire et nombre de relations orientées)
    nodes = {}
    edges = []
    for fpath in corpus:
        tree = etree.parse(fpath, parser=PARSER)
        
        # @xml:id de l'expéditeurice et du/de la destinataire
        sender = tree.xpath(
                "//tei:correspAction[@type='sent']/*[not(tei:placeName)][not(tei:date)]/@ref"
                , namespaces=NS_TEI
            )[0].replace("#", "")
        receiver = tree.xpath(
                "//tei:correspAction[@type='received']/*[not(tei:placeName)][not(tei:date)]/@ref"
                , namespaces=NS_TEI
            )[0].replace("#", "")
                
            # en utilisant l'@xml:id, on prend le nom canonique du `particDesc`
        sender_name = tree.xpath(
                f".//tei:particDesc//*[@xml:id='{sender}']/*"
                , namespaces=NS_TEI
            )[0].text
        receiver_name = tree.xpath(
                f".//tei:particDesc//*[@xml:id='{receiver}']/*"
                , namespaces=NS_TEI
            )[0].text
        # except:
        #     print(sender, receiver, sender_name, receiver_name, "\n", fpath, "\n\n\n")
        
        # on ajoute `sender`/`receiver` à `nodes`. on ne distingue pas le rôle d'expéditeur/destinataire
        if sender not in nodes.keys():
            nodes[sender] = [ sender_name, 1 ]      # 1ere fois que `sender` est identifié comme nœud => créer une nv entrée
        else:
            nodes[sender][1] += 1                   # sinon, on incrémente le compteur d'occurrences pour cette entité
        if receiver not in nodes.keys():
            nodes[receiver] = [ receiver_name, 1 ]  # 1ere fois que `receiver` est identifié comme nœud => nv entrée
        else:
            nodes[receiver][1] +=1                  # sinon, on incrémente le compteur d'occurrences pour cette entité
            
        # on ajoute la relation entre `sender` & `receiver` à `edges`
        # si la relation orientée expéditeurice->destinataire n'existe pas on l'ajoute
        if not any( [sender, receiver] == [edge["from"], edge["to"]] for edge in edges ):
            edges.append({ "from": sender, "to": receiver, "count": 1 })
        # sinon, on récupère le dictionnaire dans `edges` qui décrit la bonne relation et on incrémente son compteur 
        else:
            # on sélectionne l'index de la bonne relation
            for edge in edges:
                if [edge["from"], edge["to"]] == [sender, receiver]:
                    idx = edges.index(edge)
            edges[idx]["count"] += 1  # on incrémente son compteur
        
    # 2) CRÉER LE RÉSEAU
    #
    # on crée un objet `network` de `pyvis` et on ajoute 
    # d'abord les nœuds (`add_node()`, et ensuite les arrêtes du graphe (`add_edge()`)
    ntw = Network( 
        directed=True                # on travaille avec un graphe orienté
        , bgcolor=COLORS["gold"]    # couleur d'arrière-plan
        , font_color=COLORS["darkgreen"]  # couleur de police
        , filter_menu=True                # un menu pour filtrer par les propriétés des nœuds et arrêtes
        # , select_menu=True                # menu pour filtrer par les propriétés des nœuds et arrêtes
    )
    for k, v in nodes.items():
        ntw.add_node(
            k                       # l'identifiant du nœud: un @xml:id
            , label=v[0]            # le nom affiché
            , size=v[1]             # la taille du nœud, déterminée par le nb d'occurrences dans le corpus
            , shape="dot"           # la forme
            , color=COLORS["plum"]  # la couleur du nœud
            , title=f"{v[0]} participe à {v[1]} échanges dans le corpus."  # texte à afficher quand on clique s/ le nœud
        )
    for edge in edges:
        ntw.add_edge(
            edge["from"]           # identifiant du nœud représentant l'expéditeur.ice (défini dans `.add_nodes()`)
            , edge["to"]           # identifiant du nœud représentant le/la destinatairice
            , width=edge["count"]  # l'épaisseur de l'arrête dépend du nombre d'envois
            , title=f"{edge['count']} lettres de { nodes[edge['from']][0] } pour { nodes[edge['to']][0] }"
        )
    ntw.barnes_hut(overlap=1, gravity=-40000)  # on modifie légèrement le modèle de gravité (qui définit la position des points du réseau)
    ntw.toggle_physics(True)  # conseillé par la doc
    
    # enregistrer le fichier. les dépendances javascript nécessaires sont stockées à la racine
    # du dossier => on les déplace dans WEB, en supprimant si besoin la version précédente
    ntw.write_html(os.path.join(WEB, "network.html"), local=True, notebook=False, open_browser=True)
    if os.path.isdir(os.path.join(WEB, "lib")):
        shutil.rmtree(os.path.join(WEB, "lib"))
    shutil.move(os.path.join(CURDIR, os.pardir, "lib"), WEB)
    
    return corpus


def map(corpus):
    """
    créer une représentation cartographique du corpus,
    avec un  point par lieu d'expédition.
    en fait un crée quelque chose de proche de `network()`: on crée
    un graphe, cette fois-ci non dirigé mais géoréférencé
    
    pour créer notre carte, on utilise `folium`, un port python de la
    librairie javascript Leaflet, l'une des plus utilisées pour faire
    des cartes Web. la syntaxe folium est, à peu de choses prêt, exactement
    la même que la syntaxe leaflet.
    
    modèles de données
    ~~~~~~~~~~~~~~~~~~
    nodes compte le nombre de fois qu'une ville est une ville d'expédition/réception de lettre
    nodes = { "@xml:id": <compteur d'occurences> }
    edges compte le nombre de relations non-directionnelles qui existent entre deux villes
    edges = [ { "a": "villeA", "b": "villeB", "count": <compteur d'occurrences> } ]  # l'ordre de 'a' et 'b' n'a pas d'importance
    
    :param corpus: la liste de chemins vers tous les fichiers xml
    :returns: cette même liste
    """ 
    # 1) EXTRACTION DE DONNÉES
    #
    # on parse tous les fichiers XML et on extrait tous les 
    # @xml:id des lieux d'expédition/destination du `correspAction`
    # afin de construire nodes et edges. dans les deux cas, on ne 
    # traite pas les index ayant pour valeur `na`, puisqu'ils ne sont
    # pas géoréférencés
    nodes = {}
    edges = []
    geojson_files = [ os.path.splitext(os.path.basename(fp))[0] 
                      for fp in os.listdir(os.path.join(WEB, "json")) ]  # liste de noms de geojson sans extension
    for fpath in corpus:
        tree = etree.parse(fpath, parser=PARSER)
        indexes = tree.xpath(".//tei:correspAction/tei:placeName/@ref", namespaces=NS_TEI)
        indexes = [ idx.replace("#", "") for idx in indexes ]  # on supprime le `#` au début pour retrouver l'@xml:id
        
        # d'abord, on remplit `nodes`: 
        for idx in indexes:
            if idx not in nodes.keys() and idx != "na":
                nodes[idx] = 1
            elif idx != "na":
                nodes[idx] += 1
                
        # ensuite, on remplit `edges`.
        # on utilise `range` qui à chaque itération émet un index de `edges` =>
        # permet d'itérer à travers tous les items de `edges`.
        # on vérifie dans les 2 sens si `indexes` a déjà une entrée dans `edges`
        # si oui, on incrémente le compteur. sinon, on ajoute une nouvelle entrée
        # à `edges` pour représenter la nouvelle relation entre deux villes.
        # on ne traite une correspondance que si la ville A et la ville B sont géoréférencées
        if all(i in geojson_files for i in indexes):
            sender, receiver = indexes
            
            # si la relation a<->b n'existe pas, on l'ajoute
            if not any( [sender, receiver] == [edge["a"], edge["b"]] for edge in edges ):
                edges.append({ 'a': sender, "b": receiver, "count": 1 })
            # sinon, on incrémente le compteur
            else:
                for i in range(len(edges)):
                    if [sender, receiver] == [edges[i]["a"], edges[i]["b"]]:
                        edges[i]["count"] += 1
    
    # `edges` est pour le moment une relation orientée: il peut y avoir
    # une entrée de la liste où ['a': 'Paris', 'b': 'Kobe'] et une autre
    # où ['a': 'Kobe', 'b': 'Paris'], chacune avec son compteur. 
    # on croise donc ces deux entrées et additionne les compteurs pour que
    # de `edges` représente des relations non-dirigées
    edges_undirected = []  # variable pour stocker le graphe non dirigé
    for edge in edges:
        for i in range(len(edges)):
            if [ edge["a"], edge["b"] ] == [ edges[i]["b"], edges[i]["a"] ]:
                edge["count"] += edges[i]["count"]
        edges_undirected.append(edge)
    edges = edges_undirected
    
    # 2) CONSTRUCTION DE LA CARTE
    #
    # on crée une carte `folium` et on y ajoute les marqueurs, cad les villes
    map = folium.Map(location=[48.8534951, 2.3483915], tiles="Stamen Toner")
    markers = {}  # dictionnaire mappant un @xml:id à un objet `folium.CircleMarker`. sera utilisé pour construire les relations entre les villes
    node_titles = {}  # dictionnaire mappant l'@xml:id d'un lieu à son nom lisible
    
    # on ajoute d'abord nos nœuds sur la carte
    for k, v in nodes.items():
        # on ne traite que les clés qui ont un geojson, soit des infos géographiques
        # attachées.
        if k not in geojson_files:
            print(f"pas de geojson pour l'@xml:id: {k}. ce lieu n'est pas traité")
            continue

        # on charge tous nos fichiers geojson. ils contiennent toutes
        # les infos dont on a besoin (et bien plus)! on s'en sert pour extraire
        # des géocoordonnées et le nom de l'endroit. on pourrait directement afficher
        # un point sur la carte en ajoutant le geojson à notre carte leaflet, mais
        # celui-ci aurait un diamètre fixe (alors qu'on veut un diamètre adapté
        # au nombre de lettres associées au lieu) => on extrait des infos pour
        # créer un `CircleMarker` folium
        with open(os.path.join(WEB, "json", f"{k}.geojson"), mode="r") as fh:
            geojson = json.load(fh)                                   # on ouvre le fichier geojson 
        coordinates = geojson["features"][0]["geometry"]["coordinates"]  # géocoordonnées
        title = geojson["features"][0]["properties"]["display_name"]     # nom complet
        
        node_titles[k] = title
        
        # pour garantir la lisibilité, on représente v (nombre de lettres liées à
        # un endroit) sur une échelle logarithmique et on multiplie cette échelle
        # logarithmique par 5. cela permet d'éviter que les gros marqueurs bloquent
        # toute la carte et que les petits soient invisibles, tout en conservant
        # un ordre de grandeur
        if v > 1:
            vlog = math.log(v) * 5
        else:
            vlog = v * 5
        
        markers[k] = folium.CircleMarker(
            location=[ coordinates[1], coordinates[0] ]          # positionnement
            , radius=vlog                                        # taille du marqueur
            , color=COLORS["plum"]                               # couleur de bordure
            , fill_color=COLORS["gold"]                          # couleur de remplissage
            , fill_opacity=1                                     # opacité
            , popup=f"<b>{title}</b>: <br/><br/> <b>{v}</b> lettres reçues ou expédiées"  # popup s'affichant quand on clicke sur le marker
        )
        markers[k].add_to(map)
    
    # ensuite, on ajoute nos arrêtes: les relations entre 2 villes
    maxcount = max([ e["count"] for e in edges ])  # +gd nombre de relations
    for edge in edges:
        # on définit l'opacité en fonction du nombre de lettres envoyées: 
        # 0.3 + 0.7 x <proportion du nombre de lettres entre les 2 villes actuelles 
        #              par rapport au nombre maximal de lettres envoyées entre 2 villes>
        opacity = (edge["count"] / maxcount) * 0.7 + 0.3
        folium.PolyLine(
            locations=[ markers[edge["a"]].location, markers[edge["b"]].location ]  # positions des 2 villes
            , color=COLORS["plum"]
            , stroke=5
            , opacity=opacity
            , fillColor=COLORS["plum"]
            , fillOpacity=opacity
            , popup=f"<b>{edge['count']}</b> lettres échangées entre <b>{node_titles[edge['a']]}</b> et <b>{node_titles[edge['b']]}</b>"
            , tooltip=f"<b>{node_titles[edge['a']]}</b> <br/><br/> <b>{node_titles[edge['b']]}</b>"
        ).add_to(map)
        
    map.save(os.path.join(WEB, "map.html"))
    
    return corpus
    


def pipeline():
    """
    chaîne de traitement globale pour l'analyse du corpus en XML
    """
    # créer le dossier dans lequel les fichiers xml seront stockés
    # ainsi que les fichiers de sortie
    if not os.path.isdir(UNZIP):
        os.makedirs(UNZIP)
    if not os.path.isdir(os.path.join(WEB, "json")):
        os.makedirs(os.path.join(WEB, "json"))
    
    # extraire tous les fichiers zippés
    print("dézippage des fichiers XML")
    corpus = zip2tei()
    
    # créer le `settingDesc` dans le `profileDesc` 
    # + produire des informations spatiales pour chaque lettre
    print("\nenrichissement géographique des fichiers")
    corpus = geography(corpus)
    
    # créer le `particDesc` + faire de la reconnaissance
    # d'entités nommées pour chaque lettre du corpus
    print("\ntraitement des noms de personnes et d'organisations")
    corpus = entity(corpus)
    
    # faire une visualisation en graphique
    print("\nvisualisation de réseau")
    corpus = network(corpus)
    
    # enfin, on fait une carte
    print("\ncartographie du corpus")
    corpus = map(corpus)
    
    return

if __name__ == "__main__":
    pipeline()
    
    
    
    
    