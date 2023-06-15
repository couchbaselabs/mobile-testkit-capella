from tkinter import Variable
from wsgiref.simple_server import server_version
from requests import Session, session
from requests.auth import HTTPBasicAuth
from enum import Enum
import json
import random
import string

# project
class Culture(Enum):
    Mixed = 0
    English = 1
    Kanji = 2
    Hiragana = 3

class CapellaErrors(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

#project
class NewProject:
    def __init__(self, name, tenant_id):
        self.culture = Culture(1)
        self.name = name
        self.tenant_id = tenant_id
        self.generated = True

    def to_json(self):
        return json.dumps(self.__dict__)

#project
class ProjectPayload:
    def __init__(self, name, tenant_id, description=""):
        self.Name = name
        self.TenantID = tenant_id
        self.Description = description

    def to_json(self):
        return json.dumps(self.__dict__)

#cluster
class DiskConfig:
    def __init__(self, diskType=None, scenarioDiskType=None):
        self.CliDiskType = diskType
        self.scenarioDiskType = scenarioDiskType

    def to_json(self):
        return json.dumps(self.__dict__)

#cluster
class ClusterService:
    def __init__(self, type):
        self.Type = type

    def to_json(self):
        return json.dumps(self.__dict__)

#cluster
class ClusterInstance:
    def __init__(self, type, cpu=None, memoryinGB=50):
        self.type = type
        self.cpu = cpu
        self.memoryInGb = memoryinGB
    def to_json(self):
        return json.dumps(self.__dict__)

#cluster
class ClusterDisk:
    def __init__(self, type, sizeInGB, iops):
        self.type = type
        self.sizeInGb = sizeInGB
        self.iops = iops
    def to_json(self):
        return json.dumps(self.__dict__)

#cluster
class ClusterSpecs:
    def __init__(self, count, services=None, compute=None, disk=None):
        self.count = count
        self.services = services
        self.compute = compute
        self.disk = disk
    def to_json(self):
        return json.dumps(self.__dict__)

#cluster
class CreateCluster:
    def __init__(self, cidr, projectId, provider, region, singleAZ, name, server, timezone, specs=None):
        self.cidr = cidr
        self.projectId = projectId
        self.provider = provider
        self.region = region
        self.description = ""
        self.specs = specs
        self.singleAZ = singleAZ ==  None
        self.name = name
        self.server = server
        self.timezone = timezone
        self.plan = "Developer Pro"

# base class
class CapellaDeployments:
    def __init__(self, username, password,tenantID, url):
        self.username = username
        self.password = password
        self.apiUrl = url
        self.tenantID = tenantID
        self._session = Session()

    def to_json(self):
        return json.dumps(self.__dict__)

    def getJwtToken(self, variableDict):
        resp = self._session.post("{}/sessions".format(self.apiUrl), auth=HTTPBasicAuth(self.username, self.password))
        if resp.status_code == 200:
            resp_obj = resp.json()
            variableDict['jwt'] = resp_obj["jwt"]
            self.variableDict = variableDict
            print('JWT token retrieved')
        else: 
            raise CapellaErrors("JWT fetch failed, Status Code: " + str(resp.status_code) +", Message: " + resp.reason)
        
    def createProject(self, projectName):
        headers = {
            "Authorization": f"Bearer {self.variableDict['jwt']}"
        }
        project = NewProject(projectName, self.tenantID)
        projectPayload = ProjectPayload(project.name, project.tenant_id)
        resp = self._session.post("{}/v2/organizations/{}/projects".format(self.apiUrl, self.tenantID), headers=headers, data=projectPayload.to_json())
        if resp.status_code == 201:
            resp_obj = resp.json()
            self.variableDict['pid'] = resp_obj["id"]
            print("Project Created successfully")
        else:
            raise CapellaErrors("Project creation failed, Status Code: " + str(resp.status_code) +", Message: " + resp.reason)
        
    def deleteProject(self):
        headers = {
            "Authorization": f"Bearer {self.variableDict['jwt']}"
        }
        resp = self._session.delete("{}/v2/organizations/{}/projects/{}".format(self.apiUrl, self.tenantID, self.variableDict['pid']), headers=headers)
        if resp.status_code == 204:
            print("Project Deleted successfully")
        else:
            raise CapellaErrors("Project deletion failed, Status Code: " + str(resp.status_code) +", Message: " + resp.reason)

    def convertClusterTemplate(self, template):
        diskType = "gp3"
        data = template["servers"]
        if data[0]['aws']['ebsSizeGib'] == "":
            raise CapellaErrors("Failed to deploy cluster: invalid ebs size")
        iops = 3000
        services = data[0]['services']
        # serviceList = list()
        # for ser in services:
        #     serviceList.append(vars(ClusterService(ser)))
        clusterSpecs = list()
        clusterDiskDict = vars(ClusterDisk(type=diskType, sizeInGB=data[0]['aws']['ebsSizeGib'], iops=iops))
        # computeDict = vars(ClusterInstance(type=data[0]['aws']['instanceSize']))
        computeDict = "m5.xlarge"

        clusterSpecsDict = {"count": data[0]['size'], "services": ["kv",
                "index",
                "n1ql",
                "fts"], "disk": clusterDiskDict, "compute": computeDict, "diskAutoScaling": {
                "enabled": True
            }, "provider": "aws"}
        clusterSpecs.append(clusterSpecsDict)
        return clusterSpecs
    
    def getDeploymentOptions(self):
        params = {
            "tenantId": self.tenantID
        }
        headers = {
            "Authorization": f"Bearer {self.variableDict['jwt']}"
        }
        resp = self._session.get("{}/v2/organizarion/{}/clusters/deployment-options".format(self.apiUrl, self.tenantID), headers=headers, params=params)
        if resp.status_code == 200:
            resp_obj = resp.json()
            self.variableDict['cidr'] = resp_obj["suggestedCidr"]
        else:
            self.variableDict['cidr'] = "10.0.8.0/23"

    def createCluster(self, region, provider, template):
        clusterName = ''.join(random.choices(string.ascii_lowercase +
                             string.digits, k=8))
        self.getDeploymentOptions()
        cidr = self.variableDict['cidr']
        projectId = self.variableDict['pid']
        provider = provider
        region = region
        specs = self.convertClusterTemplate(template)
        singleAZ = True
        name = clusterName
        server_versions = "7.1"
        cluster = CreateCluster(cidr, projectId, provider, region, singleAZ, name, server_versions, "PT")
        cluster = vars(cluster)
        cluster['specs'] = specs
        return cluster
    

    def deployCluster(self, namePrefix, region, provider, template):
        cluster = self.createCluster(region, provider, template)
        name =  namePrefix + cluster["name"]
        cluster["name"] = name
        cluster
        headers = {
            "Authorization": f"Bearer {self.variableDict['jwt']}"
        }
        cluster = json.dumps(cluster)
        resp = self._session.post("{}/v2/organizations/{}/clusters".format(self.apiUrl, self.tenantID), data=cluster, timeout=10, headers=headers)
        if resp.status_code == 202:
            resp_obj = resp.json()
            self.variableDict['clusterId'] = resp_obj['id']
            self.variableDict['clusterName'] = name
            print(self.variableDict)
        else:
            print(resp._content)