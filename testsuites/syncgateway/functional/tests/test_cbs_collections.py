import uuid
import pytest
import random
from keywords.ClusterKeywords import ClusterKeywords
from keywords.MobileRestClient import MobileRestClient
from keywords import couchbaseserver
from libraries.testkit.cluster import Cluster
from keywords.constants import RBAC_FULL_ADMIN
from libraries.testkit.admin import Admin
from keywords.exceptions import RestError
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError
from keywords import document
from libraries.data import doc_generators
from time import time, sleep

# test file shared variables
bucket = "data-bucket"
sg_password = "password"
admin_client = cb_server = sg_username = channels = client_auth = sg_url = None
admin_auth = [RBAC_FULL_ADMIN['user'], RBAC_FULL_ADMIN['pwd']]
is_using_views = False


@pytest.fixture
def teardown_doc_fixture():
    def _delete_doc_if_exist(sg_client, url, db, doc_id, auth, scope, collection):
        if sg_client.does_doc_exist(url, db, doc_id, scope=scope, collection=collection) is True:
            sg_client.delete_doc(url, db, doc_id, auth=auth, scope=scope, collection=collection)
    yield _delete_doc_if_exist


@pytest.fixture
def scopes_collections_tests_fixture(params_from_base_test_setup, params_from_base_suite_setup):
    # get/set the parameters
    global admin_client
    global cb_server
    global sg_username
    global channels
    global client_auth
    global sg_url
    global is_using_views
    is_using_views = params_from_base_suite_setup["use_views"]

    sync_gateway_version = params_from_base_test_setup["sync_gateway_version"]
    if sync_gateway_version < "3.1.0":
        pytest.skip('scopes and collection tests cannot be run in versions prior to 3.1.0')
    try:  # To be able to teardon in case of a setup error
        pre_test_db_exists = pre_test_user_exists = sg_client = sg_url = sg_admin_url = None
        random_suffix = str(uuid.uuid4())[:8]
        db_prefix = "db_"
        scope_prefix = "scope_"
        collection_prefix = "collection_"
        db = db_prefix + random_suffix
        scope = scope_prefix + random_suffix
        collection = collection_prefix + random_suffix
        sg_username = "scopes_collections_user" + random_suffix
        client_auth = HTTPBasicAuth(sg_username, sg_password)
        channels = ["ABC"]
        data = {"bucket": bucket, "scopes": {scope: {"collections": {collection: {}}}}, "num_index_replicas": 0}
        cluster_config = params_from_base_test_setup["cluster_config"]
        sg_admin_url = params_from_base_test_setup["sg_admin_url"]
        cluster_helper = ClusterKeywords(cluster_config)
        topology = cluster_helper.get_cluster_topology(cluster_config)
        cbs_url = topology["couchbase_servers"][0]
        sg_url = topology["sync_gateways"][0]["public"]
        cluster = Cluster(config=cluster_config)
        sg_client = MobileRestClient()
        cb_server = couchbaseserver.CouchbaseServer(cbs_url)
        admin_client = Admin(cluster.sync_gateways[0])
        sg_url = params_from_base_test_setup["sg_url"]

        # Scope creation on the Couchbase server
        does_scope_exist = cb_server.does_scope_exist(bucket, scope)
        if does_scope_exist is False:
            cb_server.create_scope(bucket, scope)
        cb_server.create_collection(bucket, scope, collection)

        # SGW database creation
        pre_test_db_exists = admin_client.does_db_exist(db)
        test_bucket_db = admin_client.get_bucket_db(bucket)
        if test_bucket_db is not None:
            admin_client.delete_db(test_bucket_db)
        if pre_test_db_exists is False:
            admin_client.create_db(db, data)

        # Create a user
        pre_test_user_exists = admin_client.does_user_exist(db, sg_username)
        if pre_test_user_exists is False:
            sg_client.create_user(sg_admin_url, db, sg_username, sg_password, auth=admin_auth)

        yield sg_client, sg_admin_url, db, scope, collection
    except Exception as e:
        raise e
    finally:
        # Cleanup everything that was created
        if (pre_test_user_exists is not None) and (pre_test_user_exists is False):
            admin_client.delete_user_if_exists(db, sg_username)
        if (pre_test_db_exists is not None) and (pre_test_db_exists is False):
            if admin_client.does_db_exist(db) is True:
                admin_client.delete_db(db)
        cb_server.delete_scope_if_exists(bucket, scope)


