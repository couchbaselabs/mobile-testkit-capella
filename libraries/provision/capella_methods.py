from keywords.utils import log_error, log_info
import requests
from requests import Response, Session
from requests.auth import HTTPBasicAuth
from enum import Enum
import json
import random
import string
import time
import restapi
from datetime import datetime, timedelta

import restapi.capella
# import restapi.capella.common
# import restapi.capella.common.CapellaAPI_v4
# from restapi.capella.lib import APIRequests
from restapi.capella.common.CapellaAPI_v4 import CommonCapellaAPI
from restapi.capella.dedicated.CapellaAPI_v4 import ClusterOperationsAPIs


# syncgateway specs class
class syncGatewaySpecs:
    def __init__(self, clusterId, instanceType, desiredCapacity, name):
        self.clusterId = clusterId
        self.desired_capacity = desiredCapacity
        self.name = name
        self.compute = {"type": instanceType}


# app-endpoint creation class
class appEndPointCreate:
    def __init__(self, bucketName, name, delta_sync=False, importFilter="", sync=""):
        self.bucket = bucketName
        self.name = name
        self.delta_sync = delta_sync
        self.import_filter = importFilter
        self.sync = sync


# project
class Culture(Enum):
    Mixed = 0
    English = 1
    Kanji = 2
    Hiragana = 3


