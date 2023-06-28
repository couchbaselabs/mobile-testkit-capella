from libraries.provision import capella_methods
from keywords.MobileRestClient import MobileRestClient
from keywords.utils import log_info
import string
import random
import json
import time 

def setupAppService(username, password, url, tenantId):
        varialeDict=dict()
        
        deploy = capella_methods.CapellaDeployments(username, password, tenantId, url)
        deploy.getJwtToken(varialeDict)

        projectName ="mobile-" + ''.join(random.choices(string.ascii_uppercase +
                             string.digits, k=8))
        deploy.createProject(projectName)

        clustertemplateFile = "libraries/provision/quick-3.json"
        with open(clustertemplateFile, 'r') as file:
             clustertemplate = json.load(file)
        deploy.deployCluster("mobile", "us-west-2", "aws", clustertemplate)
        deploy.waitForClusterHealth()
        time.sleep(10)
        bucketTemplateFile = "libraries/provision/bucket_template.json"
        with open(bucketTemplateFile) as file:
            file_contents = file.read()
        buckettemplate = json.loads(file_contents)
        deploy.createBucket(buckettemplate)
        instanceType = "c5.2xlarge"
        deploy.createAppService(instanceType)
        deploy.waitForAppServiceHealth()
        deploy.createAppEndpoint()
        deploy.getAppEndPointUrls()
        return deploy.AppServiceSetup(), deploy
        # deploy.deleteProject()

def destroyResources(deploy):
        deploy.destroySyncGateway()
        deploy.waitForAppServiceDelete()
        deploy.deleteCluster()
        deploy.waitForClusterDeletion()
        deploy.deleteProject()
        log_info('Resources deleted successfully')