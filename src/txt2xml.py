from pprint import pprint
from lxml import etree
import datetime
import sys
import re
import os


# *****************************************************************
# transformation de la correspondance Matsutaka 
# depuis un fichier texte vers des fichiers xml-tei 
#
# crédits:
# - code: Paul Kervegan, 2023. code sous licence `GNU GPLv3.0`
# - données source: Léa Saint-Raymond (ENS-PSL)
# *****************************************************************


# variables constantes: les chemins vers les fichiers/dossiers utilisés
CURDIR = os.path.abspath(os.path.dirname(__file__))                              # dossier actuel
TXT = os.path.abspath(os.path.join(CURDIR, os.pardir, "txt"))                    # dossier `txt/`
XML = os.path.abspath(os.path.join(CURDIR, os.pardir, "xml"))                    # dossier `xml/`
NS_TEI = {"tei": "http://www.tei-c.org/ns/1.0"}                                  # tei namespace
NS_XML = {"id": "http://www.w3.org/XML/1998/namespace"}                          # general xml namespace
TEI_RNG = "https://tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng"  # odd in .rng to validate tei files
# RNG = etree.RelaxNG( etree.parse(os.path.join(XML, "schema", "tei_all.rng")) )   # schéma xml rng de validation de la TEI
# TEMPLATE = etree.parse(os.path.join(XML, "template.xml"))                        # arbre etree contenant la structure XML de base


def corpussplit(corpus):
    """
    première structuration du texte brut utilisé en source:
    à partir de la correspondance en texte brut,
    - séparer chaque entrée individuellement
    - séparer les partiers de chaque entrée (métadonnées, titre, corps de la lettre)
    - retourner le corpus structuré sous la forme d'une liste de liste:*
      - chaque entrée de la liste est une lettre. 
      - ces entrées contiennent toutes 3 listes:
        - une liste représentant les métadonnées
        - une liste représentant le titre
        - une liste représentant le corps de la lettre.
        => à ce niveau, une entrée de liste = une ligne du fichier texte.
    [
        # entrée 1
        [
            [ "métadonnées" ]
            , [ "titre" ]
            , [ "corps de la lettre" ]
        ]
        
        # entrée 2
        , [
            [ "métadonnées" ]
            , [ "titre" ]
            , [ "corps de la lettre" ]
        ]
    ]
    
    :param corpus: le corpus texte brut
    :returns: `out`, une liste correspondant à la structure définie ci-dessus
    """
    out = []  # variable de sortie
    # d'abord, on sépare les différentes entrées. 
    # pour séparer un texte en une liste en utilisant la méthode `.split()`.
    # cette méthode prend en argument un ou plusieurs caractères, qu'on appelle
    # des séparateurs. une nouvelle entrée de la liste sera créé à chaque fois
    # que le séparateur est rencontré.
    # le séparateur entre deux entrées est plusieurs sauts de lignes: "\n\n". 
    corpus = corpus.split("\n\n")
    
    # ensuite, on sépare les 3 parties de chaque lettre.
    # ici, on utilise `.split("\n")` pour accéder aux lignes 
    # individuellement en créant une liste.
    # on utilise l'indexation de la liste pour séparer les différeentes
    # parties de la lettre. pour rappel, l'indexation d'une liste commence 
    # à 0 en python.  
    for lettre in corpus:
        meta = lettre.split("\n")[0:5]  # métadonnées: les lignes 0 à 5 de la lettre
        titre = lettre.split("\n")[5]   # le titre: la 6e ligne de la lettre
        corps = lettre.split("\n")[6:]  # le corps: tout ce qui vient après le titre
        out.append([meta, titre, corps])
    
    return out


