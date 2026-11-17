#!/usr/bin/env python3
"""FISHWATCH — veille RSS et surveillance d'une page officielle, sans IA ni API payante.

Lancement : python collect.py
Test isolé : python -m unittest discover -s tests -v
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from xml.etree import ElementTree as ET

BASE = Path(__file__).resolve().parent
TZ = ZoneInfo("Europe/Paris")
USER_AGENT = "FISHWATCH-educational/1.0 (RSS reader; no scraping of restricted pages)"
MAX_DAYS = 45
MAX_RECORDS = 500

# Mots-clés vérifiables et adaptables dans le dossier : ils ne prouvent pas un fait.
GEO = ["haute savoie", "haut savoyard", "annecy", "thonon", "chablais", "arve", "cheran", "dranse", "filliere", "foron", "fier", "leman", "cluse", "bonneville", "sallanches", "faverges", "rumilly", "sevrier", "seynod", "seysse", "la roche sur foron"]
WATER = ["peche", "pecheur", "poisson", "truite", "salmonide", "piscicole", "aquatique", "riviere", "cours d eau", "lac", "fleuve", "arve", "cheran", "dranse", "fier", "debit", "crue", "etiage", "secheresse", "qualite de l eau"]
COMMERCIAL = ["promotion", "soldes", "code promo", "comparatif canne", "acheter une canne", "leurres pas cher", "poisson d avril", "recette de cuisine"]

# Une preuve réglementaire et une simple rumeur n'ont pas la même portée.
INDICATORS = {
    "PIR-1": [
        ("Projet ou consultation de texte", ["consultation", "projet d arrete", "enquete publique"]),
        ("Arrêté ou modification de règle", ["arrete", "reglement", "reglementation", "legislation", "taille minimale", "quota", "nouvelle regle"]),
        ("Restriction de pêche", ["interdiction de peche", "fermeture de la peche", "reserve de peche", "restriction de peche", "ouverture de la peche"]),
    ],
    "PIR-2": [
        ("Sécheresse ou étiage", ["secheresse", "etiage", "assec", "restriction d eau", "alerte secheresse"]),
        ("Crue ou inondation", ["crue", "inondation", "vigilance crues", "debordement"]),
        ("Débit ou température", ["debit", "temperature de l eau", "niveau d eau", "hydrologie", "hydrologique"]),
    ],
    "PIR-3": [
        ("Pollution de milieu aquatique", ["pollution", "contamination", "rejet toxique", "qualite de l eau"]),
        ("Mortalité ou maladie piscicole", ["mortalite", "poissons morts", "maladie des poissons", "epidemie piscicole"]),
        ("Étude ou suivi d'espèces", ["suivi piscicole", "population de truites", "population piscicole", "inventaire piscicole", "biodiversite aquatique", "etude sur les salmonides"]),
    ],
}

class PlainText(HTMLParser):
    def __init__(self, main_only=False):
        super().__init__(convert_charrefs=True)
        self.main_only = main_only
        self.main_depth = 0
        self.seen_main = False
        self.ignore = 0
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.seen_main = True
            self.main_depth += 1
        elif self.main_depth and self.main_only:
            self.main_depth += 1
        if tag in {"script", "style", "noscript"}:
            self.ignore += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.ignore = max(0, self.ignore - 1)
        if self.main_only and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data):
        if not self.ignore and (not self.main_only or self.main_depth):
            self.buf.append(data)

    def text(self):
        return " ".join(" ".join(self.buf).split())


def plain(value):
    p = PlainText()
    p.feed(str(value or ""))
    return html.unescape(p.text()).strip()


def norm(value):
    v = unicodedata.normalize("NFKD", str(value or "").lower())
    v = "".join(c for c in v if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", v).strip()


def contains(text, words):
    return any(re.search(r"\b" + re.escape(norm(w)) + r"\b", text) for w in words)


def source_grade(source_url):
    """Cote A-F *préliminaire de la source*, jamais crédibilité du fait."""
    host = (urlparse(source_url or "").hostname or "").lower()
    if host == "gouv.fr" or host.endswith(".gouv.fr") or host.endswith(".ofb.gouv.fr"):
        return "A"
    if host.endswith((".vigicrues.gouv.fr", ".eaufrance.fr")):
        return "A"
    if host == "pechehautesavoie.com" or host.endswith(".pechehautesavoie.com") or host.endswith(".federationpeche.fr"):
        return "B"
    return "F"  # source inconnue : pas de note de fiabilité inventée


def select_category(title, summary):
    t = norm(title + " " + summary)
    if contains(t, COMMERCIAL) or not contains(t, GEO) or not contains(t, WATER):
        return None, None, "Hors périmètre local, sans contexte aquatique, ou publicité"
    best = []
    for pir, indicators in INDICATORS.items():
        matched = [(label, sum(bool(re.search(r"\b"+re.escape(norm(w))+r"\b", t)) for w in phrases)) for label, phrases in indicators]
        candidates = [m for m in matched if m[1] > 0]
        if candidates:
            label, n = max(candidates, key=lambda item: item[1])
            bonus = sum(count for _, count in candidates)
            best.append((bonus, pir, label))
    if not best:
        return None, None, "Aucun indicateur de veille identifié"
    # En cas d'égalité, on respecte l'ordre des PIR ci-dessus ; le tri humain pourra corriger.
    _, pir, indicator = max(best, key=lambda item: item[0])
    return pir, indicator, "Correspondance lexicale vérifiable — à confirmer"


def make_key(url, title):
    # Titre harmonisé pour dédoublonner les mêmes articles issus de plusieurs flux.
    base = norm(re.sub(r"\s+-\s+[^-]{3,70}$", "", title)) or url
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:18]


def entry_date(entry):
    for field in ("published_parsed", "updated_parsed"):
        st = entry.get(field)
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc).astimezone(TZ).date().isoformat()
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(TZ).date().isoformat()
            except (ValueError, TypeError):
                pass
    return datetime.now(TZ).date().isoformat()


def score_record(pir, indicator, grade, novelty=True):
    points = {
        "pir": 3 if pir else 0,
        "indicateur": 3 if indicator else 0,
        "impact_local": 2 if pir else 0,
        "source_primaire_ou_AB": 1 if grade in ("A", "B") else 0,
        "nouveaute": 1 if novelty else 0,
    }
    return sum(points.values()), points


def classify(entry, feed_label, now=None):
    """Retourne une fiche structurée ou None. Jamais une conclusion factuelle validée."""
    now = now or datetime.now(TZ)
    title = plain(entry.get("title", ""))
    summary = plain(entry.get("summary", entry.get("description", "")))
    if not title:
        return None
    pir, indicator, why = select_category(title, summary)
    if not pir:
        return None
    date = entry_date(entry)
    try:
        pub = datetime.fromisoformat(date).date()
        if pub < (now.date() - timedelta(days=MAX_DAYS)) or pub > (now.date() + timedelta(days=1)):
            return None
    except ValueError:
        return None
    publisher = entry.get("source", {})
    publisher = publisher if hasattr(publisher, "get") else {}
    publisher_url = str(publisher.get("href") or "")
    publisher_name = plain(publisher.get("title") or "").strip()
    grade = source_grade(publisher_url)
    score, breakdown = score_record(pir, indicator, grade)
    link = str(entry.get("link") or "").strip()
    if not link.startswith(("https://", "http://")):
        return None
    source_text = publisher_name or "Éditeur non indiqué"
    if "news.google.com" in (urlparse(link).hostname or ""):
        source_text += " (via Google Actualités)"
    return {
        "id": "rss-" + make_key(link, title),
        "date": date,
        "title": title[:300],
        "summary": summary[:650] or "Résumé absent : consulter la publication originale.",
        "source": source_text,
        "publisher_url": publisher_url,
        "source_channel": feed_label,
        "url": link,
        "pir": pir,
        "indicator": indicator,
        "score": score,
        "score_details": breakdown,
        "justification": why,
        "cote": f"{grade}6",  # 6 = crédibilité non évaluable sans vérification humaine.
        "status": "",  # Le dashboard route selon le score, l'humain valide ensuite.
        "confidence": "non evaluee",
        "demo": False,
        "verification": "A vérifier : origine primaire, texte complet, date, effet réel sur le parcours.",
    }


def fetch(url, timeout=20):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/html;q=0.9,*/*;q=0.7"})
    with urlopen(req, timeout=timeout) as response:
        return response.read(2_000_000)  # ne pas télécharger des pièces lourdes


def feed_url(query):
    return "https://news.google.com/rss/search?" + urlencode({"q": query, "hl": "fr", "gl": "FR", "ceid": "FR:fr"})



def parse_feed(raw):
    """Parse RSS 2.0 ou Atom 1.0 uniquement avec la bibliothèque standard."""
    root = ET.fromstring(raw)
    items = []
    if root.tag.rsplit("}", 1)[-1].lower() == "rss" or root.find(".//channel") is not None:
        for node in root.findall(".//channel/item"):
            def read(tag):
                element = node.find(tag)
                return "" if element is None else (element.text or "")
            source = node.find("source")
            items.append({
                "title": read("title"), "summary": read("description"),
                "link": read("link"), "published": read("pubDate"),
                "source": {"title": source.text or "", "href": source.attrib.get("url", "")} if source is not None else {},
            })
    else:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for node in root.findall("a:entry", ns):
            def read(tag):
                element = node.find("a:" + tag, ns)
                return "" if element is None else "".join(element.itertext())
            link_node = node.find("a:link", ns)
            items.append({"title": read("title"), "summary": read("summary") or read("content"),
                          "link": link_node.attrib.get("href", "") if link_node is not None else "",
                          "published": read("published") or read("updated"), "source": {}})
    if not items and root.tag.rsplit("}", 1)[-1].lower() not in ("rss", "feed"):
        raise ValueError("Le document reçu n'est pas un flux RSS/Atom")
    return items

def load_json(path, fallback):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return fallback


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def monitor_pages(config, prior_state, now, fetcher=fetch):
    """Surveille une page ciblée. Une modification n'est jamais présentée comme un arrêté adopté."""
    results, errors = [], []
    state = dict(prior_state)
    for item in config.get("website_monitors", []):
        if not item.get("enabled"):
            continue
        key = item["id"]
        try:
            raw = fetcher(item["url"])
            decoded = raw.decode("utf-8", errors="replace")
            parser = PlainText(main_only=True)
            parser.feed(decoded)
            extracted = parser.text()
            if not parser.seen_main or len(extracted) < 100:
                raise ValueError("Contenu principal <main> absent ou trop court : contrôle manuel")
            digest = hashlib.sha256(norm(extracted).encode()).hexdigest()
            last = state.get(key)
            state[key] = {"hash": digest, "last_checked": now.isoformat(), "url": item["url"]}
            if last and last.get("hash") != digest:
                results.append({
                    "id": "monitor-" + key + "-" + digest[:12], "date": now.date().isoformat(),
                    "title": "Page surveillée modifiée : " + item["label"],
                    "summary": "Une modification technique du contenu principal a été détectée. Sa signification n'est pas vérifiée : comparer la version et consulter les textes officiels.",
                    "source": item["label"], "url": item["url"], "pir": "PIR-1",
                    "indicator": "Modification de page à vérifier", "score": 5,
                    "score_details": {"pir": 3, "indicateur": 0, "impact_local": 0, "source_primaire_ou_AB": 1, "nouveaute": 1},
                    "cote": "A6", "demo": False, "status": "a_analyser", "confidence": "non evaluee",
                    "verification": "Contrôler à la main les différences HTML/texte avant toute conclusion.",
                })
        except Exception as e:
            errors.append(f"Surveillance {key} : {type(e).__name__} : {str(e)[:150]}")
    return results, state, errors


