import json

import pytest

from controller.movie import (
    ANCRAGE_COMMENCEMENT,
    CYCLE_HORLOGE_MS,
    GameBuild,
    IncompatibleMovie,
    Movie,
    MovieError,
    StartConditions,
    TapInput,
    load_movie,
    save_movie,
    verifier_rejouable,
)

BUILD = GameBuild(
    package="com.zeptolab.thieves.google",
    version_name="2.83",
    version_code=4755263,
)


def make_movie(**overrides) -> Movie:
    fields = dict(
        game=BUILD,
        dt=1.0 / 60.0,
        run_kind="own_base_test",
        run_label="ma base",
        run_frames=300,
        start=StartConditions(hero_x=160.0, hero_y=548.0),
        inputs=[TapInput(frame=42), TapInput(frame=71)],
    )
    fields.update(overrides)
    return Movie(**fields)


def test_aller_retour_sur_disque(tmp_path):
    path = tmp_path / "run.json"
    original = make_movie()

    save_movie(original, path)
    reloaded = load_movie(path, expected_version_code=4755263)

    assert reloaded == original


def test_le_fichier_ecrit_porte_les_conditions_de_depart(tmp_path):
    path = tmp_path / "run.json"
    save_movie(make_movie(), path)

    data = json.loads(path.read_text(encoding="utf8"))

    assert data["version"] == 2
    assert data["anchor"] == "commencement"
    assert data["start"]["relaunch"] is True
    assert data["start"]["hero_x"] == 160.0
    assert data["start"]["hero_y"] == 548.0
    assert data["clock"]["cycle_ms"] == [16, 17, 17]
    assert data["run"]["frames"] == 300
    assert data["inputs"] == [{"frame": 42}, {"frame": 71}]


def test_refus_d_une_autre_version_de_jeu(tmp_path):
    path = tmp_path / "run.json"
    save_movie(make_movie(), path)

    with pytest.raises(IncompatibleMovie) as excinfo:
        load_movie(path, expected_version_code=9999999)

    assert "4755263" in str(excinfo.value)


def test_refus_d_une_version_de_format_inconnue(tmp_path):
    path = tmp_path / "vieux.json"
    data = json.loads(json.dumps(make_movie().to_dict()))
    data["version"] = 1
    path.write_text(json.dumps(data), encoding="utf8")

    with pytest.raises(MovieError) as excinfo:
        load_movie(path, expected_version_code=4755263)

    assert "version 1" in str(excinfo.value)


def test_refus_d_un_fichier_sans_champ_version(tmp_path):
    path = tmp_path / "casse.json"
    path.write_text(json.dumps({"inputs": []}), encoding="utf8")

    with pytest.raises(MovieError):
        load_movie(path, expected_version_code=4755263)


def test_refus_d_un_ancrage_inconnu():
    with pytest.raises(MovieError) as excinfo:
        make_movie(anchor="manual")

    assert "manual" in str(excinfo.value)


def test_refus_d_un_cycle_d_horloge_vide():
    with pytest.raises(MovieError):
        make_movie(clock_cycle_ms=())


def test_refus_d_un_nombre_d_images_nul():
    with pytest.raises(MovieError):
        make_movie(run_frames=0)


def test_refus_des_frames_negatives():
    with pytest.raises(MovieError):
        make_movie(inputs=[TapInput(frame=-1)])


def test_refus_des_frames_en_double():
    with pytest.raises(MovieError):
        make_movie(inputs=[TapInput(frame=10), TapInput(frame=10)])


def test_les_entrees_sont_triees_par_frame():
    movie = make_movie(inputs=[TapInput(frame=90), TapInput(frame=12)])
    assert [i.frame for i in movie.inputs] == [12, 90]


def test_refus_d_un_dt_nul_ou_negatif():
    with pytest.raises(MovieError):
        make_movie(dt=0.0)


def test_ajout_d_un_saut_efface_l_empreinte():
    movie = make_movie(inputs=[], fingerprint="sha256:peu importe")
    movie.add_tap(30)
    movie.add_tap(10)

    assert [i.frame for i in movie.inputs] == [10, 30]
    assert movie.fingerprint is None


def test_annulation_du_dernier_saut():
    movie = make_movie(inputs=[])
    movie.add_tap(10)
    movie.add_tap(30)
    movie.undo_last_tap()

    assert [i.frame for i in movie.inputs] == [10]


def test_annulation_sur_film_vide_ne_casse_pas():
    movie = make_movie(inputs=[])
    movie.undo_last_tap()
    assert movie.inputs == []


def test_rejouable_sous_les_memes_conditions():
    verifier_rejouable(make_movie(), cycle_ms=CYCLE_HORLOGE_MS)


def test_refus_de_rejouer_sous_un_autre_cycle_d_horloge():
    with pytest.raises(IncompatibleMovie) as excinfo:
        verifier_rejouable(make_movie(), cycle_ms=(17, 17, 17))

    assert "clock" in str(excinfo.value)


def test_refus_de_rejouer_un_film_sans_position_de_depart():
    """Sans elle, on ne saurait pas reconnaitre l'ecran de
    commencement, et l'image 0 pourrait tomber sur un menu."""
    film = make_movie(start=StartConditions())

    with pytest.raises(IncompatibleMovie) as excinfo:
        verifier_rejouable(film, cycle_ms=CYCLE_HORLOGE_MS)

    assert "start position" in str(excinfo.value)


def test_les_conditions_de_depart_par_defaut_sont_celles_du_bit_exact():
    depart = StartConditions()

    assert depart.relaunch is True
    assert depart.tap_demarrage is True
    assert depart.hero_x is None and depart.hero_y is None
    assert ANCRAGE_COMMENCEMENT == "commencement"


def test_refus_d_un_saut_au_dela_de_la_duree_du_film():
    with pytest.raises(MovieError) as excinfo:
        make_movie(run_frames=300, inputs=[TapInput(frame=301)])

    assert "301" in str(excinfo.value)


def test_un_saut_a_la_derniere_image_est_admis():
    """Poser un saut a l'image N puis ecrire le film sans avancer donne
    frame == run_frames. Le tap est emis, il n'a pas eu le temps d'agir sur la
    trace, et le film est legitime."""
    movie = make_movie(run_frames=300, inputs=[TapInput(frame=300)])

    assert [i.frame for i in movie.inputs] == [300]


def test_refus_d_un_cycle_d_horloge_a_valeur_nulle():
    """Le tuple vide declenche l'autre moitie de la garde ; celle-ci verifie
    qu'une valeur invalide noyee dans un cycle par ailleurs correct est bien
    refusee."""
    with pytest.raises(MovieError):
        make_movie(clock_cycle_ms=(16, 0, 17))


def test_ecriture_dans_un_dossier_qui_n_existe_pas(tmp_path):
    chemin = tmp_path / "films" / "sous_dossier" / "run.json"

    save_movie(make_movie(), chemin)

    assert chemin.is_file()