@pytest.mark.syncgateway
@pytest.mark.collections
def test_document_only_under_named_scope(scopes_collections_tests_fixture, teardown_doc_fixture):
    if is_using_views:
        pytest.skip("""It is not necessary to run scopes and collections tests with views.
                When it is enabled, there is a problem that affects the rest of the tests suite.""")

    # setup
    doc_prefix = "scp_tests_doc"
    doc_id = doc_prefix + "_0"
    sg_client, sg_admin_url, db, scope, collection = scopes_collections_tests_fixture
    if sg_client.does_doc_exist(sg_admin_url, db, doc_id, scope=scope, collection=collection) is False:
        sg_client.add_docs(sg_url, db, 1, doc_prefix, auth=client_auth, scope=scope, collection=collection)
    teardown_doc_fixture(sg_client, sg_admin_url, db, doc_id, auth=client_auth, scope=scope, collection=collection)

    # exercise + verification
    try:
        sg_client.get_doc(sg_admin_url, db, doc_id, scope=scope, collection=collection)
    except Exception as e:
        pytest.fail("There was a problem reading the document from a collection when specifying the scope in the endpoint. The error: " + str(e))

    # exercise + verification
    try:
        sg_client.get_doc(sg_admin_url, db, doc_id, collection=collection)
    except Exception as e:
        pytest.fail("There was a problem reading the document from a collection WITHOUT specifying the scope in the endoint. The error: " + str(e))

    #  exercise + verification
    with pytest.raises(Exception) as e:  # HTTPError doesn't work, for some  reason, but would be preferable
        sg_client.get_doc(sg_admin_url, db, doc_id, scope="_default", collection=collection)
    e.match("Not Found")


@pytest.mark.syncgateway
@pytest.mark.collections
def test_change_scope_or_collection_name(scopes_collections_tests_fixture):
    """
    1. Upload a document to a collection
    2. Rename the collection by updating the config
    3. Check that the document is not accessiable in the new collection
    4. Rename the collection to the original collection
    5. Verify that the document is accessible again
    6. Change the scope name and expect a "Bad Rquest" error
    """
    if is_using_views:
        pytest.skip("""It is not necessary to run scopes and collections tests with views.
                When it is enabled, there is a problem that affects the rest of the tests suite.""")

    # setup
    sg_client, sg_admin_url, db, scope, collection = scopes_collections_tests_fixture
    doc_prefix = "scp_tests_doc"
    doc_id = doc_prefix + "_0"
    new_collection_name = "new_collection_test"

    # 1. Upload a document to a collection
    if sg_client.does_doc_exist(sg_admin_url, db, doc_id, scope=scope, collection=collection) is False:
        sg_client.add_docs(sg_admin_url, db, 1, doc_prefix, scope=scope, collection=collection)

    # 2. Rename the collection by updating the config
    cb_server.create_collection(bucket, scope, new_collection_name)
    rename_a_single_scope_or_collection(db, scope, new_collection_name)

    #  exercise + verification
    with pytest.raises(Exception) as e:  # HTTPError doesn't work, for some reason, but would be preferable
        sg_client.get_doc(sg_admin_url, db, doc_id, scope=scope, collection=new_collection_name)
    e.match("Not Found")

    # 4. Rename the collection to the original collection
    rename_a_single_scope_or_collection(db, scope, collection)

    # 5. Verify that the document is accessible again
    try:
        sg_client.get_doc(sg_admin_url, db, doc_id, scope=scope, collection=collection)
    except Exception as e:
        pytest.fail("The document could not be read from the collection after it was renamed and renamed back. The error: " + str(e))
    # 6. Change the scope name and expect a "Bad Rquest" error
    with pytest.raises(Exception) as e:
        rename_a_single_scope_or_collection(db, "new_scope", collection)
    e.match("Bad Request")


