
This repository contains Mobile QE Functional / Integration tests. 


```
$ git clone https://github.com/couchbaselabs/sync-gateway-testcluster.git
```

The mobile test suites leverage Robot Framework (http://robotframework.org/) as an organization platform as well as a test runner and reporter. 

### IMPORTANT
### Due to resource paths and dependencies, running all scripts and tests should be done from the root of the repository. 

The repo is organized as following

## libraries
   
### provision

### testkit

### utilities

## testsuites

### android

* listener

### grocerysync

### syncgateway

* functional

* performance


## Setup

### Install dependencies

**Install dependencies**

```
$ brew install libcouchbase 
$ brew install node
npm install -g appium
```

**Install Python via brew**

If you are on OSX El Capitan, you must install docker via brew rather than using the system python due to [Pip issue 3165](https://github.com/pypa/pip/issues/3165).

```
$ brew install python
```

After you install it, you should see that the python installed via brew is the default python:

```
$ which python
/usr/local/bin/python
$ python --version
Python 2.7.10
```

Set up virtualenv install python dependencies

```
$ [sudo] pip install virtualenv
```

```
cd sync-gateway-testcluster/
virtualenv -p /usr/bin/python2.7 venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment

* Setup Global Ansible Config

```
$ cd sync-gateway-testcluster/libraries/provision/ansible/playbooks
$ cp ansible.cfg.example ansible.cfg
$ vi ansible.cfg  # edit to your liking
```

* Add current directory to $PYTHONPATH. This will pick the custom libraries and allow you to use them

```
$ export PYTHONPATH=$PYTHONPATH:.
```

## Running Tests

### android 
* listener

### grocerysync

### sgcollectinfo

### syncgateway -> functional

#### Setup
1. Create a pool.json of endpoints you would like to target (IPs or AWS ec2 endpoints). Rename resources/pool.json.example -> resources/pool.json. Update the fake ips with your endpoints.
2. Install keys (Only required if you do not have ssh access without password). 

`python libraries/utilities/install_keys.py --key-name=sample_key.pub --ssh-user=root` 

This will deploy key to each of the endpoints defined in your pool.json file. 
3. Run 

`python libraries/utilities/generate_clusters_from_pool.py`. 

This converts the pool you supplied to cluster definitions required for provisioning and running the tests. The generated configurations will be in 'resources/cluster_configs/'.

#### Running the tests
Run the whole suite 

`robot -v SERVER_VERSION:4.1.0 -v SYNC_GATEWAY_VERSION:1.2.0-79 testsuites/syncgateway/functional/ `

Run a single suite  

`robot -v SERVER_VERSION:4.1.0 -v SYNC_GATEWAY_VERSION:1.2.0-79 testsuites/syncgateway/functional/1sg_1cbs.robot`

Run a single test   

`robot -v SERVER_VERSION:4.1.0 -v SYNC_GATEWAY_VERSION:1.2.0-79 -t "test bulk get compression no compression" testsuites/syncgateway/functional/1sg_1cbs.robot`

### syncgateway -> performance

In progress ...

#### Setup
1. Create and AWS CloudFormation Stack. Make sure you have set up AWS credential described above in 'Dependencies'

`python libraries/provision/create_and_instantiate_cluster.py --stackname="TestPerfStack" --num-servers=3 --server-type="c3.2xlarge" --num-sync-gateways=2 --sync-gateway-type="c3.2xlarge" --num-gatlings=1 --gatling-type="c3.2xlarge"`

2. Generate an ansible inventory from your CloudFormation Stack. The generated 'aws_perf_config' file will be written to 'resources/cluster_configs'

`
python libraries/provision/generate_ansible_inventory_from_aws.py --stackname="TestPerfStack" --targetfile="aws_perf_config"
`

3. Edit 'aws_perf_config' to reflect the number of writers you require
4. Run the performance tests

`robot testsuites/syncgateway/performance/minimatrix.robot`

5. Teardown the CloudFormation Stack

`python libraries/provision/teardown_cluster.py --stackname="TestPerfStack`



















































* Set CLUSTER_CONFIG environment variable. This will provide a target for the provisioning scripts to use.

IMPORTANT: This will be overwritten to run some tests. This will be explained in the 'Running syncgateway functional tests section'

```
export CLUSTER_CONFIG=resources/cluster_configs/<your_cluster_config>
```

** AWS Environment requirements

* Add boto configuration

```
$ cd ~/ 
$ touch .boto
$ vi .boto
```

Add your AWS credentials (Below are a fake example).

```
[Credentials]
aws_access_key_id = CDABGHEFCDABGHEFCDAB
aws_secret_access_key = ABGHEFCDABGHEFCDABGHEFCDABGHEFCDABGHEFCDAB
```

* Add AWS env variables**

```
$ export AWS_ACCESS_KEY_ID=CDABGHEFCDABGHEFCDAB
$ export AWS_SECRET_ACCESS_KEY=ABGHEFCDABGHEFCDABGHEFCDABGHEFCDABGHEFCDAB
$ export AWS_KEY=<your-aws-keypair-name>
$ export KEYNAME=key_<your-aws-keypair-name>
```

You probably want to persist these in your `~/.bash_profile`.

NOTE: This repo now only supports ansible 2.0.0.2 `pip uninstall ansible && pip install ansible==2.0.0.2`. There are known issues with certain versions of ansible. Make sure to install 2.0.0.2.

## Setup Controller on OSX

The "controller" is the machine that runs ansible, which is typically:

* Your developer workstation
* A virtual machine / docker container

The instructions below are for setting up directly on OSX.  If you prefer to run this under Docker, see the [Running under Docker](https://github.com/couchbaselabs/sync-gateway-testcluster/wiki/Running-under-Docker) wiki page.



By default, the user is set to `root`, which works for VM clusters.  If you are on AWS, you will need to change that to `centos`

## Setup Cluster

### Spin up VM's or Bare Metal machines

Requirements:

* Should have a centos user with full root access in /etc/sudoers

### Spin up Machines on AWS (DO NOT CHECK THESE FILES INTO SOURCE CONTROL)


**To kick off cluster**

```
$ python libraries/provision/create_and_instantiate_cluster.py \
    --stackname="YourCloudFormationStack" \
    --num-servers=1 \
    --server-type="m3.large" \
    --num-sync-gateways=2 \
    --sync-gateway-type="m3.medium" \
    --num-gatlings=1 \
    --gatling-type="m3.medium" \
    --num-lbs=0 \
    --lb-type="m3.medium" 
```

NOTE: currently need at least 3 sync gateways (1 sync gw and 2 sg_accels)

The AWS virtual machines will be accessible via the `AWS_KEY` you specified above.

If you want to install a load balancer in front of the Sync Gateway instances, set `--num-lbs` to 1.

## Setup Ansible inventory

**AWS**

Generate the Ansible Inventory file (`aws_perf_config`) via:

```
$ python libraries/provision/generate_ansible_inventory_from_aws.py \
     --stackname=YourCloudFormationStack \
     --targetfile=aws_perf_config
```

## Configure sync gateway index readers vs index writers

Modify `provisioning_config` to remove at least one node from the `[sync_gateway_index_writers]` list

**Virtual Machines**

Create and edit your provisioning configuration
```
$ cp provisioning_config.example provisioning_config
```
Add the ip endpoints you would like to target

One time only. Ansible playbooks require ssh access to run on the target hosts.  This script will attempt to install a common public key to ~/.ssh/knownhosts on the machines in the cluster via ssh-copy-id. 

```
$ ssh-keygen
Generating public/private rsa key pair.
Enter file in which to save the key (/Users/sethrosetter/.ssh/id_rsa):<test-key>
```

Attempt to install the shared key on all machines in the cluster defined in (`provisioning_config`)

```
python conf/install_keys.py \
  --key-name=<public-ssh-key-name> \
  --ssh-user=<user>
```

## SSH Key setup (AWS)

In order to use Ansible, the controller needs to have it's SSH keys in all the hosts that it's connecting to.  

Follow the instructions in [Docker container SSH key instructions](https://github.com/couchbaselabs/sync-gateway-testcluster/wiki/Docker-Container---SSH-Keys)

## Provision Cluster 

This step will install:

* 3rd party dependencies
* Couchbase Server
* Sync Gateway
* Gateload/Gatling load generators

Example building from source:

```
$ python libraries/provision/provision_cluster.py \
    --server-version=4.1.0 \
    --sync-gateway-branch=master
    --install-deps (first time only, this will install prerequisites to build / debug)
```

Example from a pre-built version (dev build):

```
$ python libraries/provision/provision_cluster.py \
    --server-version=3.1.1 \
    --sync-gateway-dev-build-url=feature/distributed_index \
    --sync-gateway-dev-build-number=345
    --install-deps (first time only, this will install prerequisites to build / debug)
```

Like all scripts, run `python provision/provision_cluster.py -h` to view help options.

If you experience ssh errors, you may need to verify that the key has been added to your ssh agent

```
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/<test-key>
```


## Run Performance Tests

**Gateload**

```
$ export PYTHONPATH=$PYTHONPATH:.
$ python performance_tests/run_tests.py --number-pullers 1000 --number-pushers 1000 --use-gateload --gen-gateload-config --reset-sync-gw --test-id="perftest" 
```

To stop the tests:

```
$ python performance_tests/kill_gateload.py
```

**Gatling**

```
$ export PYTHONPATH=$PYTHONPATH:.
$ python performance_tests/run_tests.py --number-pullers=1000 --number-pushers=1000
```

### Performance test data

Most of the performance test data will be pushed to Splunk (if the splunk forwarder is installed), but you can download the Heap + CPU profile data via:

```
$ ansible-playbook performance_tests/ansible/playbooks/collect-sync-gateway-profile.yml -i temp_ansible_hosts
```

## Run Functional tests

By default the logs from all of the sync_gateways will be zipped and placed in your /tmp directory if a test fails. You
can disable this behavior in functional_tests/settings

**Install dependencies (skip if using Docker container)**

```
pip install robotframework
pip install futures
pip install requests
```

**Add current directory to $PYTHONPATH**

```
$ export PYTHONPATH=$PYTHONPATH:.
```

###  To run a suite
```
robot testsuites/syncgateway/functional/1sg_1cbs.robot
```

The functional tests are organized in files names with the cluster configuration that they require. 

For instance, testsuites/syncgateway/functional/1sg_1cbs.robot requires resources/cluster_configs/1sg_1cbs to be defined.
 
1sg_1cbs would look like below

```
[couchbase_servers]
cb1 ansible_host=111.11.111.111

[sync_gateways]
sg1 ansible_host=222.22.222.222
```

### To run a test from a suite
```
robot -t  "test overloaded channel cache one" testsuites/syncgateway/functional/1sg_1cbs.robot
```

## Running android test suite

### Pre-requisites

* Android SDK. Download [Android Studio](http://developer.android.com/sdk/index.html) to install
* Monkeyrunner (ships with Android Studio, must be in your PATH)

```
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$ANDROID_HOME/tools:$ANDROID_HOME/platform-tools:$PATH
```

You will need this to bootstrap apk installation on your emulators (ex. Users/user/Library/Android/sdk/tools/monkeyrunner). 

### Create Android Emulator (AVD)

* Create new "dummy" project
* Click on AVD manager (purple icon)
* Create Virtual Device
* Click "Download" next to Marshmallow x86_64
* Hit Next/Finish to create it

### listener

**Note:** Read the previous section to install Python dependencies.

These tests live in the `functional_tests/android_listener_test` directory.

The scenarios can run on Android stock emulators/Genymotion emulators and devices.

If you're running Android stock emulators you should make sure they are using HAXM. Follow the instructions here to install (https://software.intel.com/en-us/android/articles/installation-instructions-for-intel-hardware-accelerated-execution-manager-mac-os-x).

Ensure the RAM allocated to your combined running emulators is less than the total allocated to HAXM. You can configure the RAM for your emulator images in the Android Virtual Device Manager and in HAXM by reinstalling via the .dmg in the android sdk folder.
 
To run the tests make sure you have lauched the correct number of emulators. You can launch them using the following command. 
```
emulator -scale 0.25 @Nexus_5_API_23 &
emulator -scale 0.25 @Nexus_5_API_23 &
emulator -scale 0.25 @Nexus_5_API_23 &
emulator -scale 0.25 @Nexus_5_API_23 &
emulator -scale 0.25 @Nexus_5_API_23 &
```
Verify that the names listed below match the device definitions for the test you are trying to run
```
adb devices -l
```
```
List of devices attached
emulator-5562          device product:sdk_google_phone_x86 model:Android_SDK_built_for_x86 device:generic_x86
emulator-5560          device product:sdk_google_phone_x86 model:Android_SDK_built_for_x86 device:generic_x86
emulator-5558          device product:sdk_google_phone_x86 model:Android_SDK_built_for_x86 device:generic_x86
emulator-5556          device product:sdk_google_phone_x86 model:Android_SDK_built_for_x86 device:generic_x86
emulator-5554          device product:sdk_google_phone_x86 model:Android_SDK_built_for_x86 device:generic_x86
```

Most of the port forwarding will be set up via instantiation of the Listener. However, you do need to complete some additional steps.

**Note:** Instantiating a Listener in `test_listener_rest.py` will automatically forward the port the listener is running on to one on localhost. However, that port forwarding will not be bound on the local IP of your computer. This can be useful when combining actual devices and emulators. The following section describes how to make the emulators reachable from devices.

Once you have emulators and possibly port forwarding setup, set the `P2P_APP` environment variable to the `.apk` of the application to be tested.

```
$ export P2P_APP=/path/to/apk
```

To run the test
```
$ robot testsuites/android/listener/
```

If the test fails with a hostname unreachable error then it's probably because port forwarding needs to be configured (read section below).

### Port forwarding (setup once)

Add the following lines to the file `/etc/sysctl.conf`
```
net.inet.ip.forwarding=1
net.inet6.ip6.forwarding=1
```

Specifying the 'local_port' when instantiating a Listener will forward the port on localhost only.
 
 We need to bind the port on the `en0` interface to be reachable on the Wi-Fi. On Mac, this can be done with `pfctl`. Create a new anchor file under `/etc/pf.anchors/com.p2p`:

```
rdr pass on lo0 inet proto tcp from any to any port 10000 -> 127.0.0.1 port 10000
rdr pass on en0 inet proto tcp from any to any port 10000 -> 127.0.0.1 port 10000

rdr pass on lo0 inet proto tcp from any to any port 11000 -> 127.0.0.1 port 11000
rdr pass on en0 inet proto tcp from any to any port 11000 -> 127.0.0.1 port 11000

...
```

Parse and test your anchor file to make sure there a no errors:

```
sudo pfctl -vnf /etc/pf.anchors/com.p2p
```

The file at `/etc/pf.conf` is the main configuration file that `pf` loads at boot. Make sure to add both lines below to `/etc/pf.conf`:

```
scrub-anchor "com.apple/*"
nat-anchor "com.apple/*"
rdr-anchor "com.apple/*"
rdr-anchor "com.p2p"      # Port forwading for p2p replications 
dummynet-anchor "com.apple/*"
anchor "com.apple/*"
load anchor "com.apple" from "/etc/pf.anchors/com.apple"
load anchor "com.p2p" from "/etc/pf.anchors/com.p2p"     # Port forwarding for p2p replications
```

The `lo0` are for local requests, and the `en0` entries are for external requests (coming from an actual device or another emulator targeting your host).

Next, load and enable `pf` by running the following:

```
$ sudo pfctl -ef /etc/pf.conf
```

Now, all the databases are reachable on the internal network via host:forwarded_port (ex. http://192.168.0.21:10000/db), where 192.168.0.21 is your host computer's ip and 10000 is the 'local_port' passed when instantiating the Listener.

## Monitoring the cluster
Make sure you have installed expvarmon 
```
go get github.com/divan/expvarmon
```

To monitor the Gateload expvars for [load_generators] nodes in the provisioning_config 
```
python utilities/monitor_gateload.py
```

To monitor the sync_gateway expvars for [sync_gateways] nodes in the provisioning_config 
```
python utilities/monitor_sync_gateway.py
```

## Collecting Sync Gateway logs

```
$ python utilities/fetch_sg_logs.py
```

## Reset Sync Gateway

```
$ ansible-playbook -i provisioning_config -u centos -e sync_gateway_config_filepath=../../../../conf/bucket_online_offline//bucket_online_offline_default_dcp_cc.json ./provision/ansible/playbooks/reset-sync-gateway.yml
```

*Note: replace the Sync Gateway config with the config that you need for your use case*


running a test case

The functional tests are organized in files names with the cluster configuration that they require. 

For instance, testsuites/syncgateway/functional/1sg_1cb.robot requires resources/cluster_configs/1sg_1cb to be defined.
 
1sg_1cbs would look like below

```
[couchbase_servers]
cb1 ansible_host=111.11.111.111

[sync_gateways]
sg1 ansible_host=222.22.222.222
```
 
To run a fixture
```
robot testsuites/syncgateway/functional/1sg_1cbs.robot
```

To run a test from a fixture
```
robot -t  "test overloaded channel cache one" testsuites/syncgateway/functional/1sg_1cbs.robot
```

Debugging

The below command will write a debug file which will include a dump of stacktraces which can be useful when identifying failures

```
robot -b debug.txt
```

