import pytest

from controller.trace import (
    Etat,
    TraceError,
    decode,
    decrire_divergence,
    empreinte,
    encode,
    est_significative,
    premiere_divergence,
)

# Valeurs choisies exactement representables en float32, pour que l'aller-retour
# d'encodage soit une egalite stricte et non une comparaison approchee.
CHUTE = [
    Etat(frame=0, x=45.5, y=500.0, vx=0.0, vy=0.0),
    Etat(frame=1, x=45.5, y=502.0, vx=0.0, vy=2.0),
    Etat(frame=2, x=45.5, y=504.5, vx=0.0, vy=2.5),
]

IMMOBILE = [
    Etat(frame=n, x=45.4374, y=548.5602, vx=0.0, vy=0.0) for n in range(300)
]


def test_aller_retour_encodage():
    assert decode(encode(CHUTE)) == CHUTE


def test_decode_refuse_une_longueur_invalide():
    with pytest.raises(TraceError) as excinfo:
        decode(b"\x00" * 21)
    assert "20" in str(excinfo.value)


def test_decode_lit_le_numero_de_frame():
    assert decode(encode(CHUTE))[2].frame == 2


def test_empreinte_stable():
    assert empreinte(encode(CHUTE)) == empreinte(encode(CHUTE))


def test_empreinte_change_si_un_flottant_change():
    autre = list(CHUTE)
    autre[1] = Etat(frame=1, x=45.5, y=502.001, vx=0.0, vy=2.0)
    assert empreinte(encode(CHUTE)) != empreinte(encode(autre))


def test_empreinte_prefixee():
    assert empreinte(b"").startswith("sha256:")


def test_pas_de_divergence_entre_traces_identiques():
    assert premiere_divergence(CHUTE, CHUTE) is None


def test_divergence_designe_le_premier_enregistrement_different():
    autre = list(CHUTE)
    autre[2] = Etat(frame=2, x=45.5, y=504.75, vx=0.0, vy=2.75)
    assert premiere_divergence(CHUTE, autre) == 2


def test_divergence_de_longueur():
    assert premiere_divergence(CHUTE, CHUTE[:2]) == 2


def test_description_nomme_l_image_et_les_deux_valeurs():
    autre = list(CHUTE)
    autre[2] = Etat(frame=2, x=45.5, y=504.75, vx=0.0, vy=2.75)
    message = decrire_divergence(CHUTE, autre)
    assert "frame 2" in message
    assert "504.5" in message and "504.75" in message


def test_description_sans_divergence():
    assert decrire_divergence(CHUTE, CHUTE) == "no divergence"


def test_une_trace_immobile_n_est_pas_significative():
    assert est_significative(IMMOBILE) is False


def test_une_trace_qui_bouge_est_significative():
    mouvement = [
        Etat(frame=n, x=45.4374, y=500.0 + n, vx=0.0, vy=1.0) for n in range(40)
    ]
    assert est_significative(mouvement) is True


from controller.trace import (
    TOLERANCE_PX,
    amplifie,
    classer_modele,
    concordent,
    ecart_maximal,
    ecart_translate,
    ecarts,
)

DROITE = [Etat(frame=n, x=10.0, y=100.0 + n, vx=0.0, vy=1.0) for n in range(40)]


def _decalee(ecart_par_image):
    return [Etat(frame=e.frame, x=e.x, y=e.y + ecart_par_image * e.frame,
                 vx=e.vx, vy=e.vy) for e in DROITE]


def test_ecarts_nuls_entre_traces_identiques():
    assert ecarts(DROITE, DROITE) == [0.0] * len(DROITE)


def test_ecart_maximal_designe_l_image_et_la_valeur():
    autre = list(DROITE)
    autre[7] = Etat(frame=7, x=10.0, y=107.5, vx=0.0, vy=1.0)
    indice, valeur = ecart_maximal(DROITE, autre)
    assert indice == 7
    assert valeur == pytest.approx(0.5)


def test_concordent_sous_la_tolerance():
    autre = list(DROITE)
    autre[3] = Etat(frame=3, x=10.0, y=103.0 + TOLERANCE_PX / 2, vx=0.0, vy=1.0)
    assert concordent(DROITE, autre) is True


def test_ne_concordent_pas_au_dela_de_la_tolerance():
    autre = list(DROITE)
    autre[3] = Etat(frame=3, x=10.0, y=103.0 + TOLERANCE_PX * 10, vx=0.0, vy=1.0)
    assert concordent(DROITE, autre) is False


def test_des_longueurs_differentes_ne_concordent_pas():
    assert concordent(DROITE, DROITE[:20]) is False