@pytest.mark.syncgateway
@pytest.mark.collections
def test_collection_channels(scopes_collections_tests_fixture):
    """
    1. Create 3 users with different channels, one is in the wildcard channel
    2. Upload the documents to the collection, under the user's channels and one to the public channel
    3. Get all the documents using _all_docs
    4. Check that the users cannot see the documents in their channels with collection_access defined
    5. Check that the users see the shared document in the channel
    6. Check that _bulk_get cannot get documents that are not in the user's channel
    7. Check that _bulk_get can get documents that are in the user's channel
    8. Check that _bulk_get cannot get a document from the "right" channel but the wrong collection
    9. Check that the user have access to the docs the collection and specific channel
    """
    if is_using_views:
        pytest.skip("""It is not necessary to run scopes and collections tests with views.
                When it is enabled, there is a problem that affects the rest of the tests suite.""")
    # setup
    sg_client, sg_admin_url, db, scope, collection = scopes_collections_tests_fixture

    # Change the default sync function to be able to access the sahred channel, ["!"]
    sync_function = "function(doc){channel(doc.channels);}"
    data = {"bucket": bucket, "scopes": {scope: {"collections": {collection: {"sync": sync_function}}}}, "num_index_replicas": 0}
    admin_client.post_db_config(db, data)
    admin_client.wait_for_db_online(db, 60)

    random_str = str(uuid.uuid4())[:6]
    test_user_1 = "cu1_" + random_str
    test_user_2 = "cu2_" + random_str
    test_wildcard_user = "wu_" + random_str
    user_1_doc_prefix = "user_1_doc_" + random_str
    user_2_doc_prefix = "user_2_doc_" + random_str
    shared_doc_prefix = "shared_" + random_str
    channels_user_1 = ["USER1_CHANNEL"]
    channels_user_2 = ["USER2_CHANNEL"]
    auth_user_1 = test_user_1, sg_password
    auth_user_2 = test_user_2, sg_password
    auth_wildcard_user = test_wildcard_user, sg_password

    # 1. Create 3 users with different channels, one is in the wildcard channel
    sg_client.create_user(sg_admin_url, db, test_user_1, sg_password, channels=channels_user_1, auth=admin_auth)
    sg_client.create_user(sg_admin_url, db, test_user_2, sg_password, channels=channels_user_2, auth=admin_auth)
    sg_client.create_user(sg_admin_url, db, test_wildcard_user, sg_password, channels=["*"], auth=admin_auth)

    # 2. Upload the documents to the collection
    sg_client.add_docs(sg_url, db, 3, user_1_doc_prefix, auth=auth_user_1, channels=channels_user_1, scope=scope, collection=collection)
    uploaded_user2_docs = sg_client.add_docs(sg_url, db, 3, user_2_doc_prefix, auth=auth_user_2, channels=channels_user_2, scope=scope, collection=collection)
    uploaded_user2_docs_ids = [doc["id"] for doc in uploaded_user2_docs]
    shared_doc = sg_client.add_docs(sg_admin_url, db, 1, shared_doc_prefix, auth=client_auth, channels=["!"], scope=scope, collection=collection)

    # 3. Get all the documents using _all_docs
    user_1_docs = sg_client.get_all_docs(url=sg_url, db=db, auth=auth_user_1, include_docs=True, scope=scope, collection=collection)
    user_2_docs = sg_client.get_all_docs(url=sg_url, db=db, auth=auth_user_2, include_docs=True, scope=scope, collection=collection)
    wildcard_user_docs = sg_client.get_all_docs(url=sg_url, db=db, auth=auth_wildcard_user, include_docs=True, scope=scope, collection=collection)

    user_1_docs_ids = [doc["id"] for doc in user_1_docs["rows"]]
    user_2_docs_ids = [doc["id"] for doc in user_2_docs["rows"]]
    wildcard_user_docs_ids = [doc["id"] for doc in wildcard_user_docs["rows"]]
    shared_found_user_1 = False
    shared_found_user_2 = False

    # 4. Check that the users cannot see the documents in their channels with collection_access defined
    for doc in user_1_docs_ids:
        if (user_1_doc_prefix or user_2_doc_prefix) in doc:
            pytest.fail("The document " + doc + " must not be accessiable by any of the users, because 'collection_access' was not set, but it is")
        if shared_doc_prefix in doc:
            shared_found_user_1 = True
        if doc not in wildcard_user_docs_ids:
            pytest.fail("The document " + doc + " was not accessible even though the user was given all documents access")
    for doc in user_2_docs_ids:
        if (user_1_doc_prefix or user_2_doc_prefix) in doc:
            pytest.fail("The document " + doc + " must not be accessiable by any of the users, because 'collection_access' was not set, but it is")
        if shared_doc_prefix in doc:
            shared_found_user_2 = True
        if doc not in wildcard_user_docs_ids:
            pytest.fail("The document " + doc + " was not accessible even though the user was given all documents access")

    # 5. Check that the users see the shared document in their channels
    assert (shared_found_user_1 and shared_found_user_2), "The shared document was not found for one of the users. user1: " + str(shared_found_user_1) + " user2: " + str(shared_found_user_2)
    assert (shared_doc[0]["id"] in wildcard_user_docs_ids), "The shared document was not accessiable VIA the wildcard channel"

    # 6. Check that _bulk_get cannot get documents that are not in the user's channel
    with pytest.raises(RestError) as e:  # HTTPError doesn't work, for some  reason, but would be preferable
        sg_client.get_bulk_docs(url=sg_url, db=db, doc_ids=[uploaded_user2_docs[0]["id"]], auth=auth_user_1, scope=scope, collection=collection)
    assert "'status': 403" in str(e)
    # 7. Check that _bulk_get can get documents that are in the user's channel
    sg_client.get_bulk_docs(url=sg_url, db=db, doc_ids=user_1_docs_ids, auth=auth_user_1, scope=scope, collection=collection)

    # 8. Check that _bulk_get cannot get a document from the "right" channel but the wrong collection
    with pytest.raises(Exception) as e:
        sg_client.get_bulk_docs(url=sg_url, db=db, doc_ids=user_1_docs_ids, auth=auth_user_1, scope=scope, collection="fake_collection")
    e.match("Not Found")

    # 9. Check that now the user has access to the docs the collection and specific channel
    collection_access = {scope: {collection: {"admin_channels": channels_user_2}}}
    sg_client.update_user(sg_admin_url, db, test_user_2, channels=channels_user_2, collection_access=collection_access)
    user_2_docs = sg_client.get_all_docs(url=sg_url, db=db, auth=auth_user_2, include_docs=True, scope=scope, collection=collection)
    user_2_docs_ids = [doc["id"] for doc in user_2_docs["rows"]]

    for doc_id in uploaded_user2_docs_ids:
        if doc_id not in user_2_docs_ids:
            pytest.fail("user2 does not have access to the document " + doc_id + " in channel " + channels_user_2[0] + " although such access was given. docs ids found: " + str(user_2_docs_ids))


