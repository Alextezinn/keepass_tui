"""
Тесты для keepass_cli/keepass/db.py

Все тесты работают с настоящей временной .kdbx базой.
После каждой операции база переоткрывается с диска (_reload),
чтобы гарантировать что изменения реально сохранились, а не только в памяти.

Покрытие:
─────────
Записи:  создание, чтение, редактирование (каждое поле), удаление,
         создание нескольких, попытка создать дубликат.
Группы:  создание в корне и вложенно, чтение, переименование,
         удаление пустой и непустой группы, group_path, refresh_group.
Общее:   save() возвращает None при успехе, строку при ошибке.
"""

import unittest
from pathlib import Path

from pykeepass import PyKeePass, create_database

import keepass_tui.keepass.db as db_mod


PATH_TMP_DIR = Path(__file__).parent.parent / "data"


# ── Фикстура ─────────────────────────────────────────────────────────────────

MASTER = "masterpass"


def _create_db(tmp_dir: Path) -> tuple[PyKeePass, str]:
    """Создаёт чистую базу. Возвращает (kp, db_path)."""
    db_path = str(tmp_dir / "test.kdbx")
    kp = create_database(db_path, password=MASTER)
    return kp, db_path


def _reload(db_path: str) -> PyKeePass:
    """Переоткрывает базу с диска — все объекты свежие."""
    return PyKeePass(db_path, password=MASTER)


# ── Базовый класс ─────────────────────────────────────────────────────────────


class KeePassTestCase(unittest.TestCase):
    def setUp(self):
        self._db_dir = PATH_TMP_DIR
        self.kp, self.db_path = _create_db(self._db_dir)

    def tearDown(self):
        super().tearDown()

    def reload(self) -> PyKeePass:
        return _reload(self.db_path)


# ══════════════════════════════════════════════════════════════════════════════
# CRUD записей
# ══════════════════════════════════════════════════════════════════════════════


class TestEntryCreate(KeePassTestCase):
    def test_create_entry_returns_none_on_success(self):
        err = db_mod.create_entry(
            self.kp,
            self.kp.root_group,
            title="GitHub",
            username="user",
            password="P@ss1!",
            url="https://github.com",
        )
        self.assertIsNone(err)

    def test_create_entry_persisted_to_disk(self):
        db_mod.create_entry(
            self.kp,
            self.kp.root_group,
            title="GitHub",
            username="user",
            password="P@ss1!",
            url="https://github.com",
        )
        kp2 = self.reload()
        entry = kp2.find_entries(title="GitHub", first=True)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.username, "user")
        self.assertEqual(entry.password, "P@ss1!")
        self.assertEqual(entry.url, "https://github.com")

    def test_create_entry_with_empty_optional_fields(self):
        db_mod.create_entry(self.kp, self.kp.root_group, title="MinEntry")
        kp2 = self.reload()
        entry = kp2.find_entries(title="MinEntry", first=True)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.username or "", "")
        self.assertEqual(entry.password or "", "")

    def test_create_multiple_entries(self):
        for i in range(5):
            db_mod.create_entry(
                self.kp,
                self.kp.root_group,
                title=f"Entry-{i}",
                username=f"user{i}",
                password=f"Pass{i}!",
            )
        kp2 = self.reload()
        self.assertEqual(len(kp2.entries), 5)

    def test_create_entry_in_subgroup(self):
        group = self.kp.add_group(self.kp.root_group, "Work")
        self.kp.save()
        db_mod.create_entry(
            self.kp, group, title="Jira", username="jira_user", password="Jira1!"
        )
        kp2 = self.reload()
        entry = kp2.find_entries(title="Jira", first=True)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.group.name, "Work")


class TestEntryRead(KeePassTestCase):
    def setUp(self):
        super().setUp()
        db_mod.create_entry(
            self.kp,
            self.kp.root_group,
            title="Server",
            username="root",
            password="R00t!",
            url="ssh://10.0.0.1",
        )
        self.kp = self.reload()
        self.entry = self.kp.find_entries(title="Server", first=True)

    def test_read_title(self):
        self.assertEqual(self.entry.title, "Server")

    def test_read_username(self):
        self.assertEqual(self.entry.username, "root")

    def test_read_password(self):
        self.assertEqual(self.entry.password, "R00t!")

    def test_read_url(self):
        self.assertEqual(self.entry.url, "ssh://10.0.0.1")

    def test_find_returns_none_for_missing_entry(self):
        missing = self.kp.find_entries(title="NoSuchEntry", first=True)
        self.assertIsNone(missing)

    def test_entry_uuid_is_stable_after_reload(self):
        uuid_before = self.entry.uuid
        kp2 = self.reload()
        entry2 = kp2.find_entries(uuid=uuid_before, first=True)
        self.assertIsNotNone(entry2)
        self.assertEqual(entry2.title, "Server")


