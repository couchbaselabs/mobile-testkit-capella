import pytest

from keywords.MobileRestClient import MobileRestClient
from libraries.testkit.cluster import Cluster
from requests import Session
from keywords.utils import log_info
from keywords.SyncGateway import SyncGateway
from keywords.SyncGateway import sync_gateway_config_path_for_mode
from utilities.cluster_config_utils import persist_cluster_config_environment_prop, copy_to_temp_conf
from keywords.constants import RBAC_FULL_ADMIN
from requests.auth import HTTPBasicAuth


@pytest.mark.sanity
@pytest.mark.syncgateway
@pytest.mark.changes
@pytest.mark.oscertify
@pytest.mark.parametrize("sg_conf_name, x509_cert_auth", [
    ("sync_gateway_default", False),
])
def test_deleted_docs_from_changes_active_only(params_from_base_test_setup, sg_conf_name, x509_cert_auth):
    """
    https://github.com/couchbase/sync_gateway/issues/2955
    1. Create a document
    2. Delete the document
    3. Restart Sync Gateway (to force rebuild of cache from view)
    4. Issue an active_only=true changes request
    5. Issue an active_only=false changes request
    The deleted document was not being included in the result set in step 5.
    """
    cluster_config = params_from_base_test_setup["cluster_config"]
    topology = params_from_base_test_setup["cluster_topology"]
    need_sgw_admin_auth = params_from_base_test_setup["need_sgw_admin_auth"]
    sg_admin_url = topology["sync_gateways"][0]["admin"]
    sg_db = "db"
    num_docs = 10
    mode = params_from_base_test_setup["mode"]
    sg_conf = sync_gateway_config_path_for_mode(sg_conf_name, mode)

    disable_tls_server = params_from_base_test_setup["disable_tls_server"]
    if x509_cert_auth and disable_tls_server:
        pytest.skip("x509 test cannot run tls server disabled")
    if x509_cert_auth:
        temp_cluster_config = copy_to_temp_conf(cluster_config, mode)
        persist_cluster_config_environment_prop(temp_cluster_config, 'x509_certs', True)
        persist_cluster_config_environment_prop(temp_cluster_config, 'server_tls_skip_verify', False)
        cluster_config = temp_cluster_config

    cluster = Cluster(cluster_config)
    cluster.reset(sg_conf)
    client = MobileRestClient()

    auth = need_sgw_admin_auth and (RBAC_FULL_ADMIN['user'], RBAC_FULL_ADMIN['pwd']) or None
    # Add doc to SG
    added_doc = client.add_docs(
        url=sg_admin_url,
        db=sg_db,
        number=num_docs,
        id_prefix="test_changes",
        auth=auth
    )

    # Delete 1 doc
    doc_id = added_doc[0]["id"]
    log_info("Deleting {}".format(doc_id))
    doc = client.get_doc(url=sg_admin_url, db=sg_db, doc_id=doc_id, auth=auth)
    doc_rev = doc['_rev']
    client.delete_doc(sg_admin_url, sg_db, doc_id, doc_rev, auth=auth)

    # Restart SG
    sg_obj = SyncGateway()
    sg_obj.restart_sync_gateways(cluster_config)

    # Changes request with active_only=true
    session = Session()
    if auth:
        session.auth = HTTPBasicAuth(auth[0], auth[1])
    request_url = "{}/{}/_changes?active_only=true".format(sg_admin_url, sg_db)
    log_info("Issuing changes request {}".format(request_url))
    resp = session.get(request_url)
    resp.raise_for_status()
    resp_obj = resp.json()
    log_info("Checking that the deleted doc is not included in the active_only=true changes request")
    for d in resp_obj["results"]:
        assert doc_id not in d

    # Changes request with active_only=false
    request_url = "{}/{}/_changes?active_only=false".format(sg_admin_url, sg_db)
    log_info("Issuing changes request {}".format(request_url))
    resp = session.get(request_url)
    resp.raise_for_status()
    resp_obj = resp.json()
    doc_found = False
    for d in resp_obj["results"]:
        if doc_id != d["id"]:
            continue
        else:
            assert doc_id == d["id"]
            assert d["deleted"]
            doc_found = True
            break

    log_info("Checking that the deleted doc is included in the active_only=false changes request")
    assert doc_found