@pytest.mark.syncgateway
@pytest.mark.collections
def test_restricted_collection(scopes_collections_tests_fixture):
    """
    1. Create two more collections on CB server
    2. Add documents to the collections on CB server
    3. Sync two out of three collections to SGW
    4. Check that documents that are in the server restricted collection are not accessible via SGW
    """

    if is_using_views:
        pytest.skip("""It is not necessary to run scopes and collections tests with views.
                When it is enabled, there is a problem that affects the rest of the tests suite.""")

    sg_client, sg_admin_url, db, scope, collection = scopes_collections_tests_fixture
    # 1. Create two more collections on CB server
    random_suffix = str(uuid.uuid4())[:8]
    second_collection = "collection_2" + random_suffix
    third_collection = "collection_3" + random_suffix
    cb_server.create_collection(bucket, scope, second_collection)
    cb_server.create_collection(bucket, scope, third_collection)

    doc_1_key = "doc_1" + random_suffix
    doc_2_key = "doc_2" + random_suffix
    doc_3_key = "doc_3" + random_suffix

    # 2. Add a document to each collection
    cb_server.add_simple_document(doc_1_key, bucket, scope, collection)
    cb_server.add_simple_document(doc_2_key, bucket, scope, second_collection)
    cb_server.add_simple_document(doc_3_key, bucket, scope, third_collection)

    assert(cb_server.get_document(doc_1_key, bucket, scope, collection)["id"] == doc_1_key), "Error in test setup: failed to add document to server under " + bucket + "." + scope + "." + collection
    assert(cb_server.get_document(doc_2_key, bucket, scope, second_collection)["id"] == doc_2_key), "Error in test setup: failed to add document to server under " + bucket + "." + scope + "." + second_collection
    assert(cb_server.get_document(doc_3_key, bucket, scope, third_collection)["id"] == doc_3_key), "Error in test setup: failed to add document to server under " + bucket + "." + scope + "." + third_collection

    # 3. Sync two collections to SGW
    db_config = {"bucket": bucket, "scopes": {scope: {"collections": {collection: {}, second_collection: {}}}}, "num_index_replicas": 0,
                 "import_docs": True, "enable_shared_bucket_access": True}
    admin_client.post_db_config(db, db_config)
    admin_client.wait_for_db_online(db, 60)

    # 4. Check that documents in the server restricted collection are not accesible via SGW
    timeout = 15  # 15 seconds
    start = time()
    while True:
        all_docs_ids = []
        for row in (sg_client.get_all_docs(sg_admin_url, db, scope=scope, collection=collection)["rows"]):
            all_docs_ids.append(row["id"])
        for row in (sg_client.get_all_docs(sg_admin_url, db, scope=scope, collection=second_collection)["rows"]):
            all_docs_ids.append(row["id"])
        try:
            assert(len(all_docs_ids) == 2), "Number of expected documents in Sync Gateway database does not match expected. Expected 2; Found " + str(len(all_docs_ids))
            assert(doc_3_key not in all_docs_ids), "Sync Gateway contains document from server restricted collection. Document ID " + doc_3_key + "under " + bucket + "." + scope + "." + third_collection
            break
        except Exception as e:
            if time() - start > timeout:
                raise e
        sleep(1)


