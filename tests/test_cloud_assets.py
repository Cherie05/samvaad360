"""Offline preparation checks, not evidence of a real Snowflake deployment."""

import copy
import json

import pytest

from cloud.capabilities import coco_report
from cloud.cli import main
from cloud.config import CloudConfig, CloudError, connection_name, identifier, read_config
from cloud.fixtures import TABLES, build_bundle, digest, load_fixture, stage_rows, validate_bundle
from cloud.sql_assets import render, statements


@pytest.mark.parametrize("value", ['DB; DROP DATABASE PROD', 'DB.NAME', '"DB"', 'DB --', 'DB\nNAME', '../DB', '', 123])
def test_identifiers_reject_ambiguous_or_injected_sql(value):
    with pytest.raises(CloudError):
        identifier(value)


@pytest.mark.parametrize("value", ['--bypass', 'name;echo secret', 'a b', '../private', '', 123])
def test_connection_names_do_not_become_flags_or_shell_commands(value):
    with pytest.raises(CloudError):
        connection_name(value)


def test_config_accepts_only_connection_reference_and_object_names(tmp_path, monkeypatch):
    for key in ('SAMVAAD_SNOWFLAKE_CONNECTION', 'SAMVAAD_SNOWFLAKE_DATABASE', 'SAMVAAD_SNOWFLAKE_WAREHOUSE'):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / 'cloud.toml'
    path.write_text('[snowflake]\nconnection_name="demo"\ndatabase="samvaad_db"\nwarehouse="demo_wh"\n', encoding='utf-8')
    config = read_config(path)
    assert config.object('RAW', 'CUSTOMERS') == '"SAMVAAD_DB"."RAW"."CUSTOMERS"'
    path.write_text('[snowflake]\npassword="never-print-this-secret"\n', encoding='utf-8')
    with pytest.raises(CloudError) as error:
        read_config(path)
    assert 'never-print-this-secret' not in str(error.value)


def test_fixture_export_is_deterministic_and_manifest_checked():
    first, second = build_bundle(), build_bundle()
    assert first == second
    assert first['counts']['customers'] == 20
    assert first['sha256'] == digest({key: value for key, value in first.items() if key != 'sha256'})
    tampered = copy.deepcopy(first)
    tampered['data']['customers'][0]['monthly_income'] = 99999999
    with pytest.raises(CloudError) as error:
        validate_bundle(tampered)
    assert error.value.code == 'BUNDLE_HASH_MISMATCH'


def test_fixture_rejects_duplicate_ids_and_real_contacts_even_with_updated_hash():
    bundle = build_bundle()
    bundle['data']['customers'][1]['customer_id'] = bundle['data']['customers'][0]['customer_id']
    bundle['sha256'] = digest({key: value for key, value in bundle.items() if key != 'sha256'})
    with pytest.raises(CloudError) as error:
        validate_bundle(bundle)
    assert error.value.code == 'DUPLICATE_FIXTURE_ID'
    bundle = build_bundle()
    bundle['data']['customers'][0]['email'] = 'real@example.com'
    bundle['sha256'] = digest({key: value for key, value in bundle.items() if key != 'sha256'})
    with pytest.raises(CloudError) as error:
        validate_bundle(bundle)
    assert error.value.code == 'REAL_CONTACT_REJECTED'


def test_sql_assets_do_not_provision_compute_or_claim_workflow_constraints():
    config = CloudConfig(database='SAMVAAD_DB', warehouse='DEMO_WH')
    sql = '\n'.join(render(asset, config) for asset in ('schema', 'views', 'search', 'enrichment'))
    assert '{{' not in sql
    assert 'CREATE WAREHOUSE' not in sql.upper()
    assert '.APP.' not in sql.upper()
    assert 'PRIMARY KEY' not in render('schema', config).upper()
    assert 'AI_CLASSIFY' in sql and 'AI_SENTIMENT' in sql and 'AI_EXTRACT' in sql
    assert 'INITIALIZE = ON_SCHEDULE' in sql
    assert 'AUTO_SUSPEND = 1800' in sql  # Documented minimum is 30 minutes.
    assert "LIMIT 5" in render('enrichment', config)
    assert len(statements(render('schema', config))) == 9
    for value in (0, 101, True, '1; DROP TABLE X'):
        with pytest.raises(CloudError):
            render('enrichment', config, limit=value)


