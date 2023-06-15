from tkinter import Variable
from requests import Session, session
from requests.auth import HTTPBasicAuth
from enum import Enum
import json
from datetime import datetime

#project 
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

#cluster
class ClusterService:
    def __init__(self, type):
        self.Type = type

#cluster
class ClusterInstance:
    def __init__(self, type, cpu, memoryinGB):
        self.Type = type
        self.CPU = cpu
        self.MemoryInGb = memoryinGB

#cluster
class ClusterDisk:
    def __init__(self, type, sizeInGB, iops):
        self.Type = type
        self.SizeInGb = sizeInGB
        self.IOPS = iops

#cluster
class ClusterSpecs:
    def __init__(self, count, services, compute, disk):
        self.Count = count
        self.Services = services
        self.Compute = compute
        self.Disk = disk
#cluster
class CreateCluster:
    def __init__(self, cidr, projectId, provider, region, tenentId, specs, package, singleAZ, name):
        self.cidr = cidr
        self.projectId = projectId
        self.provider = provider
        self.region = region
        self.tenantId = tenentId
        self.specs = specs
        self.package = package
        self.singleAZ = singleAZ ==  None
        self.name = name
# base class
class CapellaDeployments:
    def __init__(self, username, password,tenantID, url):
        self.username = username
        self.password = password
        self.apiUrl = url
        self.tenantID = tenantID
        self._session = Session()

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
        data = json.load(template)["servers"]
        if data[0].AWS.EbsSizeGib == "":
            raise CapellaErrors("Failed to deploy cluster: invalid ebs size")
        iops = 3000
        services = data[0].services
        serviceList = list()
        for ser in services:
            serviceList.append(ClusterService(ser))
        clusterSpecs = list()
        clusterDisk = ClusterDisk(type=diskType, sizeInGB=data[0].aws.ebsSizeGib, iops=iops)

        clusterSpecs.append(ClusterSpecs(count=data[0].size, services=serviceList, compute=ClusterInstance(type=data[0].aws.instanceSize), disk=clusterDisk))
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
            self.variableDict['cidr'] = "10.2.0.0/20"

    def createCluster(self, region, provider, template):
        