@pytest.mark.syncgateway
@pytest.mark.collections
def test_user_collections_access(scopes_collections_tests_fixture):
    """
    1. Add second collection to SGW db and server, using sync functions to restrict collection/scope level access
    2. Create two users, one with scope level access, one with collection level access
    3. Check document upload is restricted to correct access level
    4. Check document retrieval via all_docs and document ID is restricted to correct access level
    5. Check document deletion is restricted to correct access level
    """

    if is_using_views:
        pytest.skip("""It is not necessary to run scopes and collections tests with views.
                When it is enabled, there is a problem that affects the rest of the tests suite.""")

    sg_client, sg_admin_url, db, scope, collection = scopes_collections_tests_fixture
    random_suffix = str(uuid.uuid4())[:8]

    # 1. Add second collection to SGW db and server, using sync functions and collection_access fields to restrict collection/scope level access
    second_collection = "second_collection" + random_suffix
    cb_server.create_collection(bucket, scope, second_collection)

    db_config = {"bucket": bucket, "scopes": {scope: {"collections": {collection: {"sync": simple_sync_function(collection)}, second_collection: {"sync": simple_sync_function(second_collection)}}}}, "num_index_replicas": 0}
    admin_client.post_db_config(db, db_config)
    admin_client.wait_for_db_online(db, 60)

    # 2. Create two users, one with scope level access, one with collection level access
    scope_user = "scope_user" + random_suffix
    collection_user = "collection_user" + random_suffix

    scope_user_access = {scope: {collection: {"admin_channels": [collection]}, second_collection: {"admin_channels": [second_collection]}}}
    collection_user_access = {scope: {collection: {"admin_channels": [collection]}}}

    scope_user_auth = scope_user, sg_password
    collection_user_auth = collection_user, sg_password

    sg_client.create_user(sg_admin_url, db, scope_user, sg_password, collection_access=scope_user_access, auth=admin_auth)
    sg_client.create_user(sg_admin_url, db, collection_user, sg_password, collection_access=collection_user_access, auth=admin_auth)

    # 3. Check document upload is restricted to correct access level
    scope_user_doc_prefix = "scope_user_doc" + random_suffix
    collection_user_doc_prefix = "collection_user_doc" + random_suffix

    # Upload docs to both collections as scope_user
    add_docs_result = sg_client.add_docs(sg_url, db, 3, scope_user_doc_prefix, auth=scope_user_auth, channels=[second_collection], scope=scope, collection=second_collection)
    doc_ids_second_collection = ([doc["id"] for doc in add_docs_result])
    add_docs_result = sg_client.add_docs(sg_url, db, 3, scope_user_doc_prefix, auth=scope_user_auth, channels=[collection], scope=scope, collection=collection)
    doc_ids_collection = [doc["id"] for doc in add_docs_result]

    # Attempt to upload docs to both collections as collection_user
    add_docs_result = sg_client.add_docs(sg_url, db, 3, collection_user_doc_prefix, auth=collection_user_auth, channels=[collection], scope=scope, collection=collection)
    doc_ids_collection.extend([doc["id"] for doc in add_docs_result])
    with pytest.raises(HTTPError) as e:
        sg_client.add_docs(sg_url, db, 3, collection_user_doc_prefix, auth=collection_user_auth, channels=[second_collection], scope=scope, collection=second_collection)
    assert("403" in str(e)), "User without access to collection should generate 403 HTTPError when trying to upload documents to that collection. Instead got: \n" + str(e)

    # 4. Check document retrieval via all_docs and document ID is restricted to correct access level
    # Get all docs as scope_user
    scope_user_collection_docs = [row["id"] for row in sg_client.get_all_docs(sg_url, db, auth=scope_user_auth, scope=scope, collection=collection)["rows"]]
    scope_user_second_collection_docs = [row["id"] for row in sg_client.get_all_docs(sg_url, db, auth=scope_user_auth, scope=scope, collection=second_collection)["rows"]]

    # Validate scope_user all_docs endpoint functioning
    assert(len(scope_user_collection_docs) == len(doc_ids_collection)), f"_all_docs endpoint returned wrong number of docs for user with access to {collection}. Expected {len(doc_ids_collection)}, got {len(scope_user_collection_docs)}"
    assert(len(scope_user_second_collection_docs) == len(doc_ids_second_collection)), f"_all_docs endpoint returned wrong number of docs for user with access to {second_collection}. Expected {len(doc_ids_second_collection)}, got {len(scope_user_second_collection_docs)}"

    # Get all docs as collection_user
    collection_user_collection_docs = [row["id"] for row in sg_client.get_all_docs(sg_url, db, auth=collection_user_auth, scope=scope, collection=collection)["rows"]]
    collection_user_second_collection_docs = [row["id"] for row in sg_client.get_all_docs(sg_url, db, auth=collection_user_auth, scope=scope, collection=second_collection)["rows"]]

    # Validate collection_user all_docs endpoint functioning
    assert(len(collection_user_collection_docs) == len(doc_ids_collection)), f"_all_docs endpoint returned wrong number of docs for user with access to {collection}. Expected {len(doc_ids_collection)}, got {len(collection_user_collection_docs)}"
    assert(len(collection_user_second_collection_docs) == 0), f"_all_docs endpoint returned wrong number of docs for user without access to {second_collection}. Expected 0, got {len(collection_user_second_collection_docs)}"

    # Check that collection_user cannot GET document from second_collection
    second_collection_doc = random.choice(doc_ids_second_collection)
    with pytest.raises(HTTPError) as e:
        sg_client.get_doc(sg_url, db, second_collection_doc, auth=collection_user_auth, scope=scope, collection=second_collection)
    assert("403" in str(e)), "User without access to collection should generate 403 HTTPError when trying to GET document. Instead got: \n" + str(e)

    # 5. Check document deletion is restricted to correct access level
    second_collection_doc_rev = sg_client.get_doc(sg_url, db, second_collection_doc, auth=scope_user_auth, scope=scope, collection=second_collection)["_rev"]

    # Check collection_user cannot delete doc in second collection
    with pytest.raises(HTTPError) as e:
        sg_client.delete_doc(sg_url, db, second_collection_doc, rev=second_collection_doc_rev, auth=collection_user_auth, scope=scope, collection=second_collection)
    assert("403" in str(e)), "User without access to collection should generate 403 HTTPError when trying to DELETE document. Instead got: \n" + str(e)