class FakeCursor:
    """Models transaction effects and records bindings; does not parse Snowflake SQL."""
    def __init__(self, connection):
        self.connection = connection
        self.next_result = None

    def execute(self, sql, params=None):
        self.connection.commands.append((sql, params))
        if sql.startswith('SELECT COUNT(*)'):
            table = next(key for key, (name, _) in TABLES.items() if sql.endswith('"' + name + '"'))
            row = self.connection.state[table]
            count = row['count'] + (1 if self.connection.corrupt and self.connection.inserted and table == 'customers' else 0)
            self.next_result = (count, row['hash'], row['hash'], row['count'])
        elif sql == 'BEGIN':
            self.connection.backup = copy.deepcopy(self.connection.state)
        elif sql == 'ROLLBACK':
            self.connection.state = self.connection.backup
        elif sql == 'COMMIT':
            self.connection.committed = True
        elif sql.startswith('INSERT INTO') and 'WHERE DATASET=%s' in sql:
            dataset = params[0]
            records = [record for record in self.connection.records if record[0] == dataset]
            self.connection.state[dataset] = {'count': len(records), 'hash': records[0][-1]}
            self.connection.inserted = True
        return self

    def executemany(self, sql, values):
        self.connection.commands.append((sql, values))
        self.connection.records = values

    def fetchone(self):
        return self.next_result

    def close(self):
        pass


class FakeConnection:
    def __init__(self, corrupt=False):
        self.commands, self.records = [], []
        self.state = {key: {'count': 0, 'hash': None} for key in TABLES}
        self.corrupt, self.inserted, self.committed = corrupt, False, False

    def cursor(self):
        return FakeCursor(self)


def test_fixture_values_are_bound_and_identical_reload_is_noop():
    payload = "Borrower: Robert'); DROP DATABASE PROD; -- wants a statement."
    bundle = build_bundle()
    bundle['data']['interactions'][0]['text'] = payload
    bundle['sha256'] = digest({key: value for key, value in bundle.items() if key != 'sha256'})
    connection = FakeConnection()
    result = load_fixture(connection, CloudConfig(), bundle)
    assert result['status'] == 'LOADED'
    assert connection.committed
    assert all(payload not in sql for sql, _ in connection.commands)
    assert any(payload == row[5] for row in connection.records)
    assert load_fixture(connection, CloudConfig(), bundle)['status'] == 'ALREADY_LOADED'
    assert len([sql for sql, _ in connection.commands if sql == 'COMMIT']) == 1


def test_failed_load_verification_rolls_back_instead_of_claiming_success():
    connection = FakeConnection(corrupt=True)
    with pytest.raises(CloudError) as error:
        load_fixture(connection, CloudConfig(), build_bundle())
    assert error.value.code == 'LOAD_VERIFICATION_FAILED'
    assert all(row['count'] == 0 for row in connection.state.values())
    assert connection.committed is False
    assert any(sql == 'ROLLBACK' for sql, _ in connection.commands)


def test_existing_mismatched_cloud_data_is_never_overwritten():
    connection = FakeConnection()
    connection.state['customers'] = {'count': 1, 'hash': 'other-data'}
    with pytest.raises(CloudError) as error:
        load_fixture(connection, CloudConfig(), build_bundle())
    assert error.value.code == 'CLOUD_DATA_EXISTS'
    assert all(not sql.startswith(('INSERT', 'DROP', 'CREATE')) for sql, _ in connection.commands)


def test_missing_coco_does_not_claim_invocation_or_skill_success(monkeypatch):
    monkeypatch.setattr('cloud.capabilities.cortex_path', lambda: None)
    report = coco_report(CloudConfig(), run_smoke=True)
    assert report['model_smoke_attempted'] is False
    assert report['model_smoke_verified'] is False
    assert report['project_skills_runtime_verified'] is False
    assert report['project_hook_runtime_verified'] is False


def test_cli_prepares_assets_without_account_and_apply_fails_clearly(tmp_path, capsys, monkeypatch):
    for key in ('SAMVAAD_SNOWFLAKE_CONNECTION', 'SAMVAAD_SNOWFLAKE_WAREHOUSE', 'SAMVAAD_CLOUD_CONFIG'):
        monkeypatch.delenv(key, raising=False)
    config = tmp_path / 'absent.toml'
    output = tmp_path / 'plan.sql'
    assert main(['deploy', '--config', str(config), '--output', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['cloud_modified'] is False
    assert main(['deploy', '--config', str(config), '--output', str(output), '--apply']) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'BLOCKED'
    assert report['error'] == 'WAREHOUSE_REQUIRED'
