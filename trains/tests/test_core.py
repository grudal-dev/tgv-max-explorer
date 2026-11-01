from datetime import date, time, timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from trains.models import Alert, Station, Trip, prettify_station_name
from trains.services import search
from trains.services.alerts import check_alerts
from trains.services.geo import lookup_coordinates, normalize_name
from trains.services.sncf import fetch_records, parse_record, parse_records
from trains.services.sync import import_trips


def rec(day, train, o, d, dep, arr, ok=True):
    return {
        "date": day.isoformat(), "train_no": train, "entity": "TGV INOUI", "axe": "SUD EST",
        "origine_iata": "", "destination_iata": "", "origine": o, "destination": d,
        "heure_depart": dep, "heure_arrivee": arr, "od_happy_card": "OUI" if ok else "NON",
    }


class HelpersTests(TestCase):
    def test_normalize_and_lookup(self):
        self.assertEqual(normalize_name("PARIS (intramuros)"), "PARIS")
        self.assertEqual(normalize_name("Saint-Pierre-des-Corps"), "ST PIERRE DES CORPS")
        self.assertIsNotNone(lookup_coordinates("MARSEILLE ST CHARLES"))
        self.assertIsNotNone(lookup_coordinates("PARIS GARE DE LYON HALL 1"))
        self.assertIsNone(lookup_coordinates("GARE INEXISTANTE"))

    def test_prettify(self):
        self.assertEqual(prettify_station_name("PARIS (intramuros)"), "Paris")
        self.assertEqual(prettify_station_name("ST PIERRE DES CORPS"), "St Pierre des Corps")

    def test_duration_overnight(self):
        self.assertEqual(Trip.compute_duration(time(10, 0), time(12, 30)), 150)
        self.assertEqual(Trip.compute_duration(time(23, 30), time(1, 0)), 90)

    def test_parse_record(self):
        today = timezone.localdate()
        r = parse_record(rec(today, "6101", "A", "B", "08:00", "10:00"))
        self.assertTrue(r.available)
        self.assertIsNone(parse_record({"date": "x"}))
        self.assertIsNone(parse_record(rec(today, "1", "A", "B", "25:99", "10:00")))


class SyncTests(TestCase):
    def setUp(self):
        self.day = timezone.localdate() + timedelta(days=1)

    def test_import_is_idempotent_and_updates(self):
        data = [rec(self.day, "6101", "PARIS (intramuros)", "LYON (intramuros)", "08:00", "10:00", ok=False)]
        s1 = import_trips(parse_records(data))
        self.assertEqual((s1.created, s1.stations_created), (1, 2))
        paris = Station.objects.get(name="PARIS (intramuros)")
        self.assertTrue(paris.has_coordinates)
        self.assertEqual(paris.display_name, "Paris")

        s2 = import_trips(parse_records(data))
        self.assertEqual((s2.created, s2.updated), (0, 0))

        data[0]["od_happy_card"] = "OUI"
        s3 = import_trips(parse_records(data))
        self.assertEqual(s3.updated, 1)
        self.assertTrue(Trip.objects.get().available)

    def test_prune_removes_missing_and_past(self):
        past = timezone.localdate() - timedelta(days=2)
        import_trips(parse_records([
            rec(self.day, "1", "A", "B", "08:00", "09:00"),
            rec(self.day, "2", "A", "B", "10:00", "11:00"),
        ]))
        Trip.objects.create(date=past, train_no="9", origin=Station.objects.get(name="A"),
                            destination=Station.objects.get(name="B"), departure_time=time(8),
                            arrival_time=time(9), duration_minutes=60, available=True)
        stats = import_trips(parse_records([rec(self.day, "1", "A", "B", "08:00", "09:00")]))
        self.assertEqual(stats.deleted, 2)
        self.assertEqual(list(Trip.objects.values_list("train_no", flat=True)), ["1"])

    def test_fetch_records_builds_query(self):
        session = mock.Mock()
        session.get.return_value.json.return_value = [{"a": 1}]
        session.get.return_value.raise_for_status.return_value = None
        out = fetch_records(start=date(2026, 1, 1), end=date(2026, 1, 5), session=session)
        self.assertEqual(out, [{"a": 1}])
        url, = session.get.call_args.args
        self.assertTrue(url.endswith("/catalog/datasets/tgvmax/exports/json"))
        self.assertIn('date >= date"2026-01-01"', session.get.call_args.kwargs["params"]["where"])