@pytest.mark.syncgateway
@pytest.mark.collections
def test_apis_support_collections(scopes_collections_tests_fixture):
    """
    Specifically test various APIs:
    1.  Add documents using bulk_docs
    2.  Purge one of the documents
    3.  Get a raw document
    """
    if is_using_views:
        pytest.skip("""It is not necessary to run scopes and collections tests with views.
                When it is enabled, there is a problem that affects the rest of the tests suite.""")

    sg_client, sg_admin_url, db, scope, collection = scopes_collections_tests_fixture
    user_session = sg_client.create_session(url=sg_admin_url, db=db, name=sg_username)
    created_docs = document.create_docs(doc_id_prefix='collections_api_docs', number=3, channels=channels)
    created_doc_ids = []
    for doc_info in created_docs:
        created_doc_ids.append(doc_info["_id"])
    # 1. Add documents using bulk_docs
    sg_docs = sg_client.add_bulk_docs(url=sg_url, db=db, docs=created_docs, auth=user_session, scope=scope, collection=collection)
    uplodad_docs = sg_client.get_all_docs(url=sg_admin_url, db=db, include_docs=True, scope=scope, collection=collection)

    # Check that the document was added
    for doc_key in uplodad_docs["rows"]:
        if doc_key["id"] not in created_doc_ids:
            assert False, "The document " + doc_key["id"] + " was not uploaded using POST add_bulk"

    # 2. Purge one document
    bulk_doc = sg_client.get_doc(sg_admin_url, db, sg_docs[0]["id"], scope=scope, collection=collection)
    sg_client.purge_doc(sg_admin_url, db, bulk_doc, scope=scope, collection=collection)
    # Check that the document was purged
    with pytest.raises(Exception) as e:
        sg_client.get_doc(sg_admin_url, db, sg_docs[0]["id"], scope=scope, collection=collection)
    e.match("Not Found")

    # 3.  Get a raw document
    raw_doc = sg_client.get_raw_doc(sg_admin_url, db, sg_docs[1]["id"], auth=user_session, scope=scope, collection=collection)
    assert uplodad_docs["rows"][1]["value"]["rev"] == raw_doc["_sync"]["rev"], "The wrong raw document was fetched"


@pytest.mark.syncgateway
@pytest.mark.collections
def test_import_filters(scopes_collections_tests_fixture):
    """
    Specifically test various APIs:
    1.  Update the db config's import filter.
    2.  Upload 2 documents to the server, only one matches the filter.
    3.  Get the docment that should not be imported - expect an error.
    4.  Get the document that meets the import criteria - no error expected.
    5.  Update the db's import filter using the API to accept only the second document
    6.  Check that the second document was imported
    """
    sg_client, sg_admin_url, db, scope, collection = scopes_collections_tests_fixture
    random_suffix = str(uuid.uuid4())[:8]
    doc_1_id = "should_be_in_sgw_" + random_suffix
    doc_2_id = "should_not_be_in_sgw_" + random_suffix

    # 1. Update the db config's import filter.
    import_function = "function filter(doc) { return doc.id == \"" + doc_1_id + "\"}"
    data = {"bucket": bucket, "scopes": {scope: {"collections": {collection: {"import_filter": import_function}}}}, "num_index_replicas": 0, "import_docs": True, "enable_shared_bucket_access": True}
    admin_client.post_db_config(db, data)

    # 2. Upload 2 documents to the server, only one matches the filter
    cb_server.add_simple_document(doc_1_id, bucket, scope, collection)
    cb_server.add_simple_document(doc_2_id, bucket, scope, collection)

    # 3. Get the docment that should not be imported - expect an error.
    with pytest.raises(Exception) as e:
        sg_client.get_doc(sg_admin_url, db, doc_2_id, scope=scope, collection=collection)
    e.match("Not Found")

    # 4.  Get the document that meets the import criteria - no error expected.
    sg_client.get_doc(sg_admin_url, db, doc_1_id, scope=scope, collection=collection)

    # 5.  Update the db's import filter using the API to accept only the second document
    import_function = "function filter(doc) { return doc.id == \"" + doc_2_id + "\" }"
    admin_client.create_imp_fltr_func(db, import_function, scope, collection)

    # 6. Check that the second document was imported
    sg_client.get_doc(sg_admin_url, db, doc_2_id, scope=scope, collection=collection)


