from zipfile import ZipFile
from lxml import etree
import requests
import time
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
XML = os.path.abspath(os.path.join(CURDIR, os.pardir, "xml"))                    # dossier `xml/`
UNZIP = os.path.abspath(os.path.join(XML, "unzip"))
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
    créer un `settingDesc` dans le `profileDesc` du `teiHeader`
    de chaque corpus. ce `settingDesc` contient une liste de tous
    les lieux d'expédition/réception d'une lettre du corpus, avec
    sa géolocalisation
    
    :param corpus: la liste des fichiers xml du corpus
    :returns: la liste des fichiers xml du corpus, après une mise
              à jour de ces fichiers pour y ajouter le `settingDesc`
    """
    place_list = []  # liste de lieux
    endpoint = "https://nominatim.openstreetmap.org/search?"
    
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
    for place in place_list:
        if place == "NA":
            continue  # ne pas traiter "NA", qui logiquement n'est pas géocoordonnée
        
        # on commence par chercher un nom de ville: la majorité des `place` sont des villes
        time.sleep(1)  # il faut attendre 1s entre 2 requêtes
        r = requests.get(endpoint, params={ 
            "city": place,        # le nom de la ville recherchée
            "format": "geojson",  # format de la réponse: json
            "limit": 1            # nombre de résultats à afficher
        })
        
        # si on ne trouve pas de nom de ville, alors on fait une recherche 
        # libre en utilisant le param `q` à la place de `city`
        if len(r.json()) == 0:
            print(place)
            time.sleep(1)
            r = requests.get(endpoint, params={ 
                "q": place,           # `q`: query, paramètre de recherche libre
                "format": "geojson",  # format de la réponse: json
                "limit": 1            # nombre de résultats à afficher
            })
        
        # si la requête s'est bien passée et qu'on a des résultats, alors
        res = r.json()
        if r.status_code == 200 and len(res["features"]) > 0:
            
            # on extrait les coordonnées
            if res["features"][0]["geometry"]["type"] == "Point":
                coordinates = res["features"][0]["geometry"]["coordinates"]
            else:
                print(res)
            # print(r.json(), "\n\n")
        
            
        
        
    
    return corpus


def pipeline():
    """
    chaîne de traitement globale pour l'analyse du corpus en XML
    """
    # créer le dossier dans lequel les fichiers xml seront stockés
    if not os.path.isdir(UNZIP):
        os.makedirs(UNZIP)
    
    # extraire tous les fichiers zippés
    corpus = zip2tei()
    
    # créer le `settingDesc` dans le `profileDesc`
    corpus = setting_desc(corpus)
    
    return

if __name__ == "__main__":
    pipeline()
    
    
    
    
    