def test_amplifie_detecte_un_ecart_qui_grandit():
    # L'ecart croit avec le numero d'image : c'est le cas qui condamne un TAS.
    assert amplifie(DROITE, _decalee(0.001)) is True


def test_amplifie_est_faux_pour_un_ecart_constant():
    constant = [Etat(frame=e.frame, x=e.x, y=e.y + 0.002, vx=e.vx, vy=e.vy)
                for e in DROITE]
    assert amplifie(DROITE, constant) is False


def test_amplifie_est_faux_entre_traces_identiques():
    assert amplifie(DROITE, DROITE) is False


from controller.trace import (  # noqa: E402
    GRAVITE_PX_PAR_IMAGE2,
    images_doublees,
    images_figees,
)


def _trace(positions_y, x=786.5623779296875):
    """Construit une trace comme le fait l'agent : la vitesse EST la difference
    de position avec l'image precedente enregistree (voir agent/record.js)."""
    etats, precedent = [], None
    for numero, y in enumerate(positions_y):
        vy = 0.0 if precedent is None else y - precedent
        etats.append(Etat(frame=numero, x=x, y=y, vx=0.0, vy=vy))
        precedent = y
    return etats


# Releve le 2026-09-18 sur le temoin : six images consecutives de chute, dont
# les differences de vitesse valent la gravite mesuree a 1e-5 pres.
CHUTE_PROPRE = [505.071808, 499.270874, 493.888306, 488.924042,
                484.378113, 480.250519, 476.541260]

# Meme chute, mais l'image qui vaudrait 480.250519 a recu DEUX pas de physique
# et a saute directement a 476.541260. Releve tel quel sur la capture cadencee
# a 20 ms, images 36 a 38.
CHUTE_DOUBLEE = [505.071808, 499.270874, 493.888306, 488.924042,
                 484.378113, 476.541260, 473.250305]

# Glissement le long du mur : vitesse constante de 2,088318 px/image.
GLISSEMENT = [466.389280 + 2.088318 * n for n in range(10)]


def test_gravite_mesuree_est_exposee():
    assert GRAVITE_PX_PAR_IMAGE2 == pytest.approx(0.4183, abs=1e-4)


def test_aucune_image_figee_dans_une_chute_propre():
    assert images_figees(_trace(CHUTE_PROPRE)) == []


def test_une_image_figee_en_plein_vol_est_reperee():
    # Le jeu a rendu l'image sans avancer sa simulation : la position ne bouge
    # pas, puis la chute reprend exactement ou elle en etait. Forme relevee
    # telle quelle sur le temoin du 2026-09-18, images 31 a 35.
    fige = [548.562378, 548.562378] + [505.071808] + CHUTE_PROPRE
    assert images_figees(_trace(fige)) == [3]


def test_un_heros_au_repos_n_est_pas_une_image_figee():
    assert images_figees(_trace([548.5623779296875] * 300)) == []


def test_l_arret_en_fin_de_course_n_est_pas_une_image_figee():
    assert images_figees(_trace(CHUTE_PROPRE + [476.541260] * 50)) == []


def test_aucune_image_doublee_dans_une_chute_propre():
    assert images_doublees(_trace(CHUTE_PROPRE)) == []


def test_une_image_doublee_en_chute_est_reperee():
    assert images_doublees(_trace(CHUTE_DOUBLEE)) == [5]


def test_aucune_image_doublee_dans_un_glissement_propre():
    assert images_doublees(_trace(GLISSEMENT)) == []


def test_une_image_doublee_pendant_le_glissement_est_reperee():
    # Vitesse constante : l'image doublee avance de deux fois le pas. C'est le
    # cas que la detection par la gravite seule laissait passer.
    doublee = GLISSEMENT[:5] + [g + 2.088318 for g in GLISSEMENT[5:]]
    assert images_doublees(_trace(doublee)) == [5]


def test_l_impulsion_du_saut_n_est_pas_une_image_doublee():
    # Le saut fait bondir la vitesse de 0 a -43,49 : une discontinuite, pas un
    # pas de physique en trop. La confondre ferait crier au loup a chaque saut.
    saut = [548.562378, 548.562378, 505.071808] + CHUTE_PROPRE[1:]
    assert images_doublees(_trace(saut)) == []


# --- amplifie() : un transitoire qui decroit n'est pas une amplification ---

# Profil releve le 2026-09-18 entre deux temoins : l'ecart reste exactement
# celui des positions de depart pendant 288 images, puis une bosse apparait et
# se resorbe geometriquement, d'un facteur 0,8 par image.
def _profil_bosse_amortie():
    ecart = [0.000122] * 288
    bosse = 0.009377
    for _ in range(12):
        ecart.append(bosse)
        bosse *= 0.8
    return ecart


