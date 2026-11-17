"""Tests hors ligne : ne nécessitent ni accès web ni abonnement."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch


from collect import classify, norm, select_category, score_record, source_grade, monitor_pages, run, parse_feed

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=ZoneInfo('Europe/Paris'))

SAMPLE_RSS = b'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Test RSS</title>
<item><title>Projet d'arrete peche en Haute-Savoie</title><description>Consultation publique relative a la truite sur le Fier.</description><link>https://news.google.com/rss/articles/AAAA</link><pubDate>Mon, 16 Nov 2026 08:00:00 GMT</pubDate><source url="https://www.haute-savoie.gouv.fr">Prefecture</source></item>
<item><title>Secheresse dans la vallee de l'Arve en Haute-Savoie</title><description>Debits faibles et etiage des cours d'eau</description><link>https://news.google.com/rss/articles/BBBB</link><pubDate>Mon, 16 Nov 2026 08:00:00 GMT</pubDate><source url="https://example.org">Actus</source></item>
<item><title>Promotion cannes a peche Haute-Savoie</title><description>Les meilleurs prix pour acheter une canne</description><link>https://news.google.com/rss/articles/CCCC</link><pubDate>Mon, 16 Nov 2026 08:00:00 GMT</pubDate></item>
<item><title>Pollution et mortalite de poissons dans le Cheran Haute-Savoie</title><description>Signalement de truites mortes dans la riviere.</description><link>https://news.google.com/rss/articles/DDDD</link><pubDate>Mon, 16 Nov 2026 08:00:00 GMT</pubDate></item>
</channel></rss>'''

class TestClassification(unittest.TestCase):
    def test_normalisation(self):
        self.assertEqual(norm('Sécheresse & PÊCHE'), 'secheresse peche')

    def test_pir_reglementation(self):
        pir, ind, _ = select_category('Projet d’arrêté de pêche en Haute-Savoie', 'Consultation publique sur le Fier')
        self.assertEqual(pir, 'PIR-1')
        self.assertTrue(ind)

    def test_pir_environment(self):
        pir, _, _ = select_category('Sécheresse dans la vallée de l’Arve', 'Débit du cours d’eau en Haute-Savoie')
        self.assertEqual(pir, 'PIR-2')

    def test_pir_health(self):
        pir, _, _ = select_category('Mortalité des truites du Chéran', 'Pollution d’une rivière en Haute-Savoie')
        self.assertEqual(pir, 'PIR-3')

    def test_reject_commercial_and_nonlocal(self):
        self.assertIsNone(select_category('Comparatif canne de pêche Haute-Savoie', 'promotion de leurres')[0])
        self.assertIsNone(select_category('Arrêté pêche Bretagne', 'Fermeture d’une rivière en Bretagne')[0])

    def test_score_explicit(self):
        self.assertEqual(score_record('PIR-1', 'Restriction', 'A')[0], 10)
        self.assertEqual(score_record('PIR-2', 'Crue', 'F')[0], 9)
        self.assertEqual(score_record(None, None, 'F')[0], 1)

    def test_unverified_fact(self):
        items = parse_feed(SAMPLE_RSS)
        row = classify(items[0], 'Arrêtés', NOW)
        self.assertEqual(row['pir'], 'PIR-1')
        self.assertEqual(row['cote'], 'A6')
        self.assertFalse(row['demo'])
        self.assertIn('via Google', row['source'])
        self.assertIsNone(classify(items[2], 'Promotion', NOW))

    def test_unknown_publisher_not_considered_reliable(self):
        self.assertEqual(source_grade('https://example.org'), 'F')
        self.assertEqual(source_grade('https://www.haute-savoie.gouv.fr'), 'A')

    def test_monitor_first_run_baseline_then_change(self):
        config = {'website_monitors':[{'id':'f','enabled':True,'label':'Page officielle','url':'https://example.org/page'}]}
        page1 = b'<html><main><h1>Reglementation de la peche</h1><p>' + b'Texte des conditions de peche. '*10 + b'</p></main></html>'
        page2 = page1.replace(b'Texte des conditions', b'Autres conditions')
        records, state, errors = monitor_pages(config, {}, NOW, lambda _: page1)
        self.assertEqual(records, [])
        self.assertFalse(errors)
        records2, _, errors2 = monitor_pages(config, state, NOW, lambda _: page2)
        self.assertEqual(len(records2), 1)
        self.assertEqual(records2[0]['score'], 5)
        self.assertEqual(errors2, [])

    def test_run_and_dedup(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'config').mkdir()
            (base/'config/sources.json').write_text(json.dumps({'feeds':[{'id':'f1','label':'Test','query':'test'},{'id':'f2','label':'Test2','query':'test2'}], 'website_monitors':[]}), encoding='utf8')
            f = lambda _: SAMPLE_RSS
            one = run(base, fetcher=f, now=NOW)
            self.assertEqual(one['stats']['new_articles'], 3)
            self.assertEqual(len(one['articles']), 3)
            two = run(base, fetcher=f, now=NOW)
            self.assertEqual(two['stats']['new_articles'], 0)
            self.assertEqual(len(two['articles']), 3)
            self.assertEqual(two['source'], 'python_rss_sans_ia')

if __name__ == '__main__':
    unittest.main()
