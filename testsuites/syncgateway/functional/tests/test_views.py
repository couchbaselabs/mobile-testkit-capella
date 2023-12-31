

import random

import pytest

from keywords import document
from keywords.MobileRestClient import MobileRestClient
from keywords.SyncGateway import SyncGateway, sync_gateway_config_path_for_mode
from keywords.userinfo import UserInfo
from keywords.utils import log_info
from libraries.testkit.cluster import Cluster
from utilities.cluster_config_utils import get_sg_version, persist_cluster_config_environment_prop, copy_to_temp_conf
from keywords.constants import RBAC_FULL_ADMIN


@pytest.mark.syncgateway
@pytest.mark.views
@pytest.mark.session
@pytest.mark.basicsgw
@pytest.mark.parametrize('sg_conf_name, validate_changes_before_restart, x509_cert_auth', [
    pytest.param('sync_gateway_default_functional_tests', False, False, marks=[pytest.mark.sanity, pytest.mark.oscertify]),
    ('sync_gateway_default_functional_tests', True, True),
    ('sync_gateway_default_functional_tests_no_port', False, True),
    ('sync_gateway_default_functional_tests_no_port', True, False)
])
def test_view_backfill_for_deletes(params_from_base_test_setup, sg_conf_name,
                                   validate_changes_before_restart, x509_cert_auth):
    """
    Scenario:
    1. Write a bunch of docs
    2. Delete 1/2
    3. Restart Sync Gateway
    4. Issue _changes, assert view backfills docs and delete notifications
    """

    num_docs = 1000
    sg_db = 'db'

    cluster_conf = params_from_base_test_setup['cluster_config']
    cluster_topology = params_from_base_test_setup['cluster_topology']
    mode = params_from_base_test_setup['mode']
    ssl_enabled = params_from_base_test_setup["ssl_enabled"]
    need_sgw_admin_auth = params_from_base_test_setup["need_sgw_admin_auth"]

    if ("sync_gateway_default_functional_tests_no_port" in sg_conf_name) and get_sg_version(cluster_conf) < "1.5.0":
        pytest.skip('couchbase/couchbases ports do not support for versions below 1.5')
    if "sync_gateway_default_functional_tests_no_port" in sg_conf_name and not ssl_enabled:
        pytest.skip('ssl disabled so cannot run without port')

    sg_conf = sync_gateway_config_path_for_mode(sg_conf_name, mode)
    sg_admin_url = cluster_topology['sync_gateways'][0]['admin']
    sg_url = cluster_topology['sync_gateways'][0]['public']
    cbs_url = cluster_topology['couchbase_servers'][0]
    auth = need_sgw_admin_auth and (RBAC_FULL_ADMIN['user'], RBAC_FULL_ADMIN['pwd']) or None

    log_info('sg_conf: {}'.format(sg_conf))
    log_info('sg_admin_url: {}'.format(sg_admin_url))
    log_info('sg_url: {}'.format(sg_url))
    log_info('cbs_url: {}'.format(cbs_url))
    log_info('validate_changes_before_restart: {}'.format(validate_changes_before_restart))
    disable_tls_server = params_from_base_test_setup["disable_tls_server"]
    if x509_cert_auth and disable_tls_server:
        pytest.skip("x509 test cannot run tls server disabled")
    if x509_cert_auth:
        temp_cluster_config = copy_to_temp_conf(cluster_conf, mode)
        persist_cluster_config_environment_prop(temp_cluster_config, 'x509_certs', True)
        persist_cluster_config_environment_prop(temp_cluster_config, 'server_tls_skip_verify', False)
        cluster_conf = temp_cluster_config
    cluster = Cluster(config=cluster_conf)
    cluster.reset(sg_config_path=sg_conf)

    # Create clients
    sg_client = MobileRestClient()

    # Create user / session
    seth_user_info = UserInfo(name='seth', password='pass', channels=['NASA', 'NATGEO'], roles=[])
    sg_client.create_user(
        url=sg_admin_url,
        db=sg_db,
        name=seth_user_info.name,
        password=seth_user_info.password,
        channels=seth_user_info.channels,
        auth=auth
    )

    seth_auth = sg_client.create_session(
        url=sg_admin_url,
        db=sg_db,
        name=seth_user_info.name,
        auth=auth
    )

    # Add 'num_docs' to Sync Gateway
    doc_bodies = document.create_docs('test_doc', number=num_docs, channels=seth_user_info.channels)
    bulk_resp = sg_client.add_bulk_docs(url=sg_url, db=sg_db, docs=doc_bodies, auth=seth_auth)
    assert len(bulk_resp) == num_docs

    # Delete half of the docs randomly
    deleted_docs = []
    for _ in range(num_docs // 2):
        random_doc = random.choice(bulk_resp)
        deleted_doc = sg_client.delete_doc(url=sg_url, db=sg_db, doc_id=random_doc['id'], rev=random_doc['rev'], auth=seth_auth)
        deleted_docs.append(deleted_doc)
        bulk_resp.remove(random_doc)

    log_info('Number of docs deleted: {}'.format(len(deleted_docs)))
    all_docs = bulk_resp + deleted_docs
    log_info('Number of docs to look for in changes: {}'.format(len(all_docs)))

    # This test will check changes before and after SG restart if
    # validate_changes_before_restart == True
    # If it is not set to True, only build the changes after restart
    if validate_changes_before_restart:
        # Verify deletions and inital docs show up in changes feed
        sg_client.verify_docs_in_changes(url=sg_url, db=sg_db, expected_docs=all_docs, auth=seth_auth)
        changes = sg_client.get_changes(url=sg_url, db=sg_db, since=0, auth=seth_auth)
        # All docs should show up + _user doc
        assert len(changes['results']) == num_docs + 1

        deleted_doc_ids = [doc['id']for doc in deleted_docs]
        assert len(deleted_doc_ids) == num_docs / 2
        deleted_docs_in_changes = [change['id'] for change in changes['results'] if 'deleted' in change and change['deleted']]
        assert len(deleted_docs_in_changes) == num_docs / 2

        # All deleted docs should show up in the changes feed
        for doc_id in deleted_docs_in_changes:
            assert doc_id in deleted_doc_ids
            deleted_doc_ids.remove(doc_id)
        assert len(deleted_doc_ids) == 0

    # Restart Sync Gateway
    sg_controller = SyncGateway()
    sg_controller.stop_sync_gateways(url=sg_url, cluster_config=cluster_conf)
    sg_controller.start_sync_gateways(url=sg_url, cluster_config=cluster_conf, config=sg_conf)

    # Verify deletions and inital docs show up in changes feed
    sg_client.verify_docs_in_changes(url=sg_url, db=sg_db, expected_docs=all_docs, auth=seth_auth)

    changes = sg_client.get_changes(url=sg_url, db=sg_db, since=0, auth=seth_auth)
    # All docs should show up + _user doc
    assert len(changes['results']) == num_docs + 1

    deleted_doc_ids = [doc['id']for doc in deleted_docs]
    assert len(deleted_doc_ids) == num_docs / 2
    deleted_docs_in_changes = [change['id'] for change in changes['results'] if 'deleted' in change and change['deleted']]
    assert len(deleted_docs_in_changes) == num_docs / 2

    # All deleted docs should show up in th changes feed
    for doc_id in deleted_docs_in_changes:
        assert doc_id in deleted_doc_ids
        deleted_doc_ids.remove(doc_id)
    assert len(deleted_doc_ids) == 0
