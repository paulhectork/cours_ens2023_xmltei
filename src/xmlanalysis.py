from pyvis.network import Network
from langdetect import detect
from statistics import mode
from zipfile import ZipFile
from lxml import etree
import unidecode
import requests
import spacy
import json
import time
import sys
import re
import os


# *****************************************************************
# analyse de la correspondance Matsutaka en XML-TEI
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
                ".//tei:correspAction[@type='sent']/(tei:persName or tei:orgName)/@ref"
                , namespaces=NS_TEI
            )[0].replace("#", "")
        receiver = tree.xpath(
                ".//tei:correspAction[@type='received']/(tei:persName or tei:orgName)/@ref"
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
        
    print(nodes)
    print(edges)
    
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
    print("enrichissement géographique des fichiers")
    corpus = geography(corpus)
    
    # créer le `particDesc` + faire de la reconnaissance
    # d'entités nommées pour chaque lettre du corpus
    print("traitement des noms de personnes et d'organisations")
    corpus = entity(corpus)
    
    # faire une visualisation en graphique
    print("visualisation de réseau")
    corpus = network(corpus)
    
    return

if __name__ == "__main__":
    pipeline()
    
    
    
    
    