def makesense(corpus):
    """
    faire sens du corpus: à partir de la liste 
    structurée produite par `corpussplit()`, produire 
    une "structuration sémantique": restructurer le corpus
    sous une forme qui explicite le sens de chaque partie, et
    non juste la place de chaque partie (ce que faisait `corpussplit()`.
    
    structure de sortie:
    ~~~~~~~~~~~~~~~~~~~~
    [
        # lettre 1
        {
            "idx": ""        # identifiant unique
            "typology": "",  # de quel type de document s'agit-il?
            "metadata": {},  # métadonnées du document
            "title": "",     # titre du document
            "body": {}       # corps du document
        }
        
        # lettre 2
        , {
            "idx": ""        # identifiant unique
            "typology": "",  # de quel type de document s'agit-il?
            "metadata": {},  # métadonnées du document
            "title": "",     # titre du document
            "body": {}       # corps du document
        }
    ]
    
    :param corpus: le corpus sous forme de liste imbriquée
    :returns: `corpus_struct`, une variable avec la structure présentée ci-dessus
    """
    corpus_struct = []  # variable de sortie
    meta_keys = ["date", "sender", "sender_place", "recipient", "recipient_place"]
    for lettre in corpus:
        meta = lettre[0]
        if not re.search("^\s*\[[^\]]+\]\s*$", lettre[1]):
            # si le titre n'est pas que entre crochets
            titre = re.sub("\[.+\][\.\?\s]*$", "", lettre[1])  # on supprime ce qui est entre crochets, qui formera notre clé `source` dans `meta`
            source_match = re.search("\[([^\]]+)\][\.\?\s]*$", lettre[1])  # on créée `source` en extrayant l'identifiant de la lettre source (institution de conservation + cote)
            source = source_match[1] if source_match else "Source inconnue"
        else:
            # sinon, pas moyen de distinguer titre et cote muséale/archivistique => on extrait que le titre
            titre = lettre[1] if not re.search("^\s*$", lettre[1]) else "Titre inconnu"
            source = "Source inconnue"
        
        corps = lettre[2]
        
        # 1) NORMALISATION DU TITRE
        #
        # on récupère le premier mot du titre pour créer une typologie de documents
        try:
            typology = re.search("[a-za-zàâäéèûüùîïì]+", titre.split()[0].lower())[0]
        except IndexError:
            # aucun titre pour cette lettre => rien à extraire
            typology = ""
        
        # 2) NORMALISATION DES MÉTADONNÉES
        # 
        # pour chaque lettre, construire un dictionnaire de métadonnées
        # qui prenne en clé une entrée de `meta_keys` ci-dessous et en valeur
        # des données extraites de la liste de métadonnées.
        meta_dict = {}
        meta_dict["source"] = source  # on commence par définir notre `source`, qui n'est pas dans `meta_keys` et implique donc un traitement particulier 
        
        # explication des 2 lignes de code ci-dessous:
        #
        # `meta_keys` et `meta` sont alignées (chaque entrée de `meta_keys`
        # correspond à une entrée de `meta`). les deux listes sont dans le même ordre: 
        # l'entrée 2 de `meta_keys` servira de clé à la valeur extraite de l'entrée 2 de `meta`
        #
        # on utilise `range()` qui, à chaque itération, envoie un chiffre de 0 à la 
        # longueur de la liste `meta`. cela permettra d'accéder aux entrées correspondantes
        # de `meta` et de `meta_keys` (à la 1ere itération, on peut travailler avec les items 
        # aux index 0 de `meta_keys` et de `meta`...)
        #
        # on extrait la donnée importante de l'entrée actuelle de `meta`: 
        # tout ce qui est entre `:` et la fin de l'entrée. pour ce faire, 
        # on utilise l'expression régulière `:(.+)$`, qui capture:
        # - `:`  => le caractère `:`, littéralement
        # - `.+` => n'importe quel caractère (`.`), une ou plusieurs fois (`+`). 
        #           on entoure ça de parenthèses pour en faire un sous-groupe,
        #           et pouvoir y accéder indépendamment du reste de l'expression
        #           régulière.
        # - `$`  => la fin de la ligne.
        #
        # enfin, on assigne la valeur extraite à la clé correspondante dans `meta_keys`
        # et on ajoute ce couple clé-valeur à `meta_dict`
        for i in range(len(meta)):
            meta_dict[ meta_keys[i] ] = re.search( ":(.+)$", meta[i] )[1].strip()
        
        # ensuite, on normalise la notation des dates: 
        # - on parse les dates en un objet `date` de la librairie Python `datetime`. 
        # - si les mois et les jours sont inconnus, on les remplace par `1`: 
        #   `1922/??/??` => `1922/01/01`.  c'est un détour obligatoire, 
        #    puisque Python n'accepte que des dates complètes, mois et 
        #    jours inclus
        date = meta_dict["date"].split("/")  # séparer année, jour, mois
        for i in range(len(date)):
            # on boucle sur chaque item de la liste [annee, jour, mois]
            # pour extraire les nombres ou remplacer par `1` si l'année, le jour
            # ou le mois ne contiennent pas de nombres.
            d = date[i].strip()
            dmatch = re.search("^\d+$", d)  # l'année/jour/mois ne contient que des nombres => est valide
            
            # si `d` n'est pas valide, remplacer par 1. sinon, garder les nombres extraits 
            if not dmatch:
                d = 1
            else:
                d = int(dmatch[0]) 
            date[i] = d  # on met à jour `date` avec l'année/jour/mois mis à jour.
        
        date = datetime.date( date[0], date[1], date[2] )  # on convertit en objet `datetime.date`
        meta_dict["date"] = date  # on met à jour la date dans le dictionnaire
        
        # 3) NORMALISATION DU CORPS DE TEXTE
        #
        # on extrait les formules de politesse d'ouverture et de fermeture, 
        # la signature, le post-scriptum ainsi que le corps du texte et on stocke 
        # le tout dans le dictionnaire `corps_dict`. les salutations, la signature
        #  et le post-scriptum sont des chaînes de caractères, le corps est une liste, 
        # avec une entrée par ligne de texte.
        #
        # pour ce faire, on opère par élimination, en partant des motifs les plus
        # distinctifs vers les moins distinctifs: on part de la salutation d'ouverture,
        # ensuite le post-scriptum, la signature et la salutation de fermeture. 
        # à chaque fois qu'un motif est détecté, la ligne qui y correspond est retirée
        # de `corps`. comme ça, on ne restera plus qu'avec le "vrai" corps du texte,
        # sans en-tête et salutations. c'est ce "vrai" corps qui est le moins facile
        # à détecter, et on ne le détecte pas: le corps, c'est tout ce qui n'est ni 
        # signature, ni salutations, ni formule de politesse, ni post-scriptum.
        # 
        # pour notre détection de motifs, on s'appuie sur des formulations 
        # conventionnelles ("veuillez aggréer"...), mais comme on le voit, c'est assez 
        # difficile. on arrive aux limites de ce qu'on peut faire avec du texte brut 
        # et des regex => c'est là que la TEI et la détection d'entités nommées vont
        # devenir utiles !
        #
        # comme on procède par élimination, on vérifie toujours le `len(corps) > 1`,
        # c'est-à-dire que la ligne sur laquelle on est en train de faire notre
        # détection de motifs n'est pas la dernière du document: si c'était le cas,
        # on aurait un problème, puisqu'on ne garderait plus de données pour le corps
        # de la lettre
        corps_dict = {
            "greetings": "",  # salutations en ouverture
            "body": [],       # corps de la lettre
            "closing": "",    # salutation en fermeture
            "signature": "",  # signature
            "postscript": ""  # post-scriptum, après la signature
        }
        # a. formules de politesse en ouverture
        greetings_match = re.search(
            "("
            + "[Dd]ear"
            + "|[Cc]h[eè]re?"
            + "|[Mm]onsieur"
            + "|[Mm]adame"
            + "|[Mm]a[îi]tre"
            + "|[Dd]irecteur"
            + "|[Ss]ir"
            + "|[Mm]adam"
            + "|[Mm]iss"
            + "|[Mm]essieur"
            + "|[Mm]edames"
            + ")"
            , corps[0]
        )
        if greetings_match and len(corps) > 1:
            corps_dict["greetings"] = corps[0]  # on stocke la ligne de salutation dans le dictionnaire
            corps.pop(0)  # retirer la salutation du corps de texte
        
        # b. post-scriptum
        postscript_match = (
            re.search("[Pp](ost)?(\.|\s|-)*[Ss](criptum)?(\.|\s|-)*", corps[-1])
            or re.search("[Nn](ota)?(\.|\s|-)*[Bb](ene)?(\.|\s|-)*", corps[-1])
        )
        if postscript_match and len(corps) > 1:
            corps_dict["postscript"] = corps[-1]
            corps.pop(-1)
         
        # c. signature
        signature_match = re.search(
            "("
            + "[Ss]ign[eé]"   # signé
            + "|Per\s[Pp]ro"  # per pro
            + "|P\.?P\.?"     # per pro
            + "|[A-Z]+[a-zàâäéèûüùîïì]*[\.|\s|-]*[A-Z]+[a-zàâäéèûüùîïì]*"  # nom propre au format Nom Prénom
            + "|^[\.|\s|-]*[A-Z]+[a-zàâäéèûüùîïì]*[\.|\s|-]*$"  # nom propre avec juste un nom de famille
            + "|[A-Z]+[a-zàâäéèûüùîïì]*\.$"           # Nom.[fin]
            + "|\.\s*[A-Z]+[a-zàâäéèûüùîïì]*\s*\.?$"  # . Nom\s?.?[fin]
            + "|^[A-Z]+[a-zàâäéèûüùîïì]*\."           # [début]Nom.
            + ")"
            , corps[-1]
        )
        # pour réduire le bruit, on considère qu'une signature est courte: elle fait moins de 60 caractères
        if signature_match and len(corps) > 1 and len(corps[-1]) < 60:
            corps_dict["signature"] = corps[-1]
            corps.pop(-1)
        
        # d. closing: la formule de politesse
        closing_match = re.search(
            "("
            + "[Aa]grée[rz]"
            + "|[Ss]alutation"
            + "|[Dd]istingué"
            + "|[Ss]entiment"
            + "|[Ss]incère"
            + "|[Ss]ouvenir"
            + "|[Rr]espectueu"
            + "|[Cc]onsidération"
            + "|[Cc]ordialement"
            + "|[Dd]évoué"
            + "|[Yy]ours"
            + "|[Ff]aithfully"
            + "|[Ss]incerely"
            + ")"
            , corps[-1]
        )
        # pareil, on considère qu'une formule de salutation est relativement courte
        if closing_match and len(corps) > 1 and len(corps[-1]) < 300:
            corps_dict["closing"] = corps[-1]
            corps.pop(-1)
        
        # on considère que le reste forme le corps de la lettre à proprement parler
        corps_dict["body"] = corps
        
        # 5) CONSTRUIRE L'IDENTIFIANT UNIQUE
        #
        # format: `{expéditeur}_{destinataire}_{date au format iso}_{hash de la lettre en texte sous forme de liste}`
        idx = "%s_%s_%s_%s".replace(" ", "") % (
            "".join( c for c in meta_dict['sender'] if c.isalnum() )
            , "".join( c for c in meta_dict['recipient'] if c.isalnum() )
            , "".join( c for c in str(meta_dict['date']) if c.isalnum() )
            , hash(str(lettre))
        )

        # 6) CONSTRUIRE `lettre_struct` et l'ajouter à notre variable de sortie
        lettre_struct = {
            "idx": idx,
            "typology": typology,
            "metadata": meta_dict,
            "title": titre,
            "body": corps_dict
        }
        
        corpus_struct.append(lettre_struct)
    
    return corpus_struct