def _paire_depuis_profil(profil):
    base = [Etat(frame=n, x=10.0, y=100.0 + n, vx=0.0, vy=1.0)
            for n in range(len(profil))]
    autre = [Etat(frame=e.frame, x=e.x, y=e.y + profil[e.frame],
                  vx=e.vx, vy=e.vy) for e in base]
    return base, autre


def test_amplifie_est_faux_pour_une_bosse_qui_se_resorbe():
    a, b = _paire_depuis_profil(_profil_bosse_amortie())
    assert amplifie(a, b) is False


def test_amplifie_reste_vrai_pour_une_croissance_soutenue():
    croissance = [0.000122 * (1.02 ** n) for n in range(300)]
    a, b = _paire_depuis_profil(croissance)
    assert amplifie(a, b) is True


def etats(*positions, depart=0):
    """Une trace fabriquee : une position par image, vitesse non nulle."""
    faits = []
    precedente = None
    for rang, (x, y) in enumerate(positions):
        vx = 0.0 if precedente is None else x - precedente[0]
        vy = 0.0 if precedente is None else y - precedente[1]
        faits.append(Etat(frame=depart + rang, x=x, y=y, vx=vx, vy=vy))
        precedente = (x, y)
    return faits


def test_deux_traces_identiques_ne_s_ecartent_pas():
    a = etats((10.0, 0.0), (11.0, 1.0), (12.0, 3.0))

    assert ecart_translate(a, a, decalage=0) == 0.0


def test_une_trace_recalee_d_une_image_recouvre_l_autre():
    """Le modele A : la meme trajectoire, jouee une image plus tard."""
    a = etats((10.0, 0.0), (11.0, 1.0), (12.0, 3.0), (13.0, 6.0))
    b = etats((99.0, 99.0), (10.0, 0.0), (11.0, 1.0), (12.0, 3.0))

    assert ecart_translate(a, b, decalage=1) == 0.0


def test_sans_recalage_la_meme_paire_diverge():
    """Le meme couple compare sans recalage : c est ce que mesurerait
    ecart_maximal, et c est pourquoi il ne repond pas a la question."""
    a = etats((10.0, 0.0), (11.0, 1.0), (12.0, 3.0), (13.0, 6.0))
    b = etats((99.0, 99.0), (10.0, 0.0), (11.0, 1.0), (12.0, 3.0))

    assert ecart_translate(a, b, decalage=0) == 99.0


def test_le_recalage_se_fait_aussi_vers_l_arriere():
    a = etats((10.0, 0.0), (11.0, 1.0), (12.0, 3.0))
    b = etats((11.0, 1.0), (12.0, 3.0), (77.0, 77.0))

    assert ecart_translate(a, b, decalage=-1, depuis=1) == 0.0


def test_depuis_ignore_les_images_qui_precedent():
    """Avant le decollage les deux traces different : la question ne porte
    que sur ce qui suit."""
    a = etats((0.0, 0.0), (11.0, 1.0), (12.0, 3.0))
    b = etats((50.0, 50.0), (11.0, 1.0), (12.0, 3.0))

    assert ecart_translate(a, b, decalage=0) == 50.0
    assert ecart_translate(a, b, decalage=0, depuis=1) == 0.0


def test_un_recouvrement_vide_ne_rend_pas_zero():
    """Rendre 0.0 ferait passer l absence de mesure pour une concordance."""
    a = etats((10.0, 0.0), (11.0, 1.0))

    assert ecart_translate(a, a, decalage=5) is None


def test_des_ecarts_sous_la_tolerance_font_le_modele_a():
    assert classer_modele([0.0, 0.001, 0.005]) == "A"


def test_un_seul_ecart_au_dela_suffit_a_faire_le_modele_b():
    """Le pire ecart decide : une seule trajectoire de forme differente
    prouve que la forme depend de l image de decollage."""
    assert classer_modele([0.0, 0.001, 12.5]) == "B"


def test_le_bord_exact_de_la_tolerance_reste_le_modele_a():
    assert classer_modele([TOLERANCE_PX]) == "A"


def test_sans_aucun_ecart_mesurable_il_n_y_a_pas_de_verdict():
    """Repondre A faute de contre-exemple ferait renoncer a une dimension de
    recherche sans preuve."""
    assert classer_modele([None, None]) is None


def test_un_seul_ecart_mesurable_suffit_a_trancher():
    assert classer_modele([None, 12.5]) == "B"


def test_la_tolerance_se_regle():
    assert classer_modele([5.0], tolerance=10.0) == "A"
    assert classer_modele([5.0], tolerance=1.0) == "B"