@pytest.mark.syncgateway
@pytest.mark.collections
@pytest.mark.adminauth
def test_collection_stats(scopes_collections_tests_fixture):
    """
    1. Verify that global stats and scopes/collection stats can be procured via RBAC users
    2. Add two new collections on CB server, rename SGW collection to map to it, adding new collection and enable import + sync functions
    3. Verify that stats parameters update to reflect new collections
    4. Make several API calls to affect stats as different users
    5. Verify stats reflect changes from API calls correctly
    """

    if is_using_views:
        pytest.skip("""It is not necessary to run scopes and collections tests with views.
                When it is enabled, there is a problem that affects the rest of the tests suite.""")

    sg_client, sg_admin_url, db, scope, collection = scopes_collections_tests_fixture
    random_suffix = str(uuid.uuid4())[:8]

    # 1. Verify that global stats and scopes/collection stats can be procured

    # create rbac users on CB server
    rbac_auth_sgw_dev_ops = ["devops", "password"]
    rbac_auth_stats_reader = ["reader", "password"]

    cb_server._create_internal_rbac_user_by_roles(rbac_auth_stats_reader[0], "external_stats_reader")
    cb_server._create_internal_rbac_user_by_roles(rbac_auth_sgw_dev_ops[0], "sync_gateway_dev_ops")

    # retrieve stats as admin and rbac users
    # weekly testkit runs are ran with --disable-admin-auth, making the use of auth redundant
    # run without flag  to test RBAC access
    auths = [rbac_auth_sgw_dev_ops, rbac_auth_stats_reader, admin_auth]
    for auth in auths:
        stats = sg_client.get_expvars(sg_admin_url, auth)
        verify_stats_retrieval(stats, auth, db, scope, collection)

    # 2. Add two new collections on CB server, rename SGW collection to map to it, adding new collection and enable import + sync functions
    second_collection = "second_collection" + random_suffix
    third_collection = "third_collection" + random_suffix

    second_collection_doc_key = "doc2" + random_suffix
    third_collection_doc_key = "doc3" + random_suffix

    cb_server.create_collection(bucket, scope, second_collection)
    cb_server.create_collection(bucket, scope, third_collection)

    custom_sync = f"function(doc, oldDoc) {{requireAccess(\"{third_collection}\"); if (doc._id == \"forbidden_doc\") {{throw({{incrementExceptionStat: \"forbidden doc to increment exception stat in test\"}})}} channel(\"{third_collection}\")}}"

    db_config = {"bucket": bucket, "scopes": {scope: {"collections": {third_collection: {"sync": custom_sync}, second_collection: {"sync": simple_sync_function(second_collection)}}}},
                 "num_index_replicas": 0, "import_docs": True, "enable_shared_bucket_access": True}
    admin_client.post_db_config(db, db_config)
    admin_client.wait_for_db_online(db, 60)

    # 3. Verify that stats parameters update to reflect new collections
    renamed_stats = sg_client.get_expvars(sg_admin_url, admin_auth)

    get_collection_stats(db, scope, second_collection, renamed_stats)
    get_collection_stats(db, scope, third_collection, renamed_stats)

    # 4. Make several API calls to affect stats as different users

    # Create users for making API calls
    second_user = "second_user" + random_suffix
    third_user = "third_user" + random_suffix

    second_user_doc_prefix = "second_user_doc"
    third_user_doc_prefix = "third_user_doc"

    second_user_access = {scope: {second_collection: {"admin_channels": [second_collection]}}}
    third_user_access = {scope: {third_collection: {"admin_channels": [third_collection]}}}

    second_user_auth = second_user, sg_password
    third_user_auth = third_user, sg_password

    sg_client.create_user(sg_admin_url, db, second_user, sg_password, collection_access=second_user_access, auth=admin_auth)
    sg_client.create_user(sg_admin_url, db, third_user, sg_password, collection_access=third_user_access, auth=admin_auth)

    # Add docs to CB server for import
    cb_server.add_simple_document(second_collection_doc_key, bucket, scope, second_collection)
    cb_server.add_simple_document(third_collection_doc_key, bucket, scope, third_collection)
    cb_server.add_simple_document(second_collection_doc_key + "2", bucket, scope, second_collection)

    # Upload docs as second_user to second_collection, try upload as third_user to second_collection and fail
    sg_client.add_docs(sg_url, db, 3, second_user_doc_prefix, auth=second_user_auth, scope=scope, collection=second_collection)
    with pytest.raises(HTTPError) as e:
        sg_client.add_docs(sg_url, db, 1, third_user_doc_prefix, auth=third_user_auth, scope=scope, collection=second_collection)
    assert("403" in str(e)), "User without access to collection should generate 403 HTTPError when trying to add document. Instead got: \n" + str(e)

    # Upload doc as third_user to third_collection, try upload as second_user to third_collection and fail
    sg_client.add_docs(sg_url, db, 3, third_user_doc_prefix, auth=third_user_auth, scope=scope, collection=third_collection)
    with pytest.raises(HTTPError) as e:
        sg_client.add_docs(sg_url, db, 3, second_user_doc_prefix, auth=second_user_auth, scope=scope, collection=third_collection)
    assert("403" in str(e)), "User without access to collection should generate 403 HTTPError when trying to add document. Instead got: \n" + str(e)

    # upload doc with doc._id==forbidden_doc to third_collection and be rejected by sync function
    doc_body = doc_generators.simple()
    doc_body["_id"] = "forbidden_doc"
    with pytest.raises(HTTPError) as e:
        sg_client.add_doc(sg_url, db, doc_body, auth=third_user_auth, use_post=False, scope=scope, collection=third_collection)
    assert("500" in str(e)), "Sync function should generate 500 HTTPError when trying to add document. Instead got: \n" + str(e)

    # Read doc from second_collection as second_user, read from third_collection as third_user, fail reading from second_collection as third_user
    sg_client.get_doc(sg_url, db, second_collection_doc_key, auth=second_user_auth, scope=scope, collection=second_collection)
    sg_client.get_doc(sg_url, db, third_collection_doc_key, auth=third_user_auth, scope=scope, collection=third_collection)
    with pytest.raises(HTTPError) as e:
        sg_client.get_doc(sg_url, db, second_collection_doc_key, auth=third_user_auth, scope=scope, collection=second_collection)
    assert("403" in str(e)), "User without access to collection should generate 403 HTTPError when trying to GET document. Instead got: \n" + str(e)

    # 5. Verify stats reflect changes from API calls correctly
    timeout = 15  # 15 seconds
    start = time()
    while True:
        new_stats = sg_client.get_expvars(sg_admin_url, admin_auth)
        try:
            verify_collection_stats(db, scope, second_collection, third_collection, new_stats)
            break
        except Exception as e:
            if time() - start > timeout:
                raise e
        sleep(1)


