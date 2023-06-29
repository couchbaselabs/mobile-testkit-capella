from random import randint
import pytest
import time

from keywords.MobileRestClient import MobileRestClient
from keywords.utils import log_info
from CBLClient.Database import Database
from CBLClient.Replication import Replication
from CBLClient.Array import Array
from CBLClient.Blob import Blob
from keywords.utils import random_string, get_embedded_asset_file_path
from CBLClient.Dictionary import Dictionary
from CBLClient.Authenticator import Authenticator

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
    appService_url_public = params_from_base_test_setup["appService_url_public"]
    appService_url_admin = params_from_base_test_setup["appService_url_admin"]
    appService_blip_url = params_from_base_test_setup["target_blip_url"]
    base_url = params_from_base_test_setup["base_url"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]

    channels_sg = ["valid_values"]
    admin_username = "admin"
    admin_password = "Password123,"
    username = "user"+str(randint(1,1000))
    password = "Password123,"
    number_of_updates = 2

    # Create CBL database
    sg_client = MobileRestClient()
    db.create_bulk_docs(num_of_docs, "cbl_azure", db=cbl_db, channels=channels_sg)

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


@pytest.mark.listener
@pytest.mark.replication
@pytest.mark.parametrize("blob_data_type", [
    pytest.param('stream', marks=pytest.mark.sanity)
])
def test_blob_contructor_replication(params_from_base_test_setup, blob_data_type):
    '''
    @summary:
    1. Create docs in CBL
    2. Do push replication
    3. update docs in CBL with attachment in specified blob type
    4. Do push replication after docs update
    5. Verify blob content replicated successfully
    '''

    appService_url_public = params_from_base_test_setup["appService_url_public"]
    appService_url_admin = params_from_base_test_setup["appService_url_admin"]
    appService_blip_url = params_from_base_test_setup["target_blip_url"]
    base_url = params_from_base_test_setup["base_url"]
    db = params_from_base_test_setup["db"]
    cbl_db = params_from_base_test_setup["source_db"]
    liteserv_platform = params_from_base_test_setup["liteserv_platform"]

    num_of_docs = 10
    channels_sg = ["blob_constructor"]
    admin_username = "admin"
    admin_password = "Password123,"
    username = "user"+str(randint(1,1000))
    password = "Password123,"

    if "c-" in liteserv_platform and blob_data_type == "file_url":
        pytest.skip('This test cannot run for C platforms')

    sg_client = MobileRestClient()
    auth = (admin_username, admin_password)
    sg_client.create_user(appService_url_admin, None, username, password, channels=channels_sg, auth=auth)
    cookie, session_id = sg_client.create_session(appService_url_admin, username, auth=auth)
    # session = cookie, session_id

    # 1. Create docs in CBL
    db.create_bulk_docs(num_of_docs, "cbl_sync", db=cbl_db, channels=channels_sg)

    # 2. Do push replication
    replicator = Replication(base_url)
    authenticator = Authenticator(base_url)
    replicator_authenticator = authenticator.authentication(session_id, cookie, authentication_type="session")
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=appService_blip_url,
                                              continuous=True,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="push")
    replicator.stop(repl)
    session = cookie, session_id
    sg_docs = sg_client.get_all_docs(url=appService_url_public, include_docs=True, auth=session)["rows"]
    # Verify database doc counts
    cbl_doc_count = db.getCount(cbl_db)
    assert len(sg_docs) == cbl_doc_count, "Expected number of docs does not exist in sync-gateway after replication"

    # 3. update docs in CBL with attachment in specified blob type
    blob = Blob(base_url)
    dictionary = Dictionary(base_url)

    doc_ids = db.getDocIds(cbl_db)
    cbl_db_docs = db.getDocuments(cbl_db, doc_ids)
    for doc_id, doc_body in list(cbl_db_docs.items()):
        mutable_dictionary = dictionary.toMutableDictionary(doc_body)
        dictionary.setString(mutable_dictionary, "new_field_string_1", random_string(length=30))
        dictionary.setString(mutable_dictionary, "new_field_string_2", random_string(length=80))

        image_location = get_embedded_asset_file_path(liteserv_platform, db, cbl_db, "golden_gate_large.jpg")

        if blob_data_type == "byte_array":
            image_byte_array = blob.createImageContent(image_location, cbl_db)
            blob_value = blob.create("image/jpeg", content=image_byte_array)
        elif blob_data_type == "stream":
            image_stream = blob.createImageStream(image_location, cbl_db)
            blob_value = blob.create("image/jpeg", stream=image_stream)
        elif blob_data_type == "file_url":
            image_file_url = blob.createImageFileUrl(image_location)
            blob_value = blob.create("image/jpeg", file_url=image_file_url)

        dictionary.setBlob(mutable_dictionary, "new_field_blob", blob_value)
        doc_body_new = dictionary.toMap(mutable_dictionary)
        db.updateDocument(database=cbl_db, data=doc_body_new, doc_id=doc_id)

    # 4. Do push replication after docs update
    repl = replicator.configure_and_replicate(source_db=cbl_db,
                                              target_url=appService_blip_url,
                                              continuous=True,
                                              replicator_authenticator=replicator_authenticator,
                                              replication_type="push")

    replicator.stop(repl)

    # 5. Verify blob content replicated successfully
    doc_ids = db.getDocIds(cbl_db)
    cbl_db_docs = db.getDocuments(cbl_db, doc_ids)
    for doc_id, doc_body in list(cbl_db_docs.items()):
        sg_data = sg_client.get_doc(url=appService_url_public, db=None,doc_id=doc_id, auth=session)
        assert "new_field_string_1" in sg_data, "Updated docs failed to get replicated"
        assert "new_field_string_2" in sg_data, "Updated docs failed to get replicated"
        assert "new_field_blob" in sg_data, "Updated docs failed to get replicated"