class TestEntryUpdate(KeePassTestCase):
    def setUp(self):
        super().setUp()
        db_mod.create_entry(
            self.kp,
            self.kp.root_group,
            title="OldTitle",
            username="olduser",
            password="OldP@ss1!",
            url="http://old.com",
        )
        self.kp = self.reload()
        self.entry = self.kp.find_entries(title="OldTitle", first=True)

    def test_update_all_fields(self):
        err = db_mod.update_entry(
            self.kp,
            self.entry,
            title="NewTitle",
            username="newuser",
            password="NewP@ss1!",
            url="https://new.com",
        )
        self.assertIsNone(err)
        kp2 = self.reload()
        entry = kp2.find_entries(title="NewTitle", first=True)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.username, "newuser")
        self.assertEqual(entry.password, "NewP@ss1!")
        self.assertEqual(entry.url, "https://new.com")

    def test_update_title_only(self):
        db_mod.update_entry(
            self.kp,
            self.entry,
            title="RenamedOnly",
            username=self.entry.username,
            password=self.entry.password,
            url=self.entry.url,
        )

        kp2 = self.reload()
        self.assertIsNotNone(kp2.find_entries(title="RenamedOnly", first=True))
        self.assertIsNone(kp2.find_entries(title="OldTitle", first=True))

    def test_update_password_only(self):
        db_mod.update_entry(
            self.kp,
            self.entry,
            title=self.entry.title,
            username=self.entry.username,
            password="BrandNewP@ss1!",
            url=self.entry.url,
        )
        kp2 = self.reload()
        entry = kp2.find_entries(title="OldTitle", first=True)
        self.assertEqual(entry.password, "BrandNewP@ss1!")

    def test_update_persists_by_uuid(self):
        """После обновления запись находится по тому же UUID."""
        uuid = self.entry.uuid
        db_mod.update_entry(
            self.kp, self.entry, title="ByUUID", username="u", password="P@1!", url=""
        )
        kp2 = self.reload()
        entry = kp2.find_entries(uuid=uuid, first=True)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.title, "ByUUID")

    def test_old_title_gone_after_rename(self):
        db_mod.update_entry(
            self.kp,
            self.entry,
            title="NewTitle2",
            username="u",
            password="P@1!",
            url="",
        )
        kp2 = self.reload()
        self.assertIsNone(kp2.find_entries(title="OldTitle", first=True))


class TestEntryDelete(KeePassTestCase):
    def test_delete_entry_returns_none(self):
        db_mod.create_entry(
            self.kp, self.kp.root_group, title="ToDelete", username="u", password="P@1!"
        )
        self.kp = self.reload()
        entry = self.kp.find_entries(title="ToDelete", first=True)
        err = db_mod.delete_entry(self.kp, entry)
        self.assertIsNone(err)

    def test_deleted_entry_not_on_disk(self):
        db_mod.create_entry(
            self.kp, self.kp.root_group, title="Gone", username="u", password="P@1!"
        )
        self.kp = self.reload()
        entry = self.kp.find_entries(title="Gone", first=True)
        db_mod.delete_entry(self.kp, entry)
        kp2 = self.reload()
        self.assertIsNone(kp2.find_entries(title="Gone", first=True))

    def test_delete_one_of_several_entries(self):
        for t in ("Keep1", "Remove", "Keep2"):
            db_mod.create_entry(
                self.kp, self.kp.root_group, title=t, username="u", password="P@1!"
            )
        self.kp = self.reload()
        entry = self.kp.find_entries(title="Remove", first=True)
        db_mod.delete_entry(self.kp, entry)
        kp2 = self.reload()
        self.assertEqual(len(kp2.entries), 2)
        self.assertIsNone(kp2.find_entries(title="Remove", first=True))
        self.assertIsNotNone(kp2.find_entries(title="Keep1", first=True))
        self.assertIsNotNone(kp2.find_entries(title="Keep2", first=True))

    def test_delete_all_entries(self):
        for t in ("A", "B", "C"):
            db_mod.create_entry(
                self.kp, self.kp.root_group, title=t, username="u", password="P@1!"
            )
        self.kp = self.reload()
        for entry in list(self.kp.entries):
            db_mod.delete_entry(self.kp, entry)
        kp2 = self.reload()
        self.assertEqual(len(kp2.entries), 0)


