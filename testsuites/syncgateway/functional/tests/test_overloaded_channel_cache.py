import time
import pytest

from libraries.testkit.admin import Admin
from libraries.testkit.cluster import Cluster
from libraries.testkit.verify import verify_changes
from keywords.constants import RBAC_FULL_ADMIN
from requests.auth import HTTPBasicAuth

import concurrent
import concurrent.futures
import requests

from keywords.utils import log_info
from keywords.SyncGateway import sync_gateway_config_path_for_mode
from utilities.cluster_config_utils import persist_cluster_config_environment_prop, copy_to_temp_conf


@pytest.mark.syncgateway
@pytest.mark.basicauth
@pytest.mark.channel
@pytest.mark.bulkops
@pytest.mark.parametrize("sg_conf_name, num_docs, user_channels, filter, limit, x509_cert_auth", [
    ("sync_gateway_channel_cache", 5000, "*", True, 50, False),
    pytest.param("sync_gateway_channel_cache", 1000, "*", True, 50, True, marks=[pytest.mark.sanity, pytest.mark.oscertify]),
    ("sync_gateway_channel_cache", 1000, "ABC", False, 50, True),
    ("sync_gateway_channel_cache", 1000, "ABC", True, 50, False),
])
def test_overloaded_channel_cache(params_from_base_test_setup, sg_conf_name, num_docs, user_channels,
                                  filter, limit, x509_cert_auth):
    """
    The purpose of this test is to verify that channel cache backfill via view queries is working properly.
    It works by doing the following:

    - Set channel cache size in Sync Gateway config to a small number, eg, 750.  This means that only 750 docs fit in the channel cache
    - Add a large number of docs, eg, 1000.
    - Issue a _changes request that will return all 1000 docs

    Expected behavior / Verification:

    - Since 1000 docs requested from changes feed, but only 750 docs fit in channel cache, then it will need to do a view query
      to get the remaining 250 changes
    - Verify that the changes feed returns all 1000 expected docs
    - Check the expvar statistics to verify that view queries were made
    """

    cluster_conf = params_from_base_test_setup["cluster_config"]
    mode = params_from_base_test_setup["mode"]
    cbs_ce_version = params_from_base_test_setup["cbs_ce"]
    sync_gateway_version = params_from_base_test_setup['sync_gateway_version']
    need_sgw_admin_auth = params_from_base_test_setup["need_sgw_admin_auth"]

    if mode == "di":
        pytest.skip("Unsupported feature in distributed index")

    sg_conf = sync_gateway_config_path_for_mode(sg_conf_name, mode)

    log_info("Running 'test_overloaded_channel_cache'")
    log_info("Using cluster_conf: {}".format(cluster_conf))
    log_info("Using sg_conf: {}".format(sg_conf))
    log_info("Using num_docs: {}".format(num_docs))
    log_info("Using user_channels: {}".format(user_channels))
    log_info("Using filter: {}".format(filter))
    log_info("Using limit: {}".format(limit))

    disable_tls_server = params_from_base_test_setup["disable_tls_server"]
    if x509_cert_auth and disable_tls_server:
        pytest.skip("x509 test cannot run tls server disabled")
    if x509_cert_auth and not cbs_ce_version:
        temp_cluster_config = copy_to_temp_conf(cluster_conf, mode)
        persist_cluster_config_environment_prop(temp_cluster_config, 'x509_certs', True)
        persist_cluster_config_environment_prop(temp_cluster_config, 'server_tls_skip_verify', False)
        cluster_conf = temp_cluster_config

    cluster = Cluster(config=cluster_conf)
    cluster.reset(sg_config_path=sg_conf)

    target_sg = cluster.sync_gateways[0]

    admin = Admin(target_sg)
    sg_db_name = "db"

    auth = need_sgw_admin_auth and (RBAC_FULL_ADMIN['user'], RBAC_FULL_ADMIN['pwd']) or None
    if auth:
        admin.auth = HTTPBasicAuth(auth[0], auth[1])

    users = admin.register_bulk_users(target_sg, sg_db_name, "user", 1000, "password", [user_channels], num_of_workers=10)
    assert len(users) == 1000

    doc_pusher = admin.register_user(target_sg, sg_db_name, "abc_doc_pusher", "password", ["ABC"])
    doc_pusher.add_docs(num_docs)

    # Give a few seconds to let changes register
    time.sleep(2)

    start = time.time()

    # This uses a ProcessPoolExecutor due to https://github.com/couchbaselabs/mobile-testkit/issues/1142
    with concurrent.futures.ProcessPoolExecutor(max_workers=100) as executor:

        changes_requests = []
        errors = []

        for user in users:
            if filter and limit is not None:
                changes_requests.append(executor.submit(user.get_changes, since=0, limit=limit, filter="sync_gateway/bychannel", channels=["ABC"]))
            elif filter and limit is None:
                changes_requests.append(executor.submit(user.get_changes, filter="sync_gateway/bychannel", channels=["ABC"]))
            elif not filter and limit is not None:
                changes_requests.append(executor.submit(user.get_changes, limit=limit))
            elif not filter and limit is None:
                changes_requests.append(executor.submit(user.get_changes))

        for future in concurrent.futures.as_completed(changes_requests):
            changes = future.result()
            if limit is not None:
                assert len(changes["results"]) == 50
            else:
                assert len(changes["results"]) == 5001

        # changes feed should all be successful
        log_info(len(errors))
        assert len(errors) == 0

        if limit is not None:
            # HACK: Should be less than a minute unless blocking on view calls
            end = time.time()
            time_for_users_to_get_all_changes = end - start
            log_info("Time for users to get all changes: {}".format(time_for_users_to_get_all_changes))
            assert time_for_users_to_get_all_changes < 240, "Time to get all changes was greater than 2 minutes: {}s".format(
                time_for_users_to_get_all_changes
            )

        # Sanity check that a subset of users have _changes feed intact
        for i in range(10):
            verify_changes(users[i], expected_num_docs=num_docs, expected_num_revisions=0, expected_docs=doc_pusher.cache)

        # Get sync_gateway expvars
        if auth:
            resp = requests.get(url="http://{}:4985/_expvar".format(target_sg.ip), auth=HTTPBasicAuth(auth[0], auth[1]))
        else:
            resp = requests.get(url="http://{}:4985/_expvar".format(target_sg.ip))
        resp.raise_for_status()
        resp_obj = resp.json()

        # Since Sync Gateway will need to issue view queries to handle _changes requests that don't
        # fit in the channel cache, we expect there to be several view queries

        # TODO for SG 2.1, a new parameter has to be queried
        # Ref SG issue #3424
        if sync_gateway_version < "3.0.0":
            assert resp_obj["syncGateway_changeCache"]["view_queries"] > 0
        else:
            assert resp_obj['syncgateway']['per_db'][sg_db_name]['cache']['view_queries'] > 0