def rename_a_single_scope_or_collection(db, scope, new_name):
    data = {"bucket": bucket, "scopes": {scope: {"collections": {new_name: {}}}}, "num_index_replicas": 0}
    admin_client.post_db_config(db, data)
    admin_client.wait_for_db_online(db, 60)


def get_collection_stats(db, scope, collection, stats):
    try:
        collection_stats = stats["syncgateway"]["per_db"][db]["per_collection"][scope + "." + collection]
        assert isinstance(collection_stats, dict), f"syncgateway.per_db.{db}.per_collection.{scope}.{collection} was not found in stats after collection added to SGW database"
        return collection_stats
    except KeyError as k:
        return str(k)


def verify_stats_retrieval(stats, auth, db, scope, collection):
    """
    Helper function for test_collection_stats
    Verify stats can be procured as RBAC roles sgw_dev_ops, external_stats_reader and full admin
    Verify correct stats are included, with correct initial values
    """
    collection_stats_keys = ["num_doc_writes", "num_doc_reads", "doc_writes_bytes", "doc_reads_bytes", "import_count", "sync_function_time",
                             "sync_function_count", "sync_function_reject_access_count", "sync_function_reject_count", "sync_function_exception_count"]

    try:
        global_stats = stats["syncgateway"]["global"]
    except KeyError:
        assert False, f"Could not retrieve global stats via _expvar endpoint using RBAC user {auth[0]}"
    else:
        assert len(global_stats) != 0, f"Global stats are not reported correctly \n + {str(global_stats)}"

    collection_stats = get_collection_stats(db, scope, collection, stats)

    for key in collection_stats_keys:
        try:
            assert collection_stats[key] == 0, f"{key} statistic should be 0, got {collection_stats[key]}"
        except KeyError:
            assert False, f"{key} statistic does not exist"


def simple_sync_function(collection):
    """Constructs a simple sync function that requires access to a collection to upload a document, and routes uploaded documents to default channel"""
    return f"function(doc, oldDoc) {{requireAccess(\"{collection}\"); channel(\"{collection}\")}}"


def verify_collection_stats(db, scope, second_collection, third_collection, stats_to_verify):
    """
    Helper function for test_collection_stats
    Assert that stats are expected values after making various API calls in test
    """

    second_collection_stats = get_collection_stats(db, scope, second_collection, stats_to_verify)
    third_collection_stats = get_collection_stats(db, scope, third_collection, stats_to_verify)

    # stats that have expected value
    expected_stats = {
        "sync_function_count": (6, 6),
        "sync_function_reject_count": (1, 1),
        "sync_function_reject_access_count": (1, 1),
        "sync_function_exception_count": (0, 1),
        "import_count": (2, 1),
        "num_doc_reads": (2, 1),
        "num_doc_writes": (5, 4)
    }

    # stats expected to be greater than 0
    expected_positive_stats = ["sync_function_time", "doc_reads_bytes", "doc_writes_bytes"]

    for stat, expected in expected_stats.items():
        assert second_collection_stats[stat] == expected[0], f"{second_collection} {stat} should be {expected[0]}, got {second_collection_stats[stat]}"
        assert third_collection_stats[stat] == expected[1], f"{third_collection} {stat} should be {expected[1]}, got {third_collection_stats[stat]}"
    for positive_stat in expected_positive_stats:
        assert second_collection_stats[positive_stat] > 0, f"{second_collection} {positive_stat} should be greater than 0, got {second_collection_stats[positive_stat]}"
        assert third_collection_stats[positive_stat] > 0, f"{third_collection} {positive_stat} should be greater than 0, got {third_collection_stats[positive_stat]}"