def run(base=BASE, fetcher=fetch, now=None):
    now = now or datetime.now(TZ)
    config = load_json(base / "config/sources.json", {})
    if not config.get("feeds"):
        raise ValueError("Aucun flux dans config/sources.json")
    previous = load_json(base / "veille.json", {"articles": []})
    existing = {x.get("id"): x for x in previous.get("articles", []) if x.get("id") and not x.get("demo")}
    seen_new = set()
    errors, feeds_ok, new_count = [], 0, 0
    for f in config["feeds"]:
        try:
            entries = parse_feed(fetcher(feed_url(f["query"])))
            feeds_ok += 1
            for entry in entries:
                record = classify(entry, f["label"], now)
                if record is None or record["id"] in existing or record["id"] in seen_new:
                    continue
                seen_new.add(record["id"])
                existing[record["id"]] = record
                new_count += 1
        except Exception as e:
            errors.append(f"Flux {f.get('id', '?')} : {type(e).__name__}: {str(e)[:140]}")
    states_path = base / "data/monitor_state.json"
    monitored, new_states, monitor_errors = monitor_pages(config, load_json(states_path, {}), now, fetcher)
    errors.extend(monitor_errors)
    for record in monitored:
        if record["id"] not in existing:
            existing[record["id"]] = record
            new_count += 1
    save_json(states_path, new_states)
    # Ne pas effacer l'historique si tous les flux échouent.
    cutoff = (now - timedelta(days=120)).date().isoformat()
    all_items = [x for x in existing.values() if x.get("date", "") >= cutoff]
    all_items.sort(key=lambda a: (a.get("date", ""), a.get("score", 0)), reverse=True)
    all_items = all_items[:MAX_RECORDS]
    output = {
        "updated_at": now.isoformat(), "source": "python_rss_sans_ia",
        "articles": all_items,
        "stats": {"new_articles": new_count, "feeds_ok": feeds_ok,
                  "feeds_failed": len(config["feeds"]) - feeds_ok,
                  "errors": errors,
                  "note": "Triage lexical automatique. A6/B6/F6 : la crédibilité des faits reste NON vérifiée."},
    }
    save_json(base / "veille.json", output)
    print(f"FISHWATCH : {len(all_items)} fiches, {new_count} nouvelle(s), {feeds_ok}/{len(config['feeds'])} flux OK")
    for err in errors:
        print("AVERTISSEMENT :", err, file=sys.stderr)
    return output


def main():
    parser = argparse.ArgumentParser(description="Collecte RSS gratuite et classement explicite")
    parser.add_argument("--dry-run", action="store_true", help="Test sur une copie temporaire sans modifier les fichiers du projet")
    args = parser.parse_args()
    if args.dry_run:
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            (target / "config").mkdir()
            shutil.copy(BASE / "config/sources.json", target / "config/sources.json")
            out = run(target)
            print("Mode dry-run :", out["stats"])
    else:
        run()


if __name__ == "__main__":
    main()
