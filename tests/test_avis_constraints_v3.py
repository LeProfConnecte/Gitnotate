"""V3-D : non-surclassement des depots a coeur prive et citations par affirmation.

Fixtures synthétiques, sauf la phrase explicite de README "signal engine...
remain private" reprise comme exemple public ; aucune requête réseau/API.
"""
import json

import pytest

import avis_v3 as avis


def json_review(candidate, *, score, verdict, quote=None, constraints=None):
    if quote is None:
        facts = []
    else:
        facts = [{
            "affirmation": "Le dépôt décrit la fonctionnalité citée.",
            "preuve": quote,
        }]
    return json.dumps({"avis": [{
        "id": candidate.reference, "adequation": score, "verdict": verdict,
        "raison": "Candidat à comparer aux exigences fonctionnelles concrètes.",
        "constats": facts, "contraintes": constraints or [],
    }]}, ensure_ascii=False)


def condition(key, status, evidence="", reason="Statut établi à partir des données reçues."):
    return {"id": key, "etat": status, "raison": reason, "preuve": evidence}


PRIVATE_README = (
    "This repo gives consumer-side webhook examples: receive signal events, "
    "verify them, and route them into your own dashboards, alerts, sheets, "
    "and AI agents. All examples use fictional symbols. "
    "The signal engine, selection formulas, weights, thresholds, and "
    "production infrastructure remain private. "
    "MIT applies to this repository's public materials. "
    "It does not grant access to the private engine."
)


@pytest.fixture
def private_repo():
    return avis.Candidate(
        "R1", "demo/stock-signal",
        "Webhooks, dashboards and swing-trade signal automation examples.",
        "market automation", PRIVATE_README, "", "MIT")


def test_contraintes_detectees_explicitement():
    names = avis.detect_constraints(
        "Je veux un outil open source, en local, gratuit, sans abonnement et autonome")
    assert names == ["open_source", "local", "gratuit", "sans_abonnement", "independant"]
    assert avis.detect_constraints("automatiser une veille financière") == []
    assert avis.detect_constraints("outil open-source hors ligne") == ["open_source", "local"]
    assert avis.detect_constraints("free of charge without subscription") == [
        "gratuit", "sans_abonnement"]


def test_phrase_privee_identifiee_sans_licence_trompeuse(private_repo):
    evidence = avis.private_core_evidence(private_repo)
    assert "signal engine" in evidence
    assert "remain private" in evidence
    assert len(evidence) <= 180


def test_open_source_reclasse_moteur_prive_meme_si_modele_affirme_mit(private_repo):
    payload = json_review(
        private_repo, score=3, verdict="repond_au_besoin",
        quote="receive signal events, verify them, and route them into your own dashboards",
        constraints=[condition("open_source", "satisfait",
                               "Licence SPDX : MIT",
                               "La licence MIT confirme une ouverture totale du moteur.")])
    result = avis.parse_output(payload, [private_repo], ["open_source"])[0]
    assert result["adequation"] <= 1
    assert result["verdict"] == "dependance_proprietaire"
    assert result["contraintes"][0]["etat"] == "non_satisfait"
    assert result["contraintes"][0]["ancrage_verifie"] is True
    assert "remain private" in result["contraintes"][0]["preuve"]
    assert any("moteur" in c["affirmation"].lower() or "composant" in c["affirmation"].lower()
               for c in result["constats"])
    assert result["ajustements"]


def test_private_core_is_not_automatically_disqualifying_without_requirement(private_repo):
    payload = json_review(
        private_repo, score=2, verdict="composant_partiel",
        quote="receive signal events, verify them, and route them into your own dashboards")
    result = avis.parse_output(payload, [private_repo])[0]
    assert result["adequation"] == 2
    assert result["verdict"] == "composant_partiel"
    assert result["ajustements"] == []


def test_licence_spdx_seule_ne_prouve_pas_ouverture_coeur():
    candidate = avis.Candidate(
        "R1", "demo/alerts",
        "Automated financial monitoring dashboard with alerts.",
        "finance", "Automated financial monitoring dashboard with alerts.", "", "MIT")
    payload = json_review(
        candidate, score=3, verdict="repond_au_besoin",
        quote="Automated financial monitoring dashboard with alerts.",
        constraints=[condition("open_source", "satisfait", "Licence SPDX : MIT")])
    result = avis.parse_output(payload, [candidate], ["open_source"])[0]
    assert result["adequation"] == 2
    assert result["verdict"] == "composant_partiel"
    assert result["contraintes"][0]["etat"] == "non_verifie"
    assert result["contraintes"][0]["preuve"] == ""


