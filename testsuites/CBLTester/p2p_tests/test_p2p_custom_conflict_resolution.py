import pytest
from time import sleep

from CBLClient.Replication import Replication
from CBLClient.PeerToPeer import PeerToPeer
from keywords.utils import random_string, log_info
from testsuites.CBLTester.CBL_Functional_tests.TestSetup_FunctionalTests.test_delta_sync import property_updater


@pytest.mark.p2p
@pytest.mark.listener
@pytest.mark.custom_conflict
@pytest.mark.replication
@pytest.mark.parametrize("replicator_type, endpoint_type", [
    ("pull", "URLEndPoint"),
    ("pull", "MessageEndPoint"),
    ("push_pull", "URLEndPoint"),
    ("push_pull", "MessageEndPoint")
])
def test_p2p_local_wins_custom_conflicts(params_from_base_test_setup, server_setup, replicator_type, endpoint_type):
    """
    @summary:
    1. Create few docs in client and get them replicated to server. Stop the replication once docs are replicated.
    2. Update docs couple of times with different updates on both client and server. This will create conflict.
    3. Start the replication with local_win CCR algorithm
    4. Verifies that client has retains its changes. For push and pull replication on server changes should be override with
    that of client
    """
    num_of_docs = 10
    base_url_list = server_setup["base_url_list"]
    cbl_db_server = server_setup["cbl_db_server"]
    cbl_db_list = server_setup["cbl_db_list"]
    channels = ["peerToPeer"]

    host_list = params_from_base_test_setup["host_list"]
    db_obj_list = params_from_base_test_setup["db_obj_list"]
    db_name_list = params_from_base_test_setup["db_name_list"]
    liteserv_versions = params_from_base_test_setup["version_list"]
    base_url_client = base_url_list[1]
    replicator = Replication(base_url_client)

    peer_to_peer_client = PeerToPeer(base_url_client)
    db_obj_server = db_obj_list[0]
    cbl_db_client = cbl_db_list[1]
    db_obj_client = db_obj_list[1]
    db_name_server = db_name_list[0]
    server_host = host_list[0]
    peer_to_peer_server = PeerToPeer(base_url_list[0])

    for liteserv_version in liteserv_versions:
        if liteserv_version < "2.6.0":
            pytest.skip("CCR is supported from 2.6.0 onwards")

    if endpoint_type == "URLEndPoint":
        replicator_tcp_listener = peer_to_peer_server.server_start(cbl_db_server)
        url_listener_port = peer_to_peer_server.get_url_listener_port(replicator_tcp_listener)
    else:
        url_listener_port = 5000

    db_obj_server.create_bulk_docs(num_of_docs, "local_win", db=cbl_db_server, channels=channels)
    # Now set up client
    repl = peer_to_peer_client.configure(port=url_listener_port, host=server_host, server_db_name=db_name_server, client_database=cbl_db_client,
                                         continuous=True, replication_type=replicator_type, endPointType=endpoint_type)
    peer_to_peer_client.client_start(repl)
    replicator.wait_until_replicator_idle(repl)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "replication from client to server did not completed " + str(total) +\
                               " not equal to " + str(completed)
    server_docs_count = db_obj_server.getCount(cbl_db_server)
    assert server_docs_count == num_of_docs, "Number of docs is not equivalent to number of docs in server "
    replicator.stop(repl)

    # creating conflict for docs
    doc_ids = db_obj_client.getDocIds(cbl_db_client)

    # updating docs on client side
    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    for doc_id in client_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = client_cbl_docs[doc_id]
            data = property_updater(data)
            data["client_random"] = random_string(length=10, printable=True)
            db_obj_client.updateDocument(cbl_db_client, doc_id=doc_id, data=data)

    # updating docs on client side
    server_cbl_docs = db_obj_server.getDocuments(cbl_db_server, doc_ids)
    for doc_id in server_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = server_cbl_docs[doc_id]
            data = property_updater(data)
            data["server_random"] = random_string(length=10, printable=True)
            db_obj_server.updateDocument(cbl_db_server, doc_id=doc_id, data=data)

    repl = peer_to_peer_client.configure(port=url_listener_port, host=server_host, server_db_name=db_name_server, client_database=cbl_db_client,
                                         continuous=True, replication_type=replicator_type, endPointType=endpoint_type,
                                         conflict_resolver="local_wins")
    peer_to_peer_client.client_start(repl)
    replicator.wait_until_replicator_idle(repl)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "replication from client to server did not completed " + str(total) +\
                               " not equal to " + str(completed)
    replicator.stop(repl)

    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    server_cbl_docs = db_obj_server.getDocuments(cbl_db_server, doc_ids)
    if replicator_type == "pull":
        for doc_id in server_cbl_docs:
            server_cbl_doc = server_cbl_docs[doc_id]
            client_cbl_doc = client_cbl_docs[doc_id]
            assert server_cbl_doc["sg_new_update1"] != client_cbl_doc["sg_new_update1"], "CCR failed to resolve " \
                                                                                         "conflict with local win"
            assert server_cbl_doc["sg_new_update2"] != client_cbl_doc["sg_new_update2"], "CCR failed to resolve " \
                                                                                         "conflict with local win"
            assert server_cbl_doc["sg_new_update3"] != client_cbl_doc["sg_new_update3"], "CCR failed to resolve " \
                                                                                         "conflict with local win"
            assert "server_random" not in client_cbl_doc, "CCR failed to resolve conflict with local win"
            assert "client_random" not in server_cbl_doc, "CCR failed to resolve conflict with local win"
    elif replicator_type == "push_pull":
        for doc_id in server_cbl_docs:
            server_cbl_doc = server_cbl_docs[doc_id]
            client_cbl_doc = client_cbl_docs[doc_id]
            assert server_cbl_doc["sg_new_update1"] == client_cbl_doc["sg_new_update1"], "CCR failed to resolve" \
                                                                                         " conflict with local win"
            assert server_cbl_doc["sg_new_update2"] == client_cbl_doc["sg_new_update2"], "CCR failed to resolve " \
                                                                                         "conflict with local win"
            assert server_cbl_doc["sg_new_update3"] == client_cbl_doc["sg_new_update3"], "CCR failed to resolve " \
                                                                                         "conflict with local win"
            assert "server_random" not in client_cbl_doc, "CCR failed to resolve conflict with local win"
            assert "client_random" in server_cbl_doc, "CCR failed to resolve conflict with local win"
    if endpoint_type == "URLEndPoint":
        peer_to_peer_server.server_stop(replicator_tcp_listener, endpoint_type)


@pytest.mark.p2p
@pytest.mark.listener
@pytest.mark.custom_conflict
@pytest.mark.replication
@pytest.mark.parametrize("replicator_type, endpoint_type", [
    ("pull", "URLEndPoint"),
    ("pull", "MessageEndPoint"),
    ("push_pull", "URLEndPoint"),
    pytest.param("push_pull", "MessageEndPoint", marks=pytest.mark.sanity)
])
def test_p2p_remote_wins_custom_conflicts(params_from_base_test_setup, server_setup, replicator_type, endpoint_type):
    """
    @summary:
    1. Create few docs in Client and get them replicated to Server. Stop the replication once docs are replicated.
    2. Update docs couple of times with different updates on both Server and Client app. This will create conflict.
    3. Start the replication with remote_wins CCR algorithm
    4. Verifies that CBL hasn't retains its changes. For push and pull replication server changes should retain its changes
    """
    num_of_docs = 10
    base_url_list = server_setup["base_url_list"]
    cbl_db_server = server_setup["cbl_db_server"]
    cbl_db_list = server_setup["cbl_db_list"]
    channels = ["peerToPeer"]

    host_list = params_from_base_test_setup["host_list"]
    db_obj_list = params_from_base_test_setup["db_obj_list"]
    db_name_list = params_from_base_test_setup["db_name_list"]
    liteserv_versions = params_from_base_test_setup["version_list"]
    base_url_client = base_url_list[1]
    replicator = Replication(base_url_client)

    peer_to_peer_client = PeerToPeer(base_url_client)
    db_obj_server = db_obj_list[0]
    cbl_db_client = cbl_db_list[1]
    db_obj_client = db_obj_list[1]
    db_name_server = db_name_list[0]
    server_host = host_list[0]
    peer_to_peer_server = PeerToPeer(base_url_list[0])

    for liteserv_version in liteserv_versions:
        if liteserv_version < "2.6.0":
            pytest.skip("CCR is supported from 2.6.0 onwards")

    if endpoint_type == "URLEndPoint":
        replicator_tcp_listener = peer_to_peer_server.server_start(cbl_db_server)
        url_listener_port = peer_to_peer_server.get_url_listener_port(replicator_tcp_listener)
    else:
        url_listener_port = 5000

    db_obj_server.create_bulk_docs(num_of_docs, "remote_win", db=cbl_db_server, channels=channels)
    # Now set up client
    repl = peer_to_peer_client.configure(port=url_listener_port, host=server_host, server_db_name=db_name_server, client_database=cbl_db_client,
                                         continuous=True, replication_type=replicator_type, endPointType=endpoint_type)
    peer_to_peer_client.client_start(repl)
    replicator.wait_until_replicator_idle(repl)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "replication from client to server did not completed " + str(total) +\
                               " not equal to " + str(completed)
    server_docs_count = db_obj_server.getCount(cbl_db_server)
    assert server_docs_count == num_of_docs, "Number of docs is not equivalent to number of docs in server "
    replicator.stop(repl)

    # creating conflict for docs
    doc_ids = db_obj_client.getDocIds(cbl_db_client)

    # updating docs on client side
    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    for doc_id in client_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = client_cbl_docs[doc_id]
            data = property_updater(data)
            data["client_random"] = random_string(length=10, printable=True)
            db_obj_client.updateDocument(cbl_db_client, doc_id=doc_id, data=data)

    # updating docs on client side
    server_cbl_docs = db_obj_server.getDocuments(cbl_db_server, doc_ids)
    for doc_id in server_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = server_cbl_docs[doc_id]
            data = property_updater(data)
            data["server_random"] = random_string(length=10, printable=True)
            db_obj_server.updateDocument(cbl_db_server, doc_id=doc_id, data=data)

    repl = peer_to_peer_client.configure(port=url_listener_port, host=server_host, server_db_name=db_name_server, client_database=cbl_db_client,
                                         continuous=True, replication_type=replicator_type, endPointType=endpoint_type,
                                         conflict_resolver="remote_wins")
    peer_to_peer_client.client_start(repl)
    replicator.wait_until_replicator_idle(repl)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "replication from client to server did not completed " + str(total) +\
                               " not equal to " + str(completed)
    replicator.stop(repl)

    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    server_cbl_docs = db_obj_server.getDocuments(cbl_db_server, doc_ids)
    for doc_id in server_cbl_docs:
        server_cbl_doc = server_cbl_docs[doc_id]
        client_cbl_doc = client_cbl_docs[doc_id]
        assert server_cbl_doc["sg_new_update1"] == client_cbl_doc["sg_new_update1"], "CCR failed to resolve conflict " \
                                                                                     "with remote win"
        assert server_cbl_doc["sg_new_update2"] == client_cbl_doc["sg_new_update2"], "CCR failed to resolve conflict " \
                                                                                     "with remote win"
        assert server_cbl_doc["sg_new_update3"] == client_cbl_doc["sg_new_update3"], "CCR failed to resolve conflict " \
                                                                                     "with remote win"
        assert "server_random" in client_cbl_doc, "CCR failed to resolve conflict with remote win"
        assert "client_random" not in client_cbl_doc, "CCR failed to resolve conflict with remote win"
    if endpoint_type == "URLEndPoint":
        peer_to_peer_server.server_stop(replicator_tcp_listener, endpoint_type)


@pytest.mark.p2p
@pytest.mark.listener
@pytest.mark.custom_conflict
@pytest.mark.replication
@pytest.mark.parametrize("replicator_type, endpoint_type", [
    ("pull", "URLEndPoint"),
    ("pull", "MessageEndPoint"),
    ("push_pull", "URLEndPoint"),
    ("push_pull", "MessageEndPoint")
])
def test_p2p_merge_wins_custom_conflicts(params_from_base_test_setup, server_setup, replicator_type, endpoint_type):
    """
    @summary:
    1. Create few docs in Client and get them replicated to Server. Stop the replication once docs are replicated.
    2. Update docs couple of times with different updates on both Server and Client. This will create conflict.
    3. Start the replication with remote_wins CCR algorithm
    4. Verifies that Client hasn't retains its changes. For push and pull replication Server changes should retain its changes
    """
    num_of_docs = 10
    base_url_list = server_setup["base_url_list"]
    cbl_db_server = server_setup["cbl_db_server"]
    cbl_db_list = server_setup["cbl_db_list"]
    channels = ["peerToPeer"]

    host_list = params_from_base_test_setup["host_list"]
    db_obj_list = params_from_base_test_setup["db_obj_list"]
    db_name_list = params_from_base_test_setup["db_name_list"]
    liteserv_versions = params_from_base_test_setup["version_list"]
    base_url_client = base_url_list[1]
    replicator = Replication(base_url_client)

    peer_to_peer_client = PeerToPeer(base_url_client)
    db_obj_server = db_obj_list[0]
    cbl_db_client = cbl_db_list[1]
    db_obj_client = db_obj_list[1]
    db_name_server = db_name_list[0]
    server_host = host_list[0]
    peer_to_peer_server = PeerToPeer(base_url_list[0])

    for liteserv_version in liteserv_versions:
        if liteserv_version < "2.6.0":
            pytest.skip("CCR is supported from 2.6.0 onwards")

    if endpoint_type == "URLEndPoint":
        replicator_tcp_listener = peer_to_peer_server.server_start(cbl_db_server)
        url_listener_port = peer_to_peer_server.get_url_listener_port(replicator_tcp_listener)
    else:
        url_listener_port = 5000

    db_obj_server.create_bulk_docs(num_of_docs, "remote_win", db=cbl_db_server, channels=channels)
    # Now set up client
    repl = peer_to_peer_client.configure(port=url_listener_port, host=server_host, server_db_name=db_name_server, client_database=cbl_db_client,
                                         continuous=True, replication_type=replicator_type, endPointType=endpoint_type)
    peer_to_peer_client.client_start(repl)
    replicator.wait_until_replicator_idle(repl)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "replication from client to server did not completed " + str(total) +\
                               " not equal to " + str(completed)
    server_docs_count = db_obj_server.getCount(cbl_db_server)
    assert server_docs_count == num_of_docs, "Number of docs is not equivalent to number of docs in server "
    replicator.stop(repl)

    # creating conflict for docs
    doc_ids = db_obj_client.getDocIds(cbl_db_client)

    # updating docs on client side
    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    for doc_id in client_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = client_cbl_docs[doc_id]
            data = property_updater(data)
            data["client_random"] = random_string(length=10, printable=True)
            db_obj_client.updateDocument(cbl_db_client, doc_id=doc_id, data=data)

    # updating docs on client side
    server_cbl_docs = db_obj_server.getDocuments(cbl_db_server, doc_ids)
    for doc_id in server_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = server_cbl_docs[doc_id]
            data = property_updater(data)
            data["server_random"] = random_string(length=10, printable=True)
            db_obj_server.updateDocument(cbl_db_server, doc_id=doc_id, data=data)

    repl = peer_to_peer_client.configure(port=url_listener_port, host=server_host, server_db_name=db_name_server, client_database=cbl_db_client,
                                         continuous=True, replication_type=replicator_type, endPointType=endpoint_type,
                                         conflict_resolver="merge")
    peer_to_peer_client.client_start(repl)
    replicator.wait_until_replicator_idle(repl)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "replication from client to server did not completed " + str(total) +\
                               " not equal to " + str(completed)
    replicator.stop(repl)

    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    server_cbl_docs = db_obj_server.getDocuments(cbl_db_server, doc_ids)
    if replicator_type == "pull":
        for doc_id in server_cbl_docs:
            server_cbl_doc = server_cbl_docs[doc_id]
            client_cbl_doc = client_cbl_docs[doc_id]
            assert server_cbl_doc["sg_new_update1"] != client_cbl_doc["sg_new_update1"], "CCR failed to resolve" \
                                                                                         " conflict with merge win"
            assert server_cbl_doc["sg_new_update2"] != client_cbl_doc["sg_new_update2"], "CCR failed to resolve " \
                                                                                         "conflict with merge win"
            assert server_cbl_doc["sg_new_update3"] != client_cbl_doc["sg_new_update3"], "CCR failed to resolve " \
                                                                                         "conflict with merge win"
            assert "server_random" in client_cbl_doc, "CCR failed to resolve conflict with merge win"
            assert "cbl_random" not in server_cbl_doc, "CCR failed to resolve conflict with merge win. Server doc got " \
                                                       "updated with CBL changes"
    elif replicator_type == "push_pull":
        for doc_id in server_cbl_docs:
            server_cbl_doc = server_cbl_docs[doc_id]
            client_cbl_doc = client_cbl_docs[doc_id]
            assert server_cbl_doc["sg_new_update1"] == client_cbl_doc["sg_new_update1"], "CCR failed to resolve " \
                                                                                         "conflict with merge win"
            assert server_cbl_doc["sg_new_update2"] == client_cbl_doc["sg_new_update2"], "CCR failed to resolve " \
                                                                                         "conflict with merge win"
            assert server_cbl_doc["sg_new_update3"] == client_cbl_doc["sg_new_update3"], "CCR failed to resolve " \
                                                                                         "conflict with merge win"
            assert "server_random" in client_cbl_doc, "CCR failed to resolve conflict with merge win"
            assert "client_random" in server_cbl_doc, "CCR failed to resolve conflict with merge win"

    if endpoint_type == "URLEndPoint":
        peer_to_peer_server.server_stop(replicator_tcp_listener, endpoint_type)


@pytest.mark.p2p
@pytest.mark.listener
@pytest.mark.custom_conflict
@pytest.mark.replication
@pytest.mark.parametrize("replicator_type, endpoint_type", [
    ("pull", "URLEndPoint"),
    ("pull", "MessageEndPoint"),
    ("push_pull", "URLEndPoint"),
    ("push_pull", "MessageEndPoint")
])
def test_p2p_non_blocking_custom_conflicts(params_from_base_test_setup, server_setup, replicator_type, endpoint_type):
    """
    @summary:
    1. Create few docs in app and get them replicated to Server. Stop the replication once docs are replicated.
    2. Update docs couple of times with different updates on both Client apps. This will create conflict.
    3. Start the replication with delayed_local_wins CCR algorithm and update some docs during CCR is resolving conflicts
    4. Verifies that client app hasn't retains its changes. For push and pull replication Client changes should have its changes on Server
    """
    num_of_docs = 10
    base_url_list = server_setup["base_url_list"]
    cbl_db_server = server_setup["cbl_db_server"]
    cbl_db_list = server_setup["cbl_db_list"]
    channels = ["peerToPeer"]

    host_list = params_from_base_test_setup["host_list"]
    db_obj_list = params_from_base_test_setup["db_obj_list"]
    db_name_list = params_from_base_test_setup["db_name_list"]
    liteserv_versions = params_from_base_test_setup["version_list"]
    base_url_client = base_url_list[1]
    replicator = Replication(base_url_client)

    peer_to_peer_client = PeerToPeer(base_url_client)
    db_obj_server = db_obj_list[0]
    cbl_db_client = cbl_db_list[1]
    db_obj_client = db_obj_list[1]
    db_name_server = db_name_list[0]
    server_host = host_list[0]
    peer_to_peer_server = PeerToPeer(base_url_list[0])

    for liteserv_version in liteserv_versions:
        if liteserv_version < "2.6.0":
            pytest.skip("CCR is supported from 2.6.0 onwards")

    if endpoint_type == "URLEndPoint":
        replicator_tcp_listener = peer_to_peer_server.server_start(cbl_db_server)
        url_listener_port = peer_to_peer_server.get_url_listener_port(replicator_tcp_listener)
    else:
        url_listener_port = 5000

    db_obj_server.create_bulk_docs(num_of_docs, "remote_win", db=cbl_db_server, channels=channels)
    # Now set up client
    repl = peer_to_peer_client.configure(port=url_listener_port, host=server_host, server_db_name=db_name_server, client_database=cbl_db_client,
                                         continuous=True, replication_type=replicator_type, endPointType=endpoint_type)
    peer_to_peer_client.client_start(repl)
    replicator.wait_until_replicator_idle(repl)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "replication from client to server did not completed " + str(total) +\
                               " not equal to " + str(completed)
    server_docs_count = db_obj_server.getCount(cbl_db_server)
    assert server_docs_count == num_of_docs, "Number of docs is not equivalent to number of docs in server "
    replicator.stop(repl)

    # creating conflict for docs
    doc_ids = db_obj_client.getDocIds(cbl_db_client)

    # updating docs on client side
    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    for doc_id in client_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = client_cbl_docs[doc_id]
            data = property_updater(data)
            data["client_random"] = random_string(length=10)
            db_obj_client.updateDocument(cbl_db_client, doc_id=doc_id, data=data)

    # updating docs on client side
    server_cbl_docs = db_obj_server.getDocuments(cbl_db_server, doc_ids)
    for doc_id in server_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = server_cbl_docs[doc_id]
            data = property_updater(data)
            data["server_random"] = random_string(length=10)
            db_obj_server.updateDocument(cbl_db_server, doc_id=doc_id, data=data)

    repl = peer_to_peer_client.configure(port=url_listener_port, host=server_host, server_db_name=db_name_server, client_database=cbl_db_client,
                                         continuous=True, replication_type=replicator_type, endPointType=endpoint_type,
                                         conflict_resolver="delayed_local_win")
    peer_to_peer_client.client_start(repl)
    # updating docs on client side
    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    new_docs_body = {}
    for doc_id in client_cbl_docs:
        for _ in range(2):
            log_info("Updating CBL Doc - {}".format(doc_id))
            data = client_cbl_docs[doc_id]
            data = property_updater(data)
            new_docs_body[doc_id] = [data]
            data["update_during_CCR"] = random_string(length=10)
            db_obj_client.updateDocument(cbl_db_client, doc_id=doc_id, data=data)
            # Saving the history of update to CBL doc
            new_docs_body[doc_id].append(data)
    replicator.wait_until_replicator_idle(repl, sleep_time=12)
    # Double checking that the complete replication is done as delayed CCR might give false idle for replication
    sleep(2)
    replicator.wait_until_replicator_idle(repl, sleep_time=12)
    total = replicator.getTotal(repl)
    completed = replicator.getCompleted(repl)
    assert total == completed, "replication from client to server did not completed " + str(total) +\
                               " not equal to " + str(completed)
    replicator.stop(repl)

    client_cbl_docs = db_obj_client.getDocuments(cbl_db_client, doc_ids)
    server_cbl_docs = db_obj_server.getDocuments(cbl_db_server, doc_ids)
    for doc_id in server_cbl_docs:
        server_cbl_doc = server_cbl_docs[doc_id]
        client_cbl_doc = client_cbl_docs[doc_id]
        if replicator_type == "pull":
            assert server_cbl_doc["sg_new_update1"] != client_cbl_doc["sg_new_update1"], "CCR failed to resolve " \
                                                                                         "conflict with delayed " \
                                                                                         "local win"
            assert server_cbl_doc["sg_new_update2"] != client_cbl_doc["sg_new_update2"], "CCR failed to resolve " \
                                                                                         "conflict with delayed " \
                                                                                         "local win"
            assert server_cbl_doc["sg_new_update3"] != client_cbl_doc["sg_new_update3"], "CCR failed to resolve " \
                                                                                         "conflict with delayed " \
                                                                                         "local win"
            assert "server_random" not in client_cbl_doc, "CCR failed to resolve conflict with delayed local win"
            assert "client_random" not in server_cbl_doc, "CCR failed to resolve conflict with delayed local win"
            assert new_docs_body[doc_id][1]["update_during_CCR"] == client_cbl_doc["update_during_CCR"],\
                "CCR failed to resolve conflict with delayed local win"
        elif replicator_type == "push_pull":
            assert server_cbl_doc["sg_new_update1"] == client_cbl_doc["sg_new_update1"], "CCR failed to resolve " \
                                                                                         "conflict with delayed " \
                                                                                         "local win"
            assert server_cbl_doc["sg_new_update2"] == client_cbl_doc["sg_new_update2"], "CCR failed to resolve " \
                                                                                         "conflict with delayed " \
                                                                                         "local win"
            assert server_cbl_doc["sg_new_update3"] == client_cbl_doc["sg_new_update3"], "CCR failed to resolve " \
                                                                                         "conflict with delayed " \
                                                                                         "local win"
            assert "server_random" not in server_cbl_doc, "CCR failed to resolve conflict with delayed local win"
            assert "client_random" in server_cbl_doc, "CCR failed to resolve conflict with delayed local win"
            assert client_cbl_doc["update_during_CCR"] == server_cbl_doc["update_during_CCR"],\
                "CCR failed to resolve conflict with delayed local win"
    if endpoint_type == "URLEndPoint":
        peer_to_peer_server.server_stop(replicator_tcp_listener, endpoint_type)
