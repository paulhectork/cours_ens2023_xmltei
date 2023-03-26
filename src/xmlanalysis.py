from zipfile import ZipFile
from lxml import etree
import requests
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


def setting_desc(corpus):
    """
    faire des enrichissements géographiques du corpus:
    - créer une liste de tous les lieux d'expédition/récéption du corpus
    - à partir de cette liste, créer un `settingDesc` dans le 
      `profileDesc` du `teiHeader` de chaque corpus. ce `settingDesc` 
      contient une liste de tous les lieux, avec sa géolocalisation
    - enregistrer la géolocalisation sous la forme d'un geojson 
      dans le dossier `web/json`.
    
    api nominatim:
    ~~~~~~~~~~~~~~
    https://nominatim.org/release-docs/develop/api/Search/
    
    structure de sortie:
    ~~~~~~~~~~~~~~~~~~~~
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
    place_list = []  # liste de lieux
    endpoint = "https://nominatim.openstreetmap.org/search?"  # url de l'api nominatim
    
    # on créé notre structure d'accueil pour les lieux:
    # un élément tei settingDesc, qui contient un `listPlace`
    # qui liste tout les lieux d'expédition/destination de notre
    # corpus
    settingDesc = etree.Element(
        "settingDesc"
        , nsmap=NS_TEI
    )
    listPlace = etree.SubElement(
        settingDesc
        , "listPlace"
        , nsmap=NS_TEI
    )
    
    
    # d'abord, on construit une liste dédoublonnée de tous les différents
    # lieux d'expédition / récéption de lettres
    for fpath in corpus:
        tree = etree.parse(fpath)
        for place in tree.xpath(".//tei:correspAction/tei:placeName", namespaces=NS_TEI):
            place = place.text.replace("?", "").strip()  # simplifier la chaîne de caractères
            if (
                place not in place_list 
                and not re.search("^(inconnu|aucun)$", place)
            ):
                # ajouter le lieu s'il n'est pas déjà dans la liste
                # en supprimant les notations équivalentes à "NA" (lieu inconnu)
                place_list.append(place)                
    
    # ensuite, en utilisant l'API nominatim, récupérer 
    # les géolocalisations des différents lieux
    for placename in place_list:
        # créer un identifiant unique @xml:id
        idx = "".join( c for c in placename.lower() if c.isalnum())
        
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
    print(etree.tostring(settingDesc))
        
            
        
        
    
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
    corpus = zip2tei()
    
    # créer le `settingDesc` dans le `profileDesc`
    corpus = setting_desc(corpus)
    
    return

if __name__ == "__main__":
    pipeline()
    
    
    
    
    