def test_non_verifie_ne_permet_pas_de_verdict_entierement_conforme():
    candidate = avis.Candidate(
        "R1", "demo/alert-tool",
        "Automated analytics and financial dashboards.",
        "", "", "")
    payload = json_review(
        candidate, score=3, verdict="repond_au_besoin",
        quote="Automated analytics and financial dashboards.",
        constraints=[condition("sans_abonnement", "non_verifie",
                               "", "Tarif et conditions contractuelles inconnus.")])
    result = avis.parse_output(payload, [candidate], ["sans_abonnement"])[0]
    assert result["adequation"] == 2
    assert result["verdict"] == "composant_partiel"


def test_non_satisfait_plafonne_note_a_un():
    candidate = avis.Candidate(
        "R1", "demo/cloud-api",
        "Cloud-only analytics API with monthly subscription.",
        "", "", "")
    payload = json_review(
        candidate, score=3, verdict="repond_au_besoin",
        quote="Cloud-only analytics API with monthly subscription.",
        constraints=[condition("sans_abonnement", "non_satisfait",
                               "Cloud-only analytics API with monthly subscription.")])
    result = avis.parse_output(payload, [candidate], ["sans_abonnement"])[0]
    assert result["adequation"] == 1
    assert result["verdict"] != "repond_au_besoin"


def test_citation_d_autre_depot_refusee(private_repo):
    other = avis.Candidate("R2", "demo/else", "Color palette manager.", "",
                           "User interface design tokens and components.", "")
    payload = json.dumps({"avis": [
        {"id": "R1", "adequation": 2, "verdict": "composant_partiel",
         "raison": "Une intégration de signal paraît réutilisable.",
         "constats": [{"affirmation": "Gère les couleurs d'interface.",
                      "preuve": "User interface design tokens and components."}],
         "contraintes": []},
        {"id": "R2", "adequation": 0, "verdict": "hors_sujet",
         "raison": "Aucun lien avec les signaux boursiers.",
         "constats": [], "contraintes": []},
    ]}, ensure_ascii=False)
    with pytest.raises(avis.AvisError, match="Citation IA absente"):
        avis.parse_output(payload, [private_repo, other])


def test_citation_raccourcie_ou_absente_refusee():
    candidate = avis.Candidate(
        "R1", "demo/finance", "Automated financial dashboards.", "", "", "")
    for quote in ("", "Financial", "Fabricated market signals are implemented here."):
        payload = json_review(
            candidate, score=3, verdict="repond_au_besoin",
            quote=quote)
        with pytest.raises(avis.AvisError):
            avis.parse_output(payload, [candidate])


def test_toutes_les_contraintes_declares_obligatoires():
    candidate = avis.Candidate(
        "R1", "demo/finance", "Automated financial dashboards.", "", "", "")
    payload = json_review(
        candidate, score=2, verdict="composant_partiel",
        quote="Automated financial dashboards.")
    with pytest.raises(avis.AvisError, match="contraintes"):
        avis.parse_output(payload, [candidate], ["open_source"])


def test_aucune_note_favorable_sans_constats_cites():
    candidate = avis.Candidate(
        "R1", "demo/unknown", "Automated financial dashboards.", "", "", "")
    payload = json_review(candidate, score=2, verdict="composant_partiel")
    with pytest.raises(avis.AvisError, match="citations"):
        avis.parse_output(payload, [candidate])


def test_contraintes_autres_que_open_source_ne_sont_pas_inventees():
    candidate = avis.Candidate(
        "R1", "demo/tool", "CLI for financial news.",
        "", "Command line utility to monitor financial news.", "")
    payload = json_review(
        candidate, score=2, verdict="composant_partiel",
        quote="Command line utility to monitor financial news.")
    outcome = avis.parse_output(payload, [candidate])[0]
    assert outcome["contraintes"] == []
    assert outcome["verdict"] == "composant_partiel"