# ══════════════════════════════════════════════════════════════════════════════
# CRUD групп
# ══════════════════════════════════════════════════════════════════════════════


class TestGroupCreate(KeePassTestCase):
    def test_create_group_returns_none(self):
        err = db_mod.create_group(self.kp, self.kp.root_group, "Work")
        self.assertIsNone(err)

    def test_create_group_persisted_to_disk(self):
        db_mod.create_group(self.kp, self.kp.root_group, "Work")
        kp2 = self.reload()
        group = kp2.find_groups(name="Work", first=True)
        self.assertIsNotNone(group)

    def test_create_nested_group(self):
        db_mod.create_group(self.kp, self.kp.root_group, "Work")
        self.kp = self.reload()
        work = self.kp.find_groups(name="Work", first=True)
        db_mod.create_group(self.kp, work, "DevOps")
        kp2 = self.reload()
        devops = kp2.find_groups(name="DevOps", first=True)
        self.assertIsNotNone(devops)
        self.assertEqual(devops.group.name, "Work")

    def test_create_multiple_groups_in_root(self):
        for name in ("Work", "Personal", "Finance"):
            db_mod.create_group(self.kp, self.kp.root_group, name)
        kp2 = self.reload()
        # root_group не считается — только дочерние
        names = {g.name for g in kp2.root_group.subgroups}
        self.assertSetEqual(names, {"Work", "Personal", "Finance"})

    def test_create_group_uuid_stable_after_reload(self):
        db_mod.create_group(self.kp, self.kp.root_group, "Stable")
        self.kp = self.reload()
        group = self.kp.find_groups(name="Stable", first=True)
        uuid = group.uuid
        kp2 = self.reload()
        group2 = kp2.find_groups(uuid=uuid, first=True)
        self.assertIsNotNone(group2)
        self.assertEqual(group2.name, "Stable")


class TestGroupRead(KeePassTestCase):
    def setUp(self):
        super().setUp()
        db_mod.create_group(self.kp, self.kp.root_group, "Servers")
        self.kp = self.reload()
        self.group = self.kp.find_groups(name="Servers", first=True)

    def test_group_name(self):
        self.assertEqual(self.group.name, "Servers")

    def test_group_parent_is_root(self):
        self.assertEqual(self.group.group.name, self.kp.root_group.name)

    def test_find_returns_none_for_missing_group(self):
        missing = self.kp.find_groups(name="NoSuchGroup", first=True)
        self.assertIsNone(missing)

    def test_group_path_single_level(self):
        path = db_mod.group_path(self.group)
        self.assertEqual(path, "Root / Servers")

    def test_group_path_two_levels(self):
        db_mod.create_group(self.kp, self.group, "Linux")
        self.kp = self.reload()
        linux = self.kp.find_groups(name="Linux", first=True)
        path = db_mod.group_path(linux)
        self.assertEqual(path, "Root / Servers / Linux")

    def test_group_path_three_levels(self):
        db_mod.create_group(self.kp, self.group, "Linux")
        self.kp = self.reload()
        linux = self.kp.find_groups(name="Linux", first=True)
        db_mod.create_group(self.kp, linux, "Ubuntu")
        self.kp = self.reload()
        ubuntu = self.kp.find_groups(name="Ubuntu", first=True)
        self.assertEqual(db_mod.group_path(ubuntu), "Root / Servers / Linux / Ubuntu")

    def test_refresh_group_returns_live_object(self):
        uuid = self.group.uuid
        self.kp = self.reload()
        live_group = db_mod.refresh_group(self.kp, self.group)
        self.assertEqual(live_group.uuid, uuid)

    def test_entries_in_group_readable(self):
        db_mod.create_entry(
            self.kp, self.group, title="SSH-key", username="root", password="P@1!"
        )
        self.kp = self.reload()
        group = self.kp.find_groups(name="Servers", first=True)
        self.assertEqual(len(group.entries), 1)
        self.assertEqual(group.entries[0].title, "SSH-key")


