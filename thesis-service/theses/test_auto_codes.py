from importlib import import_module
from types import SimpleNamespace
from django.apps import apps
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient
from config.testing import AuthenticatedAPITestCase, TEST_PUBLIC_KEY, bearer
from .models import Thesis, ThesisCodeSequence
from .codegen import create_with_code


class AutomaticCodeTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.number = 0
        self.url = "/api/theses/"

    def body(self):
        self.number += 1
        return {"title": f"Auto Thesis {self.number}", "max_students": 2}

    def create_record(self, **extra):
        response = self.client.post(self.url, {**self.body(), **extra}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_omitted_codes_are_generated_in_order(self):
        self.assertEqual(self.create_record()["thesis_code"], "DT001")
        self.assertEqual(self.create_record()["thesis_code"], "DT002")

    def test_blank_code_uses_automatic_generation(self):
        self.assertEqual(self.create_record(thesis_code="  ")["thesis_code"], "DT001")

    def test_existing_numeric_and_imported_codes_are_preserved(self):
        self.create_record(thesis_code="DT009")
        imported = self.create_record(thesis_code="DEMO_CUSTOM")
        self.assertEqual(imported["thesis_code"], "DEMO_CUSTOM")
        self.assertEqual(self.create_record()["thesis_code"], "DT010")

    def test_reconciles_codes_created_outside_the_api(self):
        Thesis.objects.create(thesis_code="dt1000", **self.body())
        self.assertEqual(self.create_record()["thesis_code"], "DT1001")

    def test_deleted_codes_are_not_reissued(self):
        item = self.create_record()
        Thesis.objects.get(pk=item["id"]).delete()
        self.assertEqual(self.create_record()["thesis_code"], "DT002")

    def test_edit_without_code_keeps_original(self):
        item = self.create_record()
        body = self.body()
        response = self.client.patch(self.url+str(item["id"])+"/", body, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["thesis_code"], item["thesis_code"])
        bad = self.client.patch(self.url+str(item["id"])+"/", {"thesis_code": ""}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_legacy_code_edit_advances_counter(self):
        item = self.create_record()
        response = self.client.patch(self.url+str(item["id"])+"/", {"thesis_code": "DT020"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.create_record()["thesis_code"], "DT021")

    def test_normalized_duplicate_code_is_rejected(self):
        self.create_record(thesis_code="DT010")
        response = self.client.post(self.url, {**self.body(), "thesis_code": "dt010"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Thesis.objects.count(), 1)

    def test_failed_save_does_not_consume_a_code(self):
        with patch("theses.codegen.Thesis.objects.create", side_effect=RuntimeError("simulated write failure")):
            with self.assertRaises(RuntimeError):
                create_with_code(self.body())
        self.assertEqual(ThesisCodeSequence.objects.get(pk=1).value, 0)
        self.assertEqual(self.create_record()["thesis_code"], "DT001")

    def test_counter_migration_preserves_existing_records(self):
        Thesis.objects.create(thesis_code="DT041", **self.body())
        before = list(Thesis.objects.values_list("id", "thesis_code"))
        ThesisCodeSequence.objects.all().delete()
        module = import_module("theses.migrations.0003_auto_codes")
        module.initialize_counter(apps, SimpleNamespace(connection=connection))
        self.assertEqual(ThesisCodeSequence.objects.get(pk=1).value, 41)
        self.assertEqual(list(Thesis.objects.values_list("id", "thesis_code")), before)

    def test_unauthorized_creation_does_not_allocate(self):
        self.login_as("STUDENT", student_id=1)
        self.assertEqual(self.client.post(self.url, self.body(), format="json").status_code, 403)
        self.assertEqual(ThesisCodeSequence.objects.get(pk=1).value, 0)


@skipUnless(connection.vendor == "microsoft", "Concurrent row locks must be checked on SQL Server")
@override_settings(JWT_PUBLIC_KEY=TEST_PUBLIC_KEY, JWT_CHECK_ACCOUNT_STATE=False)
class ConcurrentAutomaticCodeTests(TransactionTestCase):
    def setUp(self):
        ThesisCodeSequence.objects.get_or_create(pk=1, defaults={"value": 0})

    def test_simultaneous_api_creates_get_different_codes(self):
        barrier = Barrier(5, timeout=15)
        def create(i):
            close_old_connections()
            try:
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=bearer(role="ADMIN"))
                barrier.wait()
                response = client.post("/api/theses/", {"title": f"Parallel {i}", "max_students": 1}, format="json")
                return response.status_code, response.data
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(create, range(5)))
        self.assertTrue(all(code == 201 for code, data in results), results)
        codes = [data["thesis_code"] for code, data in results]
        self.assertEqual(len(set(codes)), 5)
        self.assertEqual(Thesis.objects.count(), 5)