# custom error class
class CapellaErrors(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


# project
class NewProject:
    def __init__(self, name, tenant_id):
        self.culture = Culture(1)
        self.name = name
        self.tenant_id = tenant_id
        self.generated = True

    def to_json(self):
        return json.dumps(self.__dict__)


# project
class ProjectPayload:
    def __init__(self, name, tenant_id, description=""):
        self.Name = name
        self.TenantID = tenant_id
        self.Description = description

    def to_json(self):
        return json.dumps(self.__dict__)


# cluster
class DiskConfig:
    def __init__(self, diskType=None, scenarioDiskType=None):
        self.CliDiskType = diskType
        self.scenarioDiskType = scenarioDiskType

    def to_json(self):
        return json.dumps(self.__dict__)


# cluster
class ClusterService:
    def __init__(self, type):
        self.Type = type

    def to_json(self):
        return json.dumps(self.__dict__)


# cluster
class ClusterInstance:
    def __init__(self, type, cpu=None, memoryinGB=50):
        self.type = type
        self.cpu = cpu
        self.memoryInGb = memoryinGB

    def to_json(self):
        return json.dumps(self.__dict__)


# cluster
class ClusterDisk:
    def __init__(self, type, sizeInGB, iops):
        self.type = type
        self.sizeInGb = sizeInGB
        self.iops = iops

    def to_json(self):
        return json.dumps(self.__dict__)


# cluster
class ClusterSpecs:
    def __init__(self, count, services=None, compute=None, disk=None):
        self.count = count
        self.services = services
        self.compute = compute
        self.disk = disk

    def to_json(self):
        return json.dumps(self.__dict__)


# cluster
class CreateCluster:
    def __init__(self, cidr, projectId, provider, region, singleAZ, name, server, timezone, specs=None):
        self.cidr = cidr
        self.projectId = projectId
        self.provider = provider
        self.region = region
        self.description = ""
        self.specs = specs
        self.singleAZ = singleAZ is None
        self.name = name
        self.server = server
        # self.timezone = timezone
        self.plan = "Developer Pro"


# base class
class CapellaDeployments:
    def __init__(self, username, password, tenantID, url,projectId):
        self.username = username
        self.password = password
        self.apiUrl = url
        self.tenantID = tenantID
        self.pid = projectId
        self._session = Session()


    # get jwt token for authentication
    def getJwtToken(self, resourceCredentials):
        resp = self._session.post("{}/sessions".format(self.apiUrl), auth=HTTPBasicAuth(self.username, self.password))
        if resp.status_code == 200:
            resp_obj = resp.json()
            resourceCredentials['jwt'] = resp_obj["jwt"]
            self.resourceCredentials = resourceCredentials
            log_info('JWT token retrieved')
            return True
        else:
            raise CapellaErrors("JWT fetch failed, Status Code: " + str(resp.status_code) + ", Message: " + resp.reason)

    def createProject(self, projectName):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        project = NewProject(projectName, self.tenantID)
        projectPayload = ProjectPayload(project.name, project.tenant_id)
        resp = self._session.post("{}/v2/organizations/{}/projects".format(self.apiUrl, self.tenantID), headers=headers, data=projectPayload.to_json())
        if resp.status_code == 201:
            resp_obj = resp.json()
            self.pid = resp_obj["id"]
            log_info("Project Created successfully")
        else:
            raise CapellaErrors("Project creation failed, Status Code: " + str(resp.status_code) + ", Message: " + resp.reason)

    def deleteProject(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        resp = self._session.delete("{}/v2/organizations/{}/projects/{}".format(self.apiUrl, self.tenantID, self.resourceCredentials['pid']), headers=headers)
        if resp.status_code == 204:
            log_info("Project Deleted successfully")
        else:
            raise CapellaErrors("Project deletion failed, Status Code: " + str(resp.status_code) + ", Message: " + resp.reason)

    # def convertClusterTemplate(self, template):
    #     diskType = "gp3"
    #     data = template["serviceGroups"]
    #     iops = 3000
    #     clusterSpecs = list()

    #     clusterSpecsDict = {"count": data[0]['size'], "services": data[0]['services'], "disk": clusterDiskDict, "compute": computeDict, "diskAutoScaling": {"enabled": True}, "provider": "aws"}
    #     clusterSpecs.append(clusterSpecsDict)
    #     return clusterSpecs

    def getDeploymentOptions(self):
        params = {
            "tenantId": self.tenantID
        }
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        resp = self._session.get("{}/v2/organizations/{}/clusters/deployment-options".format(self.apiUrl, self.tenantID), headers=headers, params=params)
        if resp.status_code == 200:
            resp_obj = resp.json()
            self.resourceCredentials['cidr'] = resp_obj["suggestedCidr"]
        else:
            self.resourceCredentials['cidr'] = "10.0.8.0/23"

    def createCluster(self, region, provider, template):
        log_info('creating cluster')
        clusterName = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.getDeploymentOptions()
        cidr = self.resourceCredentials['cidr']
        projectId = self.pid
        provider = provider
        region = region
        specs = template["serviceGroups"]
        singleAZ = True
        name = clusterName
        server_versions = "7.6"
        cluster = CreateCluster(cidr, projectId, provider, region, singleAZ, name, server_versions, "PT")
        cluster = vars(cluster)
        cluster['specs'] = specs
        log_info('cluster specs'+str(cluster))
        return cluster

    def deployCluster(self, namePrefix, region, provider, template):
        log_info('Deploy cluster')
        cluster = self.createCluster(region, provider, template)
        log_info("cluster specs created")
        name = namePrefix + cluster["name"]
        cluster["name"] = name
        log_info("Name: "+name)
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        # cluster = json.dumps(cluster)
        log_info(cluster)
        log_info("json dums"+str(cluster))
        req="{}/v2/organizations/{}/clusters/deploy".format(self.apiUrl, self.tenantID)
        log_info(req)
        clusterObj=ClusterOperationsAPIs(url=self.apiUrl,bearer_token=self.resourceCredentials['jwt'],secret=None,access=None)
        log_info("object created")
        resp=clusterObj.create_cluster(organizationId=self.tenantID,projectId=self.pid,cloudProvider=provider,couchbaseServer="7.6",
                                  serviceGroups=cluster['specs'],headers=headers, name=name)
        # resp = self._session.post(req, data=cluster, timeout=10, headers=headers)
        # restapi.capella.common.CapellaAPI_v4.APIRequests
        
        log_info("req sent"+str(resp))
        if resp.status_code == 202:
            log_info("202")
            resp_obj = resp.json()
            log_info(resp_obj)
            self.resourceCredentials['clusterId'] = resp_obj['id']
            self.resourceCredentials['clusterName'] = name
            log_info("clus")
        else:
            log_info("Error deploying cluster:" + resp._content)

    def getCluster(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenanId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        resp = self._session.get("{}/v2/organizations/{}/projects/{}/clusters/{}".format(self.apiUrl, tenanId, projectId, clusterId), headers=headers)
        if resp.status_code == 200:
            resp_obj = resp.json()
            return resp_obj['data']['status']['state']
        else:
            return resp

    def waitForClusterHealth(self):
        currentTime = datetime.now()
        while(datetime.now() < (currentTime + timedelta(minutes=130))):
            status = self.getCluster()
            if(type(status) == Response):
                log_info(status.status_code)
                return "Failed to get cluster status"
            if status == "healthy":
                log_info("cluster is in healthy state")
                return None
            if status == "deployment_failed":
                log_info("cluster deployment failed")
                return "Cluster Deployment Failed"
            log_info("Cluster still deploying")
            time.sleep(5)

    def createBucket(self, template):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        self.resourceCredentials['bucketName'] = template["name"]
        ans = json.dumps(template)
        resp = self._session.post("{}/v2/organizations/{}/projects/{}/clusters/{}/buckets".format(self.apiUrl, self.tenantID, self.resourceCredentials['pid'], self.resourceCredentials['clusterId']), headers=headers, data=ans)
        if resp.status_code == 201:
            log_info("Bucket created successfully")
        else:
            log_info(resp.status_code)
            raise CapellaErrors("Failed to create bucket")

    def createAppService(self, instanceType):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        clusterId = self.resourceCredentials['clusterId']
        instanceType = instanceType
        desiredCapacity = 2
        backendName = "test-" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        specs = json.dumps(syncGatewaySpecs(clusterId, instanceType, desiredCapacity, backendName).__dict__)
        resp = self._session.post("{}/v2/organizations/{}/backends".format(self.apiUrl, self.tenantID), data=specs, headers=headers)
        if resp.status_code == 202:
            resp_object = resp.json()
            self.resourceCredentials['backendId'] = resp_object['id']
            log_info("AppService deploy start")
        else:
            log_info(resp.status_code)
            raise CapellaErrors("Failed to create app-service")

    def getAppService(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenanId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        resp = self._session.get("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}".format(self.apiUrl, tenanId, projectId, clusterId, backendId), headers=headers)
        if resp.status_code == 200:
            resp_obj = resp.json()
            return resp_obj['data']['status']['state']
        else:
            return resp

    def waitForAppServiceHealth(self):
        currentTime = datetime.now()
        while(datetime.now() < (currentTime + timedelta(minutes=130))):
            status = self.getAppService()
            if(type(status) == Response):
                log_info(status.status_code)
                return "Failed to get app-service status"
            if status == "healthy":
                log_info("appservice is in healthy state")
                return None
            if status == "deployment_failed":
                log_info("appservice deployment failed")
                return "appservice Deployment Failed"
            log_info("appservice still deploying")
            time.sleep(5)

    def createAppEndpoint(self):
        bucketName = self.resourceCredentials['bucketName']
        name = "appendpoint"
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        specs = json.dumps(appEndPointCreate(bucketName, name).__dict__)
        resp = self._session.post("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}/databases".format(self.apiUrl, tenantId, projectId, clusterId, backendId), data=specs, headers=headers)
        if resp.status_code == 200:
            self.resourceCredentials['endpointName'] = name
        else:
            log_info(resp.status_code)
            raise CapellaErrors("Failed to create app endpoint")

    def getAppEndPointUrls(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        appEndPointName = self.resourceCredentials['endpointName']
        resp = self._session.get("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}/databases/{}/connect".format(self.apiUrl, tenantId, projectId, clusterId, backendId, appEndPointName), headers=headers)
        if resp.status_code == 200:
            resp_obj = resp.json()
            self.resourceCredentials['adminURL'] = resp_obj['data']['adminURL']
            self.resourceCredentials['publicURL'] = resp_obj['data']['publicURL']
        else:
            log_info(resp.status_code)
            raise CapellaErrors("Failed to get connection urls")

    def myIPEndpoint(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        resp = self._session.get("{}/v2/organizations/{}/projects/{}/clusters/{}/myip".format(self.apiUrl, tenantId, projectId, clusterId), headers=headers)
        if resp.status_code == 200:
            resp_obj = resp.json()
            return resp_obj["ip"]
        else:
            return resp

    def appServiceAllowIPEndpoint(self, cidr):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        payload = json.dumps({
            "cidr": cidr,
            "comment": "for testing cbl"
        })
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        resp = self._session.post("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}/allowip".format(self.apiUrl, tenantId, projectId, clusterId, backendId), headers=headers, data=payload)
        if resp.status_code == 200:
            log_info("IP address added")
        elif resp.status_code < 200 or resp.status_code >= 300:
            log_info("Unexpected error occured")
        else:
            log_info("Failed to add IP")
            log_info(resp.status_code)

    def appEndpointAddAdminCredentials(self, username, password):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        appEndPointName = self.resourceCredentials['endpointName']
        payload = json.dumps({
            "name": username,
            "password": password
        })
        retries = 0
        while retries < 5:
            try:
                resp = self._session.post("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}/databases/{}/adminusers".format(self.apiUrl, tenantId, projectId, clusterId, backendId, appEndPointName), headers=headers, data=payload)
                if resp.status_code == 200:
                    log_info("Admin credentials added")
                    return
                elif resp.status_code >= 200 and resp.status_code < 300:
                    log_info("Unexpected error occurred")
                else:
                    log_info("Failed to add admin credentials")
                    log_info(resp)
                    raise CapellaErrors("Failed to add admin users")
            except requests.exceptions.RequestException as err:
                log_info("Connection Error: {} - Retrying".format(err))
                retries += 1
                time.sleep(5)
        log_info("Maximum number of retries exceeded")

    def resumeEndPoint(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        appEndPointName = self.resourceCredentials['endpointName']
        currentTime = datetime.now()
        while(datetime.now() < (currentTime + timedelta(minutes=5))):
            resp = self._session.post("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}/databases/{}/online".format(self.apiUrl, tenantId, projectId, clusterId, backendId, appEndPointName), headers=headers)
            if resp.status_code == 200:
                break
            elif resp.status_code == 404:
                raise CapellaErrors("The resource doesn't exist")

    def appServiceGetEndPoint(self):
        params = {
            "page": 1,
            "perPage": 10
        }
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        resp = self._session.get("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}/databases".format(self.apiUrl, tenantId, projectId, clusterId, backendId), headers=headers, params=params)
        return resp

    def waitForEndpointResume(self):
        appEndPointName = self.resourceCredentials['endpointName']
        currentTime = datetime.now()
        target = None
        while(datetime.now() < (currentTime + timedelta(minutes=2))):
            response = self.appServiceGetEndPoint()
            if response.status_code == 200:
                resp_obj = response.json()
                for endpoint in resp_obj["data"]:
                    if endpoint["data"]["name"] == appEndPointName:
                        target = endpoint["data"]
                if target is None:
                    raise CapellaErrors("Endpoint not found")
                if "offline" not in target:
                    log_info("Endpoint resumed")
                    break
                else:
                    log_info("Endpoint is still paused")

    def appServiceReadyEndpoint(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        resp = self._session.get("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}/ready".format(self.apiUrl, tenantId, projectId, clusterId, backendId), headers=headers)
        return resp

    def waitForReady(self):
        currentTime = datetime.now()
        while(datetime.now() < (currentTime + timedelta(minutes=2))):
            resp = self.appServiceReadyEndpoint()
            if resp.status_code == 200:
                log_info("App endpoint ready")
                return
        raise CapellaErrors("Not able to get 200 from ready endpoint")

    def AppServiceSetup(self, username="admin", password="Password123,"):
        myip = self.myIPEndpoint()
        if type(myip) == Response:
            raise CapellaErrors("Failed to fetch the IP")
        cidr = myip + '/32'
        self.appServiceAllowIPEndpoint(cidr)
        self.resumeEndPoint()
        self.waitForEndpointResume()
        self.waitForReady()
        self.appEndpointAddAdminCredentials(username, password)
        return self.resourceCredentials

    def destroySyncGateway(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        backendId = self.resourceCredentials['backendId']
        currentTime = datetime.now()
        resp = Response()
        while(currentTime < currentTime + timedelta(minutes=5)):
            resp = self._session.delete("{}/v2/organizations/{}/projects/{}/clusters/{}/backends/{}".format(self.apiUrl, tenantId, projectId, clusterId, backendId), headers=headers)
            if resp.status_code == 202:
                log_info("Appservice deletion started")
                break
            elif resp.status_code == 404:
                log_error("Appserice resource not found")
                break
            time.sleep(5)

    def waitForAppServiceDelete(self):
        currentTime = datetime.now()
        while(datetime.now() < (currentTime + timedelta(minutes=130))):
            status = self.getAppService()
            if(type(status) == Response):
                log_info("Appservice deletion complete")
                return
            log_info("appservice still destroying")
            time.sleep(5)

    def deleteCluster(self):
        headers = {
            "Authorization": f"Bearer {self.resourceCredentials['jwt']}"
        }
        tenantId = self.tenantID
        projectId = self.resourceCredentials['pid']
        clusterId = self.resourceCredentials['clusterId']
        resp = self._session.delete("{}/v2/organizations/{}/projects/{}/clusters/{}".format(self.apiUrl, tenantId, projectId, clusterId), headers=headers)
        if resp.status_code == 202:
            log_info("Cluster destroy started")
        else:
            raise CapellaErrors("Failed to destroy cluster")

    def waitForClusterDeletion(self):
        currentTime = datetime.now()
        while(datetime.now() < (currentTime + timedelta(minutes=130))):
            resp = self.getCluster()
            if type(resp) == Response and resp.status_code == 404:
                log_info("Cluster deleted")
                break