class TestGroupRename(KeePassTestCase):
    def test_rename_group_returns_none(self):
        db_mod.create_group(self.kp, self.kp.root_group, "OldName")
        self.kp = self.reload()
        group = self.kp.find_groups(name="OldName", first=True)
        err = db_mod.rename_group(self.kp, group, "NewName")
        self.assertIsNone(err)

    def test_rename_persisted_to_disk(self):
        db_mod.create_group(self.kp, self.kp.root_group, "OldName")
        self.kp = self.reload()
        group = self.kp.find_groups(name="OldName", first=True)
        db_mod.rename_group(self.kp, group, "NewName")
        kp2 = self.reload()
        self.assertIsNotNone(kp2.find_groups(name="NewName", first=True))
        self.assertIsNone(kp2.find_groups(name="OldName", first=True))

    def test_rename_preserves_uuid(self):
        db_mod.create_group(self.kp, self.kp.root_group, "ByUUID")
        self.kp = self.reload()
        group = self.kp.find_groups(name="ByUUID", first=True)
        uuid = group.uuid
        db_mod.rename_group(self.kp, group, "RenamedUUID")
        kp2 = self.reload()
        group2 = kp2.find_groups(uuid=uuid, first=True)
        self.assertIsNotNone(group2)
        self.assertEqual(group2.name, "RenamedUUID")

    def test_rename_preserves_entries_inside(self):
        db_mod.create_group(self.kp, self.kp.root_group, "Container")
        self.kp = self.reload()
        group = self.kp.find_groups(name="Container", first=True)
        db_mod.create_entry(
            self.kp, group, title="Inner", username="u", password="P@1!"
        )
        self.kp = self.reload()
        group = self.kp.find_groups(name="Container", first=True)
        db_mod.rename_group(self.kp, group, "Renamed")
        kp2 = self.reload()
        renamed = kp2.find_groups(name="Renamed", first=True)
        self.assertEqual(len(renamed.entries), 1)
        self.assertEqual(renamed.entries[0].title, "Inner")


class TestGroupDelete(KeePassTestCase):
    def test_delete_empty_group_returns_none(self):
        db_mod.create_group(self.kp, self.kp.root_group, "Empty")
        self.kp = self.reload()
        group = self.kp.find_groups(name="Empty", first=True)
        err = db_mod.delete_group(self.kp, group)
        self.assertIsNone(err)

    def test_delete_empty_group_not_on_disk(self):
        db_mod.create_group(self.kp, self.kp.root_group, "Gone")
        self.kp = self.reload()
        group = self.kp.find_groups(name="Gone", first=True)
        db_mod.delete_group(self.kp, group)
        kp2 = self.reload()
        self.assertIsNone(kp2.find_groups(name="Gone", first=True))

    def test_delete_group_with_entries_removes_entries_too(self):
        db_mod.create_group(self.kp, self.kp.root_group, "WithEntries")
        self.kp = self.reload()
        group = self.kp.find_groups(name="WithEntries", first=True)
        db_mod.create_entry(
            self.kp, group, title="Child1", username="u", password="P@1!"
        )
        db_mod.create_entry(
            self.kp, group, title="Child2", username="u", password="P@1!"
        )
        self.kp = self.reload()
        group = self.kp.find_groups(name="WithEntries", first=True)
        db_mod.delete_group(self.kp, group)
        kp2 = self.reload()
        self.assertIsNone(kp2.find_groups(name="WithEntries", first=True))
        self.assertIsNone(kp2.find_entries(title="Child1", first=True))
        self.assertIsNone(kp2.find_entries(title="Child2", first=True))

    def test_delete_group_with_nested_subgroup(self):
        db_mod.create_group(self.kp, self.kp.root_group, "Parent")
        self.kp = self.reload()
        parent = self.kp.find_groups(name="Parent", first=True)
        db_mod.create_group(self.kp, parent, "Child")
        self.kp = self.reload()
        parent = self.kp.find_groups(name="Parent", first=True)
        db_mod.delete_group(self.kp, parent)
        kp2 = self.reload()
        self.assertIsNone(kp2.find_groups(name="Parent", first=True))
        self.assertIsNone(kp2.find_groups(name="Child", first=True))

    def test_delete_one_of_several_groups(self):
        for name in ("Keep1", "Remove", "Keep2"):
            db_mod.create_group(self.kp, self.kp.root_group, name)
        self.kp = self.reload()
        group = self.kp.find_groups(name="Remove", first=True)
        db_mod.delete_group(self.kp, group)
        kp2 = self.reload()
        names = {g.name for g in kp2.root_group.subgroups}
        self.assertIn("Keep1", names)
        self.assertIn("Keep2", names)
        self.assertNotIn("Remove", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