class SearchTests(TestCase):
    def setUp(self):
        self.d = timezone.localdate() + timedelta(days=1)
        self.next = self.d + timedelta(days=2)
        import_trips(parse_records([
            rec(self.d, "1", "PARIS (intramuros)", "LYON (intramuros)", "08:00", "10:00"),
            rec(self.d, "2", "LYON (intramuros)", "GRENOBLE", "10:40", "12:00"),   # corresp. 40 min
            rec(self.d, "3", "LYON (intramuros)", "ANNECY", "10:05", "12:00"),     # trop court (5 min)
            rec(self.d, "4", "LYON (intramuros)", "NICE VILLE", "15:00", "19:00"), # trop long (5 h)
            rec(self.d, "5", "PARIS (intramuros)", "NANTES", "09:00", "11:00"),
            rec(self.next, "6", "NANTES", "PARIS (intramuros)", "18:00", "20:00"),
            rec(self.next, "7", "LYON (intramuros)", "PARIS (intramuros)", "18:00", "20:00", ok=False),
        ]))
        self.paris = Station.objects.get(name="PARIS (intramuros)")
        self.grenoble = Station.objects.get(name="GRENOBLE")

    def test_connections(self):
        conns = search.connections(self.d, self.paris)
        self.assertEqual([c.destination.name for c in conns], ["GRENOBLE"])
        c = conns[0]
        self.assertEqual((c.wait_minutes, c.total_minutes), (40, 240))
        self.assertEqual(search.connections(self.d, self.paris, self.grenoble)[0].via.name,
                         "LYON (intramuros)")

    def test_round_trips_require_available_return(self):
        res = search.round_trips(self.paris, self.d, self.next)
        self.assertEqual([r.station.name for r in res], ["NANTES"])

    def test_group_by_destination_sorted_by_duration(self):
        groups = search.group_by_destination(search.direct_trips(self.d, self.paris))
        self.assertEqual(len(groups), 2)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AlertTests(TestCase):
    def setUp(self):
        self.d = timezone.localdate() + timedelta(days=3)
        self.data = [rec(self.d, "6101", "PARIS (intramuros)", "LYON (intramuros)", "08:00", "10:00", ok=False)]
        import_trips(parse_records(self.data))
        self.alert = Alert.objects.create(
            email="a@b.fr", date=self.d,
            origin=Station.objects.get(name="PARIS (intramuros)"),
            destination=Station.objects.get(name="LYON (intramuros)"),
        )

    def test_email_sent_once_when_seat_appears(self):
        self.assertEqual(check_alerts(), 0)
        self.data[0]["od_happy_card"] = "OUI"
        import_trips(parse_records(self.data))
        self.assertEqual(check_alerts(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("6101", mail.outbox[0].body)
        self.assertIn(self.alert.token, mail.outbox[0].body)
        self.assertEqual(check_alerts(), 0)  # pas de doublon

    def test_past_alert_deactivated(self):
        Alert.objects.filter(pk=self.alert.pk).update(date=timezone.localdate() - timedelta(days=1))
        check_alerts()
        self.alert.refresh_from_db()
        self.assertFalse(self.alert.active)


class ViewTests(TestCase):
    def setUp(self):
        self.d = timezone.localdate() + timedelta(days=1)
        import_trips(parse_records([
            rec(self.d, "1", "PARIS (intramuros)", "LYON (intramuros)", "08:00", "10:00"),
            rec(self.d, "2", "LYON (intramuros)", "GRENOBLE", "10:40", "12:00"),
        ]))

    def test_pages(self):
        q = f"?date={self.d.isoformat()}"
        for url in [
            reverse("trains:search") + q,
            reverse("trains:search") + q + "&origin=paris-intramuros&connections=on",
            reverse("trains:search") + q + "&origin=paris-intramuros&destination=lyon-intramuros",
            reverse("trains:search") + q + "&destination=lyon-intramuros",
            reverse("trains:weekend") + f"?origin=paris-intramuros&out_date={self.d}&back_date={self.d}",
            reverse("trains:alert_create"),
            reverse("trains:about"),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_htmx_returns_partial(self):
        r = self.client.get(reverse("trains:search") + f"?date={self.d}&origin=paris-intramuros",
                            HTTP_HX_REQUEST="true")
        self.assertNotContains(r, "<html")
        self.assertContains(r, "Lyon")
        self.assertContains(r, 'id="map-data"')

    def test_connection_shown(self):
        r = self.client.get(reverse("trains:search") + f"?date={self.d}&origin=paris-intramuros&connections=on")
        self.assertContains(r, "Grenoble")
        self.assertContains(r, "via Lyon")

    def test_alert_flow(self):
        r = self.client.post(reverse("trains:alert_create"), {
            "email": "x@y.fr", "origin": "paris-intramuros", "destination": "lyon-intramuros",
            "date": self.d.isoformat(),
        })
        alert = Alert.objects.get()
        self.assertRedirects(r, reverse("trains:alert_detail", args=[alert.token]))
        self.client.post(reverse("trains:alert_unsubscribe", args=[alert.token]))
        alert.refresh_from_db()
        self.assertFalse(alert.active)

    def test_alert_rejects_past_date_and_same_station(self):
        r = self.client.post(reverse("trains:alert_create"), {
            "email": "x@y.fr", "origin": "paris-intramuros", "destination": "paris-intramuros",
            "date": (timezone.localdate() - timedelta(days=1)).isoformat(),
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Alert.objects.exists())
