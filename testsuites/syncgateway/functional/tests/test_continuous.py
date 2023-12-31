import time

import pytest
import concurrent.futures

from libraries.testkit.admin import Admin
from libraries.testkit.cluster import Cluster
from libraries.testkit.verify import verify_changes
from libraries.testkit.verify import verify_same_docs
from keywords.constants import RBAC_FULL_ADMIN
from requests.auth import HTTPBasicAuth

from keywords.utils import log_info
from keywords.SyncGateway import sync_gateway_config_path_for_mode
from utilities.cluster_config_utils import get_sg_version, persist_cluster_config_environment_prop, copy_to_temp_conf


@pytest.mark.syncgateway
@pytest.mark.changes
@pytest.mark.basicauth
@pytest.mark.parametrize("sg_conf_name, num_users, num_docs, num_revisions", [
    ("sync_gateway_default_functional_tests_no_port", 1, 5000, 1),
    pytest.param("sync_gateway_default_functional_tests_couchbase_protocol_withport_11210", 1, 5000, 1, marks=pytest.mark.oscertify),
    ("sync_gateway_default_functional_tests", 1, 5000, 1),
    ("sync_gateway_default_functional_tests", 50, 5000, 1),
    ("sync_gateway_default_functional_tests", 50, 10, 10),
    ("sync_gateway_default_functional_tests_revslimit50", 50, 50, 1000)
])
def test_continuous_changes_parametrized(params_from_base_test_setup, sg_conf_name, num_users, num_docs, num_revisions):

    cluster_conf = params_from_base_test_setup["cluster_config"]
    mode = params_from_base_test_setup["mode"]
    ssl_enabled = params_from_base_test_setup["ssl_enabled"]
    need_sgw_admin_auth = params_from_base_test_setup["need_sgw_admin_auth"]

    sg_conf = sync_gateway_config_path_for_mode(sg_conf_name, mode)

    # Skip the test if ssl disabled as it cannot run without port using http protocol
    if ("sync_gateway_default_functional_tests_no_port" in sg_conf_name) and get_sg_version(cluster_conf) < "1.5.0":
        pytest.skip('couchbase/couchbases ports do not support for versions below 1.5')
    if "sync_gateway_default_functional_tests_no_port" in sg_conf_name and not ssl_enabled:
        pytest.skip('ssl disabled so cannot run without port')

    # Skip the test if ssl enabled as it cannot couchbase protocol
    # TODO : https://github.com/couchbaselabs/sync-gateway-accel/issues/227
    # Remove DI condiiton once above bug is fixed
    if "sync_gateway_default_functional_tests_couchbase_protocol_withport_11210" in sg_conf_name and (ssl_enabled or mode.lower() == "di"):
        pytest.skip('ssl enabled so cannot run with couchbase protocol')

    log_info("Running 'continuous_changes_parametrized'")
    log_info("cluster_conf: {}".format(cluster_conf))
    log_info("sg_conf: {}".format(sg_conf))
    log_info("num_users: {}".format(num_users))
    log_info("num_docs: {}".format(num_docs))
    log_info("num_revisions: {}".format(num_revisions))

    cluster = Cluster(config=cluster_conf)
    cluster.reset(sg_config_path=sg_conf)

    admin = Admin(cluster.sync_gateways[0])
    auth = need_sgw_admin_auth and (RBAC_FULL_ADMIN['user'], RBAC_FULL_ADMIN['pwd']) or None
    if auth:
        admin.auth = HTTPBasicAuth(auth[0], auth[1])
    users = admin.register_bulk_users(target=cluster.sync_gateways[0], db="db", name_prefix="user", number=num_users, password="password", channels=["ABC", "TERMINATE"])
    abc_doc_pusher = admin.register_user(target=cluster.sync_gateways[0], db="db", name="abc_doc_pusher", password="password", channels=["ABC"])
    doc_terminator = admin.register_user(target=cluster.sync_gateways[0], db="db", name="doc_terminator", password="password", channels=["TERMINATE"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:

        futures = {executor.submit(user.start_continuous_changes_tracking, termination_doc_id="killcontinuous"): user.name for user in users}
        futures[executor.submit(abc_doc_pusher.add_docs, num_docs)] = "doc_pusher"

        for future in concurrent.futures.as_completed(futures):
            task_name = futures[future]

            # Send termination doc to seth continuous changes feed subscriber
            if task_name == "doc_pusher":

                errors = future.result()
                assert len(errors) == 0
                abc_doc_pusher.update_docs(num_revs_per_doc=num_revisions)

                time.sleep(10)

                doc_terminator.add_doc("killcontinuous")
            elif task_name.startswith("user"):
                # When the user has continuous _changes feed closed, return the docs and verify the user got all the channel docs
                docs_in_changes = future.result()
                # Expect number of docs + the termination doc + _user doc
                verify_same_docs(expected_num_docs=num_docs, doc_dict_one=docs_in_changes, doc_dict_two=abc_doc_pusher.cache)

    # Expect number of docs + the termination doc
    verify_changes(abc_doc_pusher, expected_num_docs=num_docs, expected_num_revisions=num_revisions, expected_docs=abc_doc_pusher.cache)


@pytest.mark.syncgateway
@pytest.mark.changes
@pytest.mark.basicauth
@pytest.mark.parametrize("sg_conf_name, num_docs, num_revisions, x509_cert_auth", [
    ("sync_gateway_default_functional_tests", 10, 10, True),
    pytest.param("sync_gateway_default_functional_tests_no_port", 10, 10, False, marks=[pytest.mark.sanity, pytest.mark.oscertify]),
    ("sync_gateway_default_functional_tests_couchbase_protocol_withport_11210", 10, 10, False)
])
def test_continuous_changes_sanity(params_from_base_test_setup, sg_conf_name, num_docs, num_revisions, x509_cert_auth):
    cluster_conf = params_from_base_test_setup["cluster_config"]
    mode = params_from_base_test_setup["mode"]
    ssl_enabled = params_from_base_test_setup["ssl_enabled"]
    need_sgw_admin_auth = params_from_base_test_setup["need_sgw_admin_auth"]

    sg_conf = sync_gateway_config_path_for_mode(sg_conf_name, mode)

    # Skip the test if ssl disabled as it cannot run without port using http protocol
    if ("sync_gateway_default_functional_tests_no_port" in sg_conf_name) and get_sg_version(cluster_conf) < "1.5.0":
        pytest.skip('couchbase/couchbases ports do not support for versions below 1.5')
    if "sync_gateway_default_functional_tests_no_port" in sg_conf_name and not ssl_enabled:
        pytest.skip('ssl disabled so cannot run without port')

    # Skip the test if ssl enabled as it cannot run with couchbase protocol
    # TODO : https://github.com/couchbaselabs/sync-gateway-accel/issues/227
    # Remove DI condiiton once above bug is fixed
    if "sync_gateway_default_functional_tests_couchbase_protocol_withport_11210" in sg_conf_name and (ssl_enabled or mode.lower() == "di"):
        pytest.skip('ssl enabled so cannot run with couchbase protocol')

    log_info("Running 'continuous_changes_sanity'")
    log_info("cluster_conf: {}".format(cluster_conf))
    log_info("sg_conf: {}".format(sg_conf))
    log_info("num_docs: {}".format(num_docs))
    log_info("num_revisions: {}".format(num_revisions))

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

    admin = Admin(cluster.sync_gateways[0])
    auth = need_sgw_admin_auth and (RBAC_FULL_ADMIN['user'], RBAC_FULL_ADMIN['pwd']) or None
    if auth:
        admin.auth = HTTPBasicAuth(auth[0], auth[1])
    seth = admin.register_user(target=cluster.sync_gateways[0], db="db", name="seth", password="password", channels=["ABC", "TERMINATE"])
    abc_doc_pusher = admin.register_user(target=cluster.sync_gateways[0], db="db", name="abc_doc_pusher", password="password", channels=["ABC"])
    doc_terminator = admin.register_user(target=cluster.sync_gateways[0], db="db", name="doc_terminator", password="password", channels=["TERMINATE"])

    docs_in_changes = dict()

    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:

        futures = dict()
        futures[executor.submit(seth.start_continuous_changes_tracking, termination_doc_id="killcontinuous")] = "continuous"
        futures[executor.submit(abc_doc_pusher.add_docs, num_docs)] = "doc_pusher"

        for future in concurrent.futures.as_completed(futures):
            task_name = futures[future]

            # Send termination doc to seth continuous changes feed subscriber
            if task_name == "doc_pusher":
                abc_doc_pusher.update_docs(num_revs_per_doc=num_revisions)

                time.sleep(5)

                doc_terminator.add_doc("killcontinuous")
            elif task_name == "continuous":
                docs_in_changes = future.result()

    # Expect number of docs + the termination doc
    verify_changes(abc_doc_pusher, expected_num_docs=num_docs, expected_num_revisions=num_revisions, expected_docs=abc_doc_pusher.cache)

    # Expect number of docs + the termination doc + _user doc
    verify_same_docs(expected_num_docs=num_docs, doc_dict_one=docs_in_changes, doc_dict_two=abc_doc_pusher.cache)
