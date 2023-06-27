import pytest
import time
import os
import random

from keywords.MobileRestClient import MobileRestClient
from keywords.ClusterKeywords import ClusterKeywords
from keywords import couchbaseserver
from keywords.utils import log_info
from CBLClient.Database import Database
from CBLClient.Replication import Replication
from CBLClient.Document import Document
from CBLClient.Authenticator import Authenticator
from concurrent.futures import ThreadPoolExecutor
from libraries.testkit.prometheus import verify_stat_on_prometheus
from keywords.SyncGateway import sync_gateway_config_path_for_mode
from keywords import document, attachment
from libraries.testkit import cluster
from utilities.cluster_config_utils import persist_cluster_config_environment_prop, copy_to_temp_conf
from keywords.attachment import generate_2_png_100_100
from keywords.SyncGateway import SyncGateway
from libraries.testkit.syncgateway import get_buckets_from_sync_gateway_config
from keywords.constants import RBAC_FULL_ADMIN


@pytest.fixture(scope="function")
def setup_teardown_test(params_from_base_test_setup):
    cbl_db_name = "cbl_db"
    base_url = params_from_base_test_setup["base_url"]
    db = Database(base_url)
    db_config = db.configure()
    log_info("Creating db")
    cbl_db = db.create(cbl_db_name, db_config)

    yield{
        "db": db,
        "cbl_db": cbl_db,
        "cbl_db_name": cbl_db_name
    }

    log_info("Deleting the db")
    db.deleteDB(cbl_db)


@pytest.mark.listener
@pytest.mark.replication
@pytest.mark.parametrize("num_of_docs, continuous, x509_cert_auth", [
    pytest.param(10, True, True, marks=pytest.mark.sanity)
])
def test_replication_configuration_valid_values(params_from_base_test_setup, num_of_docs, continuous, x509_cert_auth):
    """
        @summary:
        1. Create CBL DB and create bulk doc in CBL
        2. Configure replication with valid values of valid cbl Db, valid target url
        3. Start replication with push and pull
        4. Verify replication is successful and verify docs exist
    """
    sg_db = "db"
    appService_url_public = params_from_base_test_setup["appService_url_public"]
    appService_url_admin = params_from_base_test_setup["appService_url_admin"]
    appService_blip_url = params_from_base_test_setup["target_blip_url"]
    base_url = params_from_base_test_setup["base_url"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]

    channels_sg = ["ABC"]
    admin_username = "admin"
    admin_password = "Password123,"
    username = "user"
    password = "Password123,"
    number_of_updates = 2

    # Create CBL database
    sg_client = MobileRestClient()
    db.create_bulk_docs(num_of_docs, "cbl", db=cbl_db, channels=channels_sg)

    # Configure replication with push_pull
    replicator = Replication(base_url)
    auth = (admin_username, admin_password)
    sg_client.create_user(appService_url_admin, None, username, password, channels=channels_sg, auth=auth)
    session, replicator_authenticator, repl = replicator.create_session_configure_replicate(
        base_url, appService_url_admin, username, password, channels_sg, sg_client, cbl_db, appService_blip_url, continuous=continuous, replication_type="push_pull", auth=auth)

    sg_docs = sg_client.get_all_docs(url=appService_url_public, auth=session)
    sg_client.update_docs(url=appService_url_public, db=None, docs=sg_docs["rows"], number_updates=number_of_updates, auth=session)
    replicator.wait_until_replicator_idle(repl)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "total is not equal to completed"
    time.sleep(2)  # wait until replication is done
    sg_docs = sg_client.get_all_docs(url=appService_url_public, include_docs=True, auth=session)
    sg_docs = sg_docs["rows"] 

    # Verify database doc counts
    cbl_doc_count = db.getCount(cbl_db)
    assert len(sg_docs) == cbl_doc_count, "Expected number of docs does not exist in sync-gateway after replication"

    time.sleep(2)
    cbl_doc_ids = db.getDocIds(cbl_db)
    cbl_db_docs = db.getDocuments(cbl_db, cbl_doc_ids)
    count = 0
    for doc in cbl_doc_ids:
        if continuous:
            while count < 30:
                time.sleep(0.5)
                log_info("Checking {} for updates".format(doc))
                if cbl_db_docs[doc]["updates"] == number_of_updates:
                    break
                else:
                    log_info("{} is missing updates, Retrying...".format(doc))
                    count += 1
                    cbl_db_docs = db.getDocuments(cbl_db, cbl_doc_ids)
            assert cbl_db_docs[doc]["updates"] == number_of_updates, "updates did not get updated"
        else:
            assert cbl_db_docs[doc]["updates"] == 0, "sync-gateway updates got pushed to CBL for one shot replication"
    replicator.stop(repl)