def corpus2tei(corpus):
    """
    transformer le corpus en documents TEI
    
    exemple d'encodage TEI de lettre:
    https://gist.github.com/dhscratch/378e31e8e69dbb54d82b6be2634f4e7f
    
    exemple avancé d'utilisation de LXML:
    https://github.com/katabase/Application/blob/main/APP/utils/api_classes/representations_tei.py
    """
    for lettre in corpus:
        # on transforme toutes nos représentations de lettres en documents XML.
        idx = lettre["idx"]
        tree = etree.parse(
            os.path.join(XML, "template", "template.xml")     # le fichier à ouvrir
            , parser=etree.XMLParser(remove_blank_text=True)  # le parseur à utiliser. celui-ci ne prend pas en compte les espaces entre les éléments
        )  # notre arbre xml, qui stockera l'arbre xml que l'on est en train de créer
        
        # on accède à l'élément racine (`tree.getroot()`
        # et on lui ajoute l'identifiant unique du fichier (`.set("nom de l'attribut", "valeur")`)
        # la syntaxe un peu étrange avec une URL sert à indiquer que `id` appartient à l'espace 
        # de nom XML défini par le W3C
        tree.getroot().set("{http://www.w3.org/XML/1998/namespace}id", idx)
        
        # on crée le contenu de notre `titleStmt`: 
        # - un `title` avec le titre de la lettre, 
        # - un `author` avec l'auteur.ice
        # - deux `respStmt`, qui décrivent les personnes 
        #   responsables de l'édition numérique
        # `etree.SubElement(parent, "titre", namespace)` crée un élément enfant de `parent`;
        # `.text` permet d'ajouter du texte à l'intérieur de l'élement.
        titleStmt = tree.xpath(".//tei:titleStmt", namespaces=NS_TEI)[0]
        # titre
        title = lettre["title"] if not re.search("^\s*$", lettre["title"]) else "Titre inconnu"
        etree.SubElement(
            titleStmt
            , "title"
            , nsmap=NS_TEI
        ).text=title
        # auteur.ice de la lettre (le/la destinataire sera indiqué.e dans le `profileDesc`) 
        etree.SubElement(
            titleStmt
            , "author"
            , nsmap=NS_TEI
        ).text = lettre["metadata"]["sender"]
        # le premier respStmt: qui a préparé le document texte pour l'encodage  
        respStmt = etree.SubElement(
            titleStmt
            , "respStmt"
            , nsmap=NS_TEI
        )
        etree.SubElement(
            respStmt
            , "resp"
            , nsmap=NS_TEI
        ).text="Production et préparation du texte brut"
        etree.SubElement(
            respStmt
            , "persName"
            , nsmap=NS_TEI
        ).text="Léa Saint-Raymond"
        # le second respStmt: qui a préparé produit l'encodage XML
        respStmt = etree.SubElement(
            titleStmt
            , "respStmt"
            , nsmap=NS_TEI
        )
        etree.SubElement(
            respStmt
            , "resp"
            , nsmap=NS_TEI
        ).text="Transformation automatique du texte brut vers le XML-TEI"
        etree.SubElement(
            respStmt
            , "persName"
            , nsmap=NS_TEI
        ).text='Les participant.e.s à l\'atelier "Modéliser et exploiter des corpus textuels" (ENS-PSL, campus d\'Ulm)'
        
        # on passe ensuite au `publicationStmt` , 
        # qui décrit la publication du document XML
        publicationStmt = tree.xpath(".//tei:publicationStmt", namespaces=NS_TEI)[0]
        # `publisher`: l'institution éditant le document
        etree.SubElement(
            publicationStmt
            , "publisher"
            , nsmap=NS_TEI
        ).text="ENS-PSL"
        # `pubPlace`: le lieu de publication
        etree.SubElement(
            publicationStmt
            , "pubPlace"
            , nsmap=NS_TEI
        ).text="Paris (France)"
        # `date`: date de publication, soit maintenant
        etree.SubElement(
            publicationStmt
            , "date"
            , nsmap=NS_TEI
        ).text=str(datetime.datetime.utcnow())
        
        # le dernier élément du `fileDesc`: le `sourceDesc` est créé, 
        # qui contient une description bibliographique basique (complétée
        # par éléments du `profileDesc`: le `correspDesc`
        sourceDesc = tree.xpath(".//tei:sourceDesc", namespaces=NS_TEI)[0]
        bibl = etree.SubElement(
            sourceDesc
            , "bibl"
            , type=lettre["typology"]
            , nsmap=NS_TEI
        )
        etree.SubElement(
            bibl
            , "author"
            , nsmap=NS_TEI
        ).text = lettre["metadata"]["sender"]
        etree.SubElement(
            bibl
            , "title"
            , nsmap=NS_TEI
        ).text = lettre["title"]
        etree.SubElement(
            bibl
            , "date"
            , nsmap=NS_TEI
        ).text = str(lettre["metadata"]["date"])
        msIdentifier = etree.SubElement(
            bibl
            , "msIdentifier"
            , nsmap=NS_TEI
        )
        if re.search("(INHA|Rodin)", lettre["metadata"]["source"]):
            institution_name = ("INHA" if re.search("^INHA", lettre["metadata"]["source"]) 
                                       else "Musée Rodin")
        else:
            institution_name = "Lieu de conservation inconnu"
        etree.SubElement(
            msIdentifier
            , "institution"
            , nsmap=NS_TEI
        ).text = institution_name
        etree.SubElement(
            msIdentifier
            , "idno"
            , nsmap=NS_TEI
        ).text = lettre["metadata"]["source"]
        
        # ensuite, on passe à l'encodingDesc: description des normes d'encodage suivies
        encodingDesc = tree.xpath(".//tei:encodingDesc", namespaces=NS_TEI)[0]
        editorialDecl = etree.SubElement(
            encodingDesc
            , "editorialDecl"
            , nsmap=NS_TEI
        )
        etree.SubElement(
            editorialDecl
            , "p"
            , nsmap=NS_TEI
        ).text = ("Production de l'encodage XML réalisée automatiquement"
                  + " avec la librairie LXML de Python à partir d'une version"
                  + " en texte brut de la correspondance de Matsukata")
        projectDesc = etree.SubElement(
            encodingDesc
            , "projectDesc"
            , nsmap=NS_TEI
        )
        etree.SubElement(
            projectDesc
            , "p"
            , nsmap=NS_TEI
        ).text = 'L\'atelier "Modéliser et exploiter des corpus textuels" a donné lieu à cet encodage.'
        
        # ensuite, dans le `profileDesc`, on ajoute du contenu au 
        # `correspDesc` qui décrit la correspondance
        # cf: https://journals.openedition.org/jtei/1433
        correspDesc = tree.xpath(".//tei:correspDesc", namespaces=NS_TEI)[0]
        # 1e action contenant le nom de l'expéditeurice
        correspAction = etree.SubElement(
            correspDesc
            , "correspAction"
            , type="sent"
            , nsmap=NS_TEI
        )
        etree.SubElement(
            correspAction
            , "persName"
            , nsmap=NS_TEI
        ).text = lettre["metadata"]["sender"]
        etree.SubElement(
            correspAction
            , "placeName"
            , nsmap=NS_TEI
        ).text = lettre["metadata"]["sender_place"]
        etree.SubElement(
            correspAction
            , "date"
            , when = str(lettre["metadata"]["date"])
            , nsmap=NS_TEI
        ).text = str(lettre["metadata"]["date"])
        correspAction = etree.SubElement(
        # seconde action contenant le nom du/de la destinatairice
            correspDesc
            , "correspAction"
            , type="received"
            , nsmap=NS_TEI
        )
        etree.SubElement(
            correspAction
            , "persName"
            , nsmap=NS_TEI
        ).text = lettre["metadata"]["recipient"]
        etree.SubElement(
            correspAction
            , "placeName"
            , nsmap=NS_TEI
        ).text = lettre["metadata"]["recipient_place"]
        
        # pour finir, on a plus qu'à créer le corps texte.
        body = tree.xpath(".//tei:body", namespaces=NS_TEI)[0]
        # créer un élément `opener` avec un `salute` contenant la formule de politesse
        if lettre["body"]["greetings"]:
            opener = etree.SubElement(
                body
                , "opener"
                , nsmap=NS_TEI
            )
            etree.SubElement(
                opener
                , "salute"
                , nsmap=NS_TEI
            ).text = lettre["body"]["greetings"]
        # ensuite, le corps de la lettre: un paragraphe par item dans `lettre["body"]["body"]`
        for p in lettre["body"]["body"]:
            etree.SubElement(
                body
                , "p"
                , nsmap=NS_TEI
            ).text = p
        # on crée un `closer` contenant 
        # - la formule de politesse dans un `salute` 
        # - la signature dans un `signed`
        if lettre["body"]["closing"] != "" or lettre["body"]["signature"] != "":
            closer = etree.SubElement(
                body
                , "closer"
                , nsmap=NS_TEI
            )
            if lettre["body"]["closing"] != "":
                etree.SubElement(
                    closer
                    , "salute"
                    , nsmap=NS_TEI
                ).text = lettre["body"]["closing"]
            if lettre["body"]["signature"] != "":
                etree.SubElement(
                    closer
                    , "signed"
                    , nsmap=NS_TEI
                ).text = lettre["body"]["signature"]
        # enfin, le post-scriptum
        if lettre["body"]["postscript"] != "":
            postscript = etree.SubElement(
                body
                , "postscript"
                , nsmap=NS_TEI
            )
            etree.SubElement(
                postscript
                , "p"
                , nsmap=NS_TEI
            ).text = lettre["body"]["postscript"]
        
        # on nettoie le fichier: LXML a ajouté l'espace de noms à chaque
        # élement créé, il faut le retirer: l'espace de nom sera seulement
        # indiqué à la racine du document xml. on garde seulement le `xmlns`
        # de la racine, qui pointe vers l'URI canonique de la TEI
        for el in tree.getiterator():
            if (el.tag != "{http://www.tei-c.org/ns/1.0}TEI"
                and not (
                    isinstance(el, etree._Comment) 
                    or isinstance(el, etree._ProcessingInstruction)
                )
            ):
                el.tag = etree.QName(el).localname  # strip namespaces
                etree.strip_attributes(el, "xmlns")

        etree.cleanup_namespaces(tree)
        
        # on vérifie que le document est valide
        # valid = RNG.validate(tree)
        # if not valid:
        #     print(RNG.error_log)
        
        # enfin, on enregistre le fichier. 
        etree.ElementTree(tree.getroot()).write(
            os.path.join(XML, f"{idx}.xml")
            , pretty_print=True
        )
        
    return
    
    
def pipeline():
    """
    chaîne de conversion de la correspondance Matsutaka 
    depuis le format .txt vers .xml
    """
    # ouvrir le fichier texte avec `with open()`, lire son contenu et l'assigner
    # à la variable `corpus`
    with open(os.path.join(TXT, "correspondance_matsutaka.txt"), mode="r") as fh:
        corpus = fh.read()
    
    # supprimer les espaces insécables du texte
    corpus = corpus.replace("\xa0", " ")
    
    # structurer le texte sous la forme de liste imriquée
    # (1 liste = 1 lettre.)
    corpus = corpussplit(corpus)
    
    # "faire sens" de `corpus`: produire une structuration
    # sémantique en déterminant et explicitant le sens des 
    # différentes parties/sous-parties de corpus
    corpus = makesense(corpus)
    
    # traduire cette structuration sémantique en xml-tei
    corpus2tei(corpus)

    return


if __name__ == "__main__":
    pipeline()
    
    
    