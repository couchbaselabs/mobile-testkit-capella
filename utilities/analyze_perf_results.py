import json
import datetime
import os
import sys
import matplotlib
import matplotlib.pyplot as plt
from optparse import OptionParser
from collections import OrderedDict

matplotlib.rcParams.update({'font.size': 6})


def keys_present(keys, dictionary):
    for key in keys:
        if key not in dictionary:
            # only plot timestamps with all info
            return False
    return True


def plot_gateload_expvars(figure, json_file_name):

    print("Plotting gateload expvars ...")

    with open(json_file_name, "r") as f:
        obj = json.loads(f.read(), object_pairs_hook=OrderedDict)

    datetimes = []
    p95 = []
    p99 = []
    docs_pushed = []
    docs_pulled = []

    for timestamp in obj:

        # only plot if p95 and p99 exist in expvars
        if "PushToSubscriberInteractive" in obj[timestamp]["expvars"]["gateload"]["ops"]:
            datetimes.append(datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f"))
            p95.append(obj[timestamp]["expvars"]["gateload"]["ops"]["PushToSubscriberInteractive"]["p95"])
            p99.append(obj[timestamp]["expvars"]["gateload"]["ops"]["PushToSubscriberInteractive"]["p99"])
            docs_pushed.append(obj[timestamp]["expvars"]["gateload"]["total_doc_pushed"])
            docs_pulled.append(obj[timestamp]["expvars"]["gateload"]["total_doc_pulled"])

    # Plot p95 / p99
    ax1 = figure.add_subplot(211)
    ax1.set_title("PushToSubscriberInteractive: p95 (blue) / p99 ns (green)")
    ax1.plot(datetimes, p95, "bs", datetimes, p99, "g^")
    # for i, j in zip(datetimes, p95):
    #     ax1.annotate(str(j), xy=(i, j))

    # Plot docs pushed / docs pulled
    ax2 = figure.add_subplot(212)
    ax2.set_title("total_doc_pushed (red) / total_doc_pulled (yellow)")
    ax2.plot(datetimes, docs_pushed, "rs", datetimes, docs_pulled, "y^")

    figure.autofmt_xdate()


def plot_sync_gateway_expvars(figure, json_file_name):

    print("Plotting sync_gateway expvars ...")

    with open(json_file_name, "r") as f:
        obj = json.loads(f.read(), object_pairs_hook=OrderedDict)

    datetimes = []
    memstats_alloc = []
    memstats_sys = []

    for timestamp in obj:
        datetimes.append(datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f"))
        memstats_alloc.append(obj[timestamp]["expvars"]["memstats"]["Alloc"])
        memstats_sys.append(obj[timestamp]["expvars"]["memstats"]["Sys"])

    # Plot Alloc / Sys
    ax1 = figure.add_subplot(111)
    ax1.set_title("memstats.Alloc (blue) / memstats.Sys (green)")
    ax1.plot(datetimes, memstats_alloc, "bs", datetimes, memstats_sys, "g^")

    figure.autofmt_xdate()


def plot_machine_stats(figure, folder_path):

    print("Plotting machine stats ...")

    folders = [x[0] for x in os.walk(folder_path)]

    machine_stats = dict()
    # entry at one is the first subdirect
    for subfolder in folders[1:]:

        # Get name of sg
        path_components = os.path.split(subfolder)
        name = path_components[len(path_components) - 1]

        # Get CPU stats dict for sg
        with open("{}/cpu_stats.json".format(subfolder), "r") as f:
            obj = json.loads(f.read())
            machine_stats[name] = obj

    ax3 = figure.add_subplot(111)
    ax3.set_title("CPU percent (sg1=blue, sg2=green, sg3=red, sg4=cyan, sg5=magenta, sg6=yellow, else=black)")

    for machine in machine_stats:
        entity = machine_stats[machine]

        datetimes = []
        cpu_percents = []

        # create a list of timestamps with the corresponding CPU percent
        for timestamp in entity.keys():
            datetimes.append(datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f"))
            cpu_percents.append(entity[timestamp]["cpu_percent"])

        # Hack to show different machines in different color
        if machine == "sg1":
            color = "b"
        elif machine == "sg2":
            color = "g"
        elif machine == "sg3":
            color = "r"
        elif machine == "sg4":
            color = "c"
        elif machine == "sg5":
            color = "m"
        elif machine == "sg6":
            color = "y"
        else:
            color = "k"

        ax3.plot(datetimes, cpu_percents, "{}o".format(color))

    figure.autofmt_xdate()


def analze_perf_results(test_id):

    print("Generating graphs for {}".format(test_id))

    # Generate plot of gateload expvars
    fig1 = plt.figure()
    fig1.text(0.5, 0.04, 'Gateload Expvars', ha='center', va='center')
    plot_gateload_expvars(fig1, "performance_results/{}/gateload_expvars.json".format(test_id))
    plt.savefig("performance_results/{}/gateload_expvars.png".format(test_id), dpi=300)

    # Generate plot of sync_gateway expvars
    fig2 = plt.figure()
    fig2.text(0.5, 0.04, 'sync_gateway expvars', ha='center', va='center')
    plot_sync_gateway_expvars(fig2, "performance_results/{}/sync_gateway_expvars.json".format(test_id))
    plt.savefig("performance_results/{}/sync_gateway_expvars.png".format(test_id), dpi=300)

    # Generate plot of machine stats
    fig3 = plt.figure()
    fig3.text(0.5, 0.04, 'sync_gateway CPU', ha='center', va='center')
    plot_machine_stats(fig3, "performance_results/{}/perf_logs/".format(test_id))
    plt.savefig("performance_results/{}/sync_gateway_machine_stats.png".format(test_id), dpi=300)

if __name__ == "__main__":
    usage = """usage: analyze_perf_results.py
    --test-id=<test-id>
    """

    parser = OptionParser(usage=usage)

    parser.add_option("", "--test-id",
                      action="store", type="string", dest="test_id", default=None,
                      help="Test id to generate graphs for")

    arg_parameters = sys.argv[1:]

    (opts, args) = parser.parse_args(arg_parameters)

    if opts.test_id is None:
        print("You must provide a test identifier to run the test")
        sys.exit(1)

    analze_perf_results(opts.test